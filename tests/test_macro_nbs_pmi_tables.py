import copy
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import unittest

PROJECT = Path(__file__).resolve().parents[1]
SCRIPTS = PROJECT / "skills/macro-monthly-report/scripts"


def load(name):
    spec = importlib.util.spec_from_file_location("pmi_table_tests_" + name, SCRIPTS / (name + ".py"))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


reader, sources = load("macro_nbs_pmi_tables"), load("macro_sources")


def requests():
    result = [{"id": "s11-shape12::PMI", "chart_id": "s11-shape12", "series_name": "PMI",
               "definition": "制造业PMI企业规模：PMI", "definition_aliases": ["制造业采购经理指数", "制造业PMI", "PMI"],
               "unit": "指数", "frequency": "monthly", "source_domains": ["stats.gov.cn"], "history_count": 3}]
    for index, (label, _, _) in reader.CATEGORIES.items():
        result.append({"id": "s11-shape15::category" + str(index), "chart_id": "s11-shape15", "series_name": "snapshot",
                       "category_index": index, "definition": "PMI分项指数：" + label,
                       "definition_aliases": [label, label + "指数"], "unit": "指数", "frequency": "monthly",
                       "source_domains": ["stats.gov.cn"], "history_count": 3})
    return result


def original(year=2026):
    main = ('<table><tr><td colspan="7">单位：%</td></tr><tr><td rowspan="2"></td>'
            '<td rowspan="2">PMI</td><td colspan="5"></td></tr><tr>'
            + ''.join('<td>' + v + '</td>' for v in reader.TABLE_LABELS[1][2:]) + '</tr>')
    other = '<table><tr><td colspan="9">单位：%</td></tr><tr>' + ''.join('<td>' + v + '</td>' for v in reader.TABLE_LABELS[2]) + '</tr>'
    for month in (7, 8, 9):
        main += '<tr><td>' + f'{year}年{month}月' + '</td>' + ''.join('<td>' + v + '</td>' for v in ['50.1','51.7','50.5','48.2','48.4','50.1']) + '</tr>'
        other += '<tr><td>' + f'{year}年{month}月' + '</td>' + ''.join('<td>' + v + '</td>' for v in ['50.0','49.2','51.0','60.8','54.0','47.6','46.0','53.8']) + '</tr>'
    main += '</table>'; other += '</table>'
    html = (f'<html><meta name="PublishDate" content="{year}-09-30"><p>成文日期 {year}年09月30日</p>'
            '<p>国家统计局服务业调查中心</p><p>中国物流与采购联合会</p><p>一、中国制造业采购经理指数运行情况</p>'
            '<p>表1 中国制造业PMI及构成指数（经季节调整）</p>' + main
            + '<p>表2 中国制造业PMI其他相关指标情况（经季节调整）</p>' + other + '</html>')
    url = f'https://www.stats.gov.cn/xxgk/sjfb/zxfb2020/{year}09/t{year}0930_1965000.html'
    page = sources.parse_page(html, url)
    page.update(receipt_id='synthetic-pmi-original-fixture', text_sha256=sha256(page['text'].encode()).hexdigest())
    return page


def table_changed(page, table_index, old, new):
    altered = copy.deepcopy(page); table = altered['tables'][table_index]
    table['source_html'] = table['source_html'].replace(old, new)
    table['html_sha256'] = sha256(table['source_html'].encode()).hexdigest()
    return altered


