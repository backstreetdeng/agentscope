"""Forecast evidence linkage and deterministic analysis on synthetic data."""
import unittest
from unittest.mock import Mock, patch

from integrations.forecast_insights import analyze, load_result, _forecast_changes, _seasonality
from integrations.forecast_local_assistant import allow_loopback_request, answer, validate_request
from integrations.chronos2_data import ProvinceWorkbook


def fixture():
    records = {}
    history = []
    for year in range(2020, 2025):
        for month in range(1, 13):
            ym = f'{year}-{month:02d}'
            value = (year - 2019) * 100 + month
            records[(ym, '甲', '纯电动')] = value
            records[(ym, '乙', '纯电动')] = value * 2
            history.append((ym, float(value)))
    workbook = ProvinceWorkbook('sha-1', ('乙','甲'), ('纯电动',), records, '2020-01', '2024-12', 0)
    data = {'source_sha256':'sha-1','data_cutoff':'2024-12','province':'甲','energy':'纯电动',
            'model':'example','scenario':'base','metric':'零售','unit':'辆',
            'forecast':[{'month':'2025-01','p10':450,'p50':500,'p90':550},
                        {'month':'2025-02','p10':500,'p50':600,'p90':700}]}
    return workbook, data, history


class InsightsTests(unittest.TestCase):
    def test_rejects_changed_workbook(self):
        workbook, data, _ = fixture(); data['source_sha256'] = 'other'
        with self.assertRaisesRegex(ValueError, '已变化'):
            load_result('run', job_store=Mock(get=Mock(return_value={'status':'completed','data':data})),
                        workbook_loader=lambda:workbook)

    def test_rejects_pending_result(self):
        with self.assertRaisesRegex(ValueError, '尚未完成'):
            load_result('run', job_store=Mock(get=Mock(return_value={'status':'running'})))

    def test_predict_growth_sources_and_zero_denominator(self):
        rows = _forecast_changes([('2024-01',0),('2024-12',100)], [
            {'month':'2025-01','p10':9,'p50':10,'p90':11},
            {'month':'2025-02','p10':18,'p50':20,'p90':22}])
        self.assertEqual(rows[0]['mom_pct'], -90)
        self.assertIsNone(rows[0]['yoy_pct'])
        self.assertEqual(rows[0]['yoy_reference'], '历史实际')
        self.assertEqual(rows[1]['mom_pct'], 100)
        self.assertEqual(rows[1]['mom_reference'], '上月预测')

    def test_seasonality_uses_full_years_only(self):
        result = _seasonality([(f'{year}-{i:02d}', 10) for year in (2021,2022,2023) for i in range(1,13)] + [('2024-01',1000)])
        self.assertEqual(result['years'], ['2021', '2022', '2023'])
        self.assertEqual(result['monthly_index']['1'], 100)
        self.assertIsNone(_seasonality([('2023-%02d' % i, 10) for i in range(1,13)]))

    def test_comparison_is_history_and_same_cutoff(self):
        workbook, data, history = fixture()
        result = analyze({'result':data,'history':history,'workbook':workbook,'run_id':'run'}, '哪些省销量增长最快？')
        self.assertIn('历史实际', result['comparison']['kind'])
        self.assertEqual(result['comparison']['recent_end'], '2024-12')
        self.assertEqual(result['comparison']['groups_eligible'], 2)
        self.assertFalse(result['external_citation_allowed'])

    def test_related_result_must_match_scope_and_data_version(self):
        workbook, data, _ = fixture()
        other = dict(data, province='乙', forecast=None, backtest={'records':[]})
        store = Mock(get=Mock(side_effect=lambda run_id: {'status':'completed', 'data':data if run_id == 'a' else other}))
        with self.assertRaisesRegex(ValueError, '范围或数据版本不同'):
            load_result('a', 'b', job_store=store, workbook_loader=lambda:workbook)

    def test_related_forecast_and_backtest_are_combined(self):
        workbook, data, _ = fixture()
        other = dict(data, forecast=None, backtest={'records':[{'month':'2024-01'}]})
        store = Mock(get=Mock(side_effect=lambda run_id: {'status':'completed', 'data':data if run_id == 'a' else other}))
        result = load_result('a', 'b', job_store=store, workbook_loader=lambda:workbook)
        self.assertTrue(result['result']['forecast'])
        self.assertTrue(result['result']['backtest'])
        self.assertEqual(result['related_run_id'], 'b')

    def test_local_only_request_guards(self):
        self.assertTrue(allow_loopback_request('127.0.0.1', '127.0.0.1:7860', 'http://127.0.0.1:7860'))
        self.assertFalse(allow_loopback_request('192.168.1.2', '127.0.0.1:7860', 'http://127.0.0.1:7860'))
        self.assertFalse(allow_loopback_request('127.0.0.1', 'evil.example:7860', 'http://evil.example:7860'))
        self.assertFalse(allow_loopback_request('127.0.0.1', '127.0.0.1:7860', 'http://127.0.0.1:9999'))
        self.assertFalse(allow_loopback_request('127.0.0.1', '127.0.0.1:7860', 'https://evil.example'))

    def test_local_followup_uses_previous_topic_not_as_fact(self):
        workbook, data, history = fixture()
        context = {'result':data,'history':history,'workbook':workbook,'run_id':'chronos-'+'a'*32}
        args = {'run_id':context['run_id'], 'question':'那哪些月份？', 'prior_questions':['历史季节性如何？']}
        with patch('integrations.forecast_local_assistant.load_result',return_value=context), \
             patch('socket.create_connection',side_effect=AssertionError('network not allowed')):
            result = answer(args)
        self.assertEqual(result['mode'],'local_deterministic')
        self.assertTrue(any('历史季节性' in line for line in result['facts']))
        self.assertFalse(result['analysis']['external_citation_allowed'])

    def test_foreign_provider_or_missing_result_rejected(self):
        with self.assertRaises(ValueError): validate_request({'question':'趋势'})
        with self.assertRaises(ValueError): validate_request({'run_id':'chronos-'+'a'*32,'question':'趋势','provider':'deepseek_flash'})

    def test_backtest_errors_group_by_target_month(self):
        workbook, data, history = fixture()
        data = dict(data, forecast=None, backtest={'origins':2,'horizon':2,'observations':3,
             'records':[{'origin':'2024-09','month':'2024-11','horizon':2,'actual':100,'p50':120},
                        {'origin':'2024-10','month':'2024-11','horizon':1,'actual':100,'p50':140},
                        {'origin':'2024-10','month':'2024-12','horizon':2,'actual':100,'p50':110}]})
        result = analyze({'result':data,'history':history,'workbook':workbook,'run_id':'run'}, '回测误差最大的月份')
        worst = result['backtest']['worst_months'][0]
        self.assertEqual((worst['month'], worst['observations'], worst['mean_abs_error_pct']), ('2024-11', 2, 30))


if __name__ == '__main__': unittest.main()
