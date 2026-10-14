"""Real file and failure-mode acceptance for deterministic forecast calculations."""
import copy
import hashlib
import io
import unittest
from pathlib import Path

from openpyxl import Workbook
from utils.passenger_forecast import ForecastInputError, parse_history, build_forecast, validate_forecast


BUSINESS_FILE = Path('D:/document/WXWork/1688852089355778/Cache/File/2026-10/2012起分月PC+NEV销量.xlsx')
TARGETS = {2026: 1960, 2027: 2060}


def csv_history(first=2020, last=2026, current_months=8):
    lines = ['年份,月份,乘用车总量,新能源销量']
    for year in range(first,last+1):
        for month in range(1,(current_months if year == last else 12)+1):
            total = 1000000 + month*10000 + (year-first)*1000
            nev = total * (0.1+(year-first)*0.04+month*0.001)
            lines.append(f'{year},{month},{total},{nev}')
    return ('\n'.join(lines)).encode('utf-8')


def xlsx(rows, percentage=False):
    wb = Workbook()
    for row in rows: wb.active.append(row)
    if percentage: wb.active['D2'].number_format = '0.00%'
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


class ForecastTests(unittest.TestCase):
    def setUp(self):
        self.history = parse_history(csv_history(), 'history.csv')

    def test_real_business_workbook_read_only_and_screenshot_totals(self):
        if not BUSINESS_FILE.exists(): self.skipTest('Business workbook unavailable in this environment')
        before = BUSINESS_FILE.read_bytes()
        history = parse_history(before, BUSINESS_FILE.name)
        self.assertEqual(history['summary']['count'], 176)
        self.assertEqual(history['summary']['latest_period'], '2026-08')
        self.assertEqual(history['summary']['complete_years'], list(range(2012,2026)))
        result = build_forecast(history,2027,TARGETS,'2026-10-10')
        self.assertEqual(result['history_window'],list(range(2021,2026)))
        self.assertEqual([round(r['total'],2) for r in result['rows'][:7]], [190.71,114.98,153.79,147.74,161.63,183.01,160.22])
        self.assertAlmostEqual(result['summary']['penetration'],68.73640134751625)
        self.assertEqual(validate_forecast(result,history,TARGETS)['status'],'passed')
        self.assertEqual(hashlib.sha256(BUSINESS_FILE.read_bytes()).hexdigest(),hashlib.sha256(before).hexdigest())

    def test_bridge_preserves_sources_and_fixed_annuals(self):
        result = build_forecast(self.history,2027,TARGETS,'2026-10-10')
        self.assertEqual(len(result['bridge_rows']),12)
        self.assertEqual(result['bridges'][0]['summary']['provided_months'],list(range(1,9)))
        source = [r for r in self.history['records'] if r['year']==2026]
        for raw, out in zip(source,result['bridge_rows']):
            self.assertEqual((raw['total'],raw['nev'],raw['source_cells']),(out['total'],out['nev'],out['source_cells']))
            self.assertEqual(out['status'],'provided')
        self.assertAlmostEqual(sum(r['total'] for r in result['rows']),2060)
        self.assertAlmostEqual(sum(r['total'] for r in result['bridge_rows']),1960)
        self.assertEqual(validate_forecast(result,self.history,TARGETS)['status'],'passed')

    def test_missing_target_or_bridge_target_never_invented(self):
        for annuals in ({2026:1960},{2027:2060}):
            with self.assertRaises(ForecastInputError): build_forecast(self.history,2027,annuals,'2026-10-10')

    def test_infeasible_annual_rejected(self):
        with self.assertRaisesRegex(ForecastInputError,'低于'):
            build_forecast(self.history,2027,{2026:1,2027:2060},'2026-10-10')

    def test_missing_pair_rejected_both_blank_not_zero(self):
        with self.assertRaisesRegex(ForecastInputError,'配对缺失'):
            parse_history(b'year,month,total,nev\n2025,1,100,','bad.csv')
        h = parse_history(b'year,month,total,nev\n2025,1,100,20\n2025,2,,','ok.csv')
        self.assertEqual(len(h['records']),1)
        self.assertIn('2025-02',h['summary']['missing_periods'])

    def test_negative_excess_duplicate_nonfinite_rejected(self):
        for data in ('2025,1,-1,0','2025,1,100,101','2025,1,100,20\n2025,1,100,20','2025,1,NaN,20','2025,13,100,20'):
            with self.subTest(data=data), self.assertRaises(ForecastInputError):
                parse_history(('year,month,total,nev\n'+data).encode(),'bad.csv')

    def test_formula_without_cache_rejected(self):
        with self.assertRaisesRegex(ForecastInputError,'公式没有缓存'):
            parse_history(xlsx([['year','month','total','nev'],[2025,1,'=100+100',50]]),'bad.xlsx')

    def test_long_xlsx_percent_and_units(self):
        h = parse_history(xlsx([['年份','月份','乘用车总量（万辆）','新能源渗透率'],[2025,1,100,0.5]],True),'good.xlsx','wan')
        self.assertEqual(h['records'][0]['nev'],50)
        self.assertEqual(h['records'][0]['source_values']['penetration'],0.5)
        with self.assertRaisesRegex(ForecastInputError,'单位不一致'):
            parse_history(xlsx([['年份','月份','乘用车总量（万辆）','新能源销量'],[2025,1,100,50]]),'bad.xlsx','vehicle')
        with self.assertRaises(ForecastInputError): parse_history(csv_history(),'bad.csv','auto')

    def test_future_records_are_not_training_or_preserved_values(self):
        h = parse_history(csv_history(current_months=12),'future.csv')
        r = build_forecast(h,2027,TARGETS,'2026-10-10')
        self.assertEqual(r['history_window'],list(range(2021,2026)))
        self.assertEqual(r['bridges'][0]['summary']['provided_months'],list(range(1,10)))
        self.assertEqual(r['excluded_periods'],['2026-10','2026-11','2026-12'])
        self.assertEqual(validate_forecast(r,h,TARGETS)['status'],'passed')

    def test_backtest_cutoff_prevents_leakage(self):
        h = parse_history(csv_history(first=2012,last=2026),'backtest.csv')
        r = build_forecast(h,2018,{2018:1800},'2017-12-31')
        self.assertEqual(r['history_window'],list(range(2013,2018)))
        self.assertTrue(all(row['status']=='forecast' for row in r['rows']))
        self.assertEqual(r['bridge_rows'],[])
        self.assertEqual(validate_forecast(r,h,{2018:1800})['status'],'passed')

    def test_validator_rejects_corrupted_result(self):
        good = build_forecast(self.history,2027,TARGETS,'2026-10-10')
        mutations = [lambda r:r['rows'][0].__setitem__('total',-1),
                     lambda r:r['summary'].__setitem__('penetration',1),
                     lambda r:r['rows'][0].__setitem__('allocation_weight',0.99),
                     lambda r:r['rows'][0].__setitem__('seasonal_weight',0.99),
                     lambda r:r['bridges'][0]['rows'][0].__setitem__('total',999),
                     lambda r:r.__setitem__('history_window',[2022,2023,2024,2025,2026]),
                     lambda r:r['rows'][0].__setitem__('net_driver',0)]
        for mutate in mutations:
            result = copy.deepcopy(good)
            mutate(result)
            self.assertEqual(validate_forecast(result,self.history,TARGETS)['status'],'failed')

    def test_zero_total_handling(self):
        r = build_forecast(self.history,2027,{2026:1960,2027:0},'2026-10-10')
        self.assertIsNone(r['summary']['penetration'])
        self.assertTrue(all(row['penetration'] is None for row in r['rows']))
        self.assertEqual(validate_forecast(r,self.history,{2026:1960,2027:0})['status'],'passed')

    def test_out_of_boundary_penetration_is_not_clipped(self):
        h = copy.deepcopy(self.history)
        for r in h['records']:
            if r['year']==2026: r['nev'] = r['total']*0.99
        with self.assertRaisesRegex(ForecastInputError,'超出0–100'):
            build_forecast(h,2027,TARGETS,'2026-10-10')


if __name__ == '__main__': unittest.main()