class PmiTablesTests(unittest.TestCase):
    def test_main_multilevel_header_not_flat_column_mapping(self):
        page = original(); candidates = reader.reviewed_pmi_candidates(page, requests())
        self.assertEqual(len(candidates), 39)
        order = next(c for c in candidates if c['request_id'] == 's11-shape15::category1' and c['period'] == '2026-09')
        self.assertEqual(order['value'], 50.5)
        proof = order['table_proof']
        self.assertEqual((proof['row_index'], proof['column_index'], proof['header_row_index'], proof['header_column_index']), (5,3,2,1))
        self.assertEqual(proof['source_label'], '新订单')
        self.assertEqual(proof['header_spans'][1], [[2,1],[2,1],[1,5]])

    def test_all_twelve_contract_categories_and_aggregate_three_months(self):
        page = original(); qs = requests(); candidates = reader.reviewed_pmi_candidates(page, qs)
        self.assertEqual({c['request_id'] for c in candidates}, {q['id'] for q in qs})
        expected = {0:51.7,1:50.5,2:50.0,3:46.0,4:47.6,5:51.0,6:49.2,7:60.8,8:48.2,9:48.4,10:50.1,11:53.8}
        for candidate in candidates:
            request = next(q for q in qs if q['id'] == candidate['request_id'])
            verified = reader.verify_pmi_table_candidate(candidate, request, page, '2026-10-03', '2026-09')
            self.assertTrue(verified['reviewed_period_and_definition'])
            if 'category_index' in request: self.assertEqual(candidate['value'], expected[request['category_index']])
            else: self.assertEqual(candidate['value'], 50.1)
            self.assertEqual(candidate['unit'], '指数')

    def test_prior_generic_pmi_column_cannot_impersonate_new_order(self):
        page = original(); q = next(q for q in requests() if q['id'] == 's11-shape15::category1')
        candidate = reader.reviewed_pmi_candidates(page, [q])[-1]
        forged = copy.deepcopy(candidate); forged.update(value=50.1, value_text='50.1')
        forged['table_proof'].update(column_index=1, expanded_column_index=1, header_row_index=1, header_column_index=1,
                                    source_label='PMI', header_cell_quote='PMI')
        with self.assertRaisesRegex(ValueError, 'exact_original_role_cell'):
            reader.verify_pmi_table_candidate(forged, q, page)

    def test_other_table_headers_cannot_swap_exports_imports_orders_or_factory_price(self):
        page = original(); candidates = reader.reviewed_pmi_candidates(page, requests())
        candidate = next(c for c in candidates if c['request_id'] == 's11-shape15::category2')
        q = next(q for q in requests() if q['id'] == candidate['request_id'])
        forged = copy.deepcopy(candidate); forged.update(value=49.2, value_text='49.2')
        forged['table_proof'].update(column_index=2, expanded_column_index=2, header_column_index=2,
                                    source_label='进口', header_cell_quote='进口')
        with self.assertRaises(ValueError): reader.verify_pmi_table_candidate(forged,q,page)
        self.assertEqual(reader.reviewed_pmi_candidates(page, [{**q, 'definition_aliases':['出厂价格','出厂价格指数']}]), [])

    def test_original_header_rows_spans_and_caption_must_be_replayed(self):
        page = original(); q = requests()[0]; c = reader.reviewed_pmi_candidates(page,[q])[0]
        for altered in [table_changed(page,0,'rowspan="2"','rowspan="1"'), table_changed(page,0,'colspan="5"','colspan="4"'),
                        table_changed(page,0,'>PMI<','>新订单<')]:
            with self.assertRaises(ValueError): reader.verify_pmi_table_candidate(c,q,altered)
        altered = copy.deepcopy(page); altered['tables'][0]['context'] = '表3 中国非制造业主要分类指数（经季节调整）'
        with self.assertRaises(ValueError): reader.verify_pmi_table_candidate(c,q,altered)

    def test_raw_html_cell_hash_row_quote_period_and_index_not_trusted(self):
        page=original();q=requests()[0];c=reader.reviewed_pmi_candidates(page,[q])[0]
        for key,value in [('html_sha256','fake'),('source_html','<table>fake</table>')]:
            altered=copy.deepcopy(page);altered['tables'][0][key]=value
            with self.assertRaises(ValueError):reader.verify_pmi_table_candidate(c,q,altered)
        for key,value in [('cells',['2026年7月','99.9']),('quote','|2026年7月|99.9'),('row_index',True)]:
            altered=copy.deepcopy(page);altered['tables'][0]['rows'][3][key]=value
            with self.assertRaises(ValueError):reader.verify_pmi_table_candidate(c,q,altered)

    def test_candidate_coordinates_value_period_definition_and_metadata_not_forged(self):
        page=original();q=requests()[0];c=reader.reviewed_pmi_candidates(page,[q])[0]
        for change in ({'value':True},{'value':float('nan')},{'period':'2026-09'},{'value':49.0},{'unit':'%'},
                       {'source_url':'https://evil.test/'},{'published_at':'2026-10-01'},{'observation_kind':'forecast'}):
            with self.assertRaises(ValueError): reader.verify_pmi_table_candidate({**c,**change},q,page)
        for change in ({'column_index':True},{'row_index':0},{'profile':'generic'},{'header_column_index':0},{'period_column_index':1}):
            forged=copy.deepcopy(c);forged['table_proof'].update(change)
            with self.assertRaises(ValueError):reader.verify_pmi_table_candidate(forged,q,page)

    def test_future_cutoff_target_and_source_publisher_guards(self):
        page=original();qs=requests()
        self.assertEqual(reader.reviewed_pmi_candidates(page,qs,'2026-09-29'),[])
        candidates=reader.reviewed_pmi_candidates(page,qs,report_month='2026-08')
        self.assertEqual(len(candidates),26)
        self.assertEqual({c['period'] for c in candidates},{'2026-07','2026-08'})
        for changed in ({'text_sha256':'fake'},{'truncated':True},{'url':'https://evil.test/pmi.html'}, {'published_at':'2026-09-29'}):
            self.assertEqual(reader.reviewed_pmi_candidates({**page,**changed},qs),[])

    def test_whitelist_frequency_id_category_and_alias_exact(self):
        page=original();qs=requests()
        for q in qs:
            for changed in ({'frequency':'annual'},{'unit':'%'},{'id':'not-registered'},{'definition':'非制造业PMI'},
                            {'source_domains':['wind.com']},{'definition_aliases':['制造业']}):
                self.assertEqual(reader.reviewed_pmi_candidates(page,[{**q,**changed}]),[])
        self.assertEqual(reader.reviewed_pmi_candidates(page,[{**qs[1],'category_index':True}]),[])

    def test_explicit_actual_row_year_not_fixed_or_inferred_from_url(self):
        page=original(2027);candidates=reader.reviewed_pmi_candidates(page,requests(),'2027-10-03','2027-09')
        self.assertEqual(len(candidates),39)
        self.assertEqual({c['period'] for c in candidates},{'2027-07','2027-08','2027-09'})

    def test_real_latest_vintage_and_cold_original_replay(self):
        cache=PROJECT/'.work/macro-public-run/codex-run-v3/working/macro-sources/pages'
        contract=PROJECT/'runtime/skill-runs/macro-20261004-005541-c8ad8701/working/template-contract.json'
        if not cache.exists() or not contract.exists(): self.skipTest('Real official cached pages and contract required')
        qs=json.loads(contract.read_text(encoding='utf-8'))['source_requests']
        files=['fac43ff52cb70db246b2052bfd56881bdb930b7a1369da6ceff7fd299e254ae7',
               '9675e5d6a8698cd2df2f97946bd61ccb315fbb6b67f01fc46b21c584d593ad4d',
               '0a74d2361229b9356f96a08f14597346d41d0e2441211894391b05d94865c9fb',
               '919720249014019ecd6a5aac600c585b2b517d7db4ba38dee73172d87a24f9df']
        replayed=0
        for stem in files:
            page=json.loads((cache/(stem+'.json')).read_text(encoding='utf-8'))
            candidates=reader.reviewed_pmi_candidates(page,qs,'2026-10-03','2026-09')
            self.assertEqual(len(candidates),39)
            for candidate in candidates:
                q=next(q for q in qs if q['id']==candidate['request_id'])
                reader.verify_pmi_table_candidate(candidate,q,page,'2026-10-03','2026-09');replayed+=1
            current={c['request_id']:c for c in candidates if c['period']==page['published_at'][:7]}
            self.assertEqual(current['s11-shape15::category1']['table_proof']['column_index'],3)
            self.assertNotEqual(current['s11-shape15::category1']['value'],current['s11-shape12::PMI']['value'])
        self.assertEqual(replayed,156)
        cold=PROJECT/'.work/macro-public-run/source-subset-cold/20261004-093246/working/macro-sources/pages'
        if cold.exists():
            hits=0
            for path in cold.glob('*.json'):
                page=json.loads(path.read_text(encoding='utf-8'))
                candidates=reader.reviewed_pmi_candidates(page,qs,'2026-10-03','2026-09')
                for candidate in candidates:
                    reader.verify_pmi_table_candidate(candidate,next(q for q in qs if q['id']==candidate['request_id']),page,'2026-10-03','2026-09');hits+=1
            self.assertGreaterEqual(hits,117)


if __name__=='__main__': unittest.main()
