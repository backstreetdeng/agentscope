from datetime import date
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

PATH = Path(__file__).resolve().parents[1] / 'skills/macro-monthly-report/scripts/macro_official_discovery.py'
SPEC = importlib.util.spec_from_file_location('macro_official_discovery_tests', PATH)
discovery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(discovery)


def investment_amount_request():
    return {"id": "s14-shape15::固定资产投资累计值", "chart_id": "s14-shape15",
            "series_name": "固定资产投资累计值", "definition_aliases": ["固定资产投资"],
            "frequency": "monthly", "unit": "亿元", "source_domains": ["stats.gov.cn"]}


class DirectoryParserTests(unittest.TestCase):
    def test_relative_link_title_and_actual_directory_date(self):
        raw = '<ul><li><a href="202608/t20260814_3995497.htm">2026年1-7月财政收支情况</a> 2026-08-21</li></ul>'
        item = discovery.extract_directory_links(raw, 'https://gks.mof.gov.cn/tongjishuju/', '2026-10-03')[0]
        self.assertEqual(item['url'], 'https://gks.mof.gov.cn/tongjishuju/202608/t20260814_3995497.htm')
        self.assertEqual(item['published_at'], '2026-08-21')
        self.assertEqual(item['publication_date_basis'], 'directory_label')
        self.assertTrue(item['discovery_only'])
        self.assertNotIn('value', item)

    def test_future_and_unsafe_urls_rejected(self):
        raw = '<li><a href="https://evil.test/a">居民消费价格</a>2026-09-09</li><li><a href="javascript:alert(1)">Bad</a></li><li><a href="https://www.stats.gov.cn/a">future</a>2026-10-09</li><li><a href="https://u:p@www.stats.gov.cn/a">credential URL</a></li>'
        self.assertEqual(discovery.extract_directory_links(raw, 'https://www.stats.gov.cn/', '2026-10-03'), [])

    def test_url_day_only_is_hint_not_observation_proof(self):
        raw = '<a href="202609/t20260915_111.html">2026年8月份工业增加值</a>'
        item = discovery.extract_directory_links(raw, 'https://www.stats.gov.cn/sj/zxfb/', date(2026, 10, 3))[0]
        self.assertEqual(item['published_at'], '2026-09-15')
        self.assertEqual(item['publication_date_basis'], 'publisher_url_date_discovery_hint')
        self.assertEqual(item['directory_date_quote'], '')

    def test_does_not_borrow_next_articles_publication_date(self):
        raw = '<li><a href="a.html">No date</a></li><li><a href="b.html">Other</a>2026-09-15</li>'
        items = discovery.extract_directory_links(raw, 'https://www.stats.gov.cn/', '2026-10-03')
        self.assertEqual(items[0]['published_at'], '')
        self.assertEqual(items[1]['published_at'], '2026-09-15')

    def test_year_agnostic_and_attachment_flag(self):
        raw = '<a href="attachDir/2027/09/2027091512330000000.xls">2027年统计数据 Excel</a>'
        item = discovery.extract_directory_links(raw, 'https://www.pbc.gov.cn/diaochatongjisi/', '2027-10-03')[0]
        self.assertTrue(item['attachment'])
        self.assertTrue(item['discovery_only'])
        self.assertIn('/2027/', item['url'])

    def test_reviewed_http_href_upgraded_without_insecure_fetch(self):
        raw = '<li><a href="http://gks.mof.gov.cn/tongjishuju/202609/t20260918_1.htm">2026年1-8月财政收支情况</a>2026-09-18</li>'
        item = discovery.extract_directory_links(raw, 'https://www.mof.gov.cn/', '2026-10-03')[0]
        self.assertTrue(item['transport_upgraded_to_https'])
        self.assertTrue(item['url'].startswith('https://gks.mof.gov.cn/'))
        self.assertTrue(item['original_href'].startswith('http://'))

    def test_nbs_directory_date_beyond_whitespace_in_same_list_item(self):
        raw = '<li><a href="t20260814_1.html">Release</a>\n <span>2026-08-21</span></li><li>2026-10-20</li>'
        item = discovery.extract_directory_links(raw, 'https://www.stats.gov.cn/', '2026-10-03')[0]
        self.assertEqual(item['published_at'], '2026-08-21')
        self.assertEqual(item['publication_date_basis'], 'directory_label')

    def test_pbc_attachment_row_context_and_url_day_are_discovery_hints(self):
        raw = '<tr><td><div>社会融资规模增量统计表<br>Flow</div></td><td><a href="/diaochatongjisi/attachDir/2026/09/2026091417323857622.htm">htm</a></td><td><a href="/diaochatongjisi/attachDir/2026/09/2026091418125322850.xlsx">xls</a></td></tr>'
        items = discovery.extract_directory_links(raw, 'https://www.pbc.gov.cn/', '2026-10-03')
        self.assertTrue(items[0]['statistical_document'])
        self.assertFalse(items[0]['attachment'])
        self.assertIn('社会融资规模增量统计表',items[1]['table_context_quote'])
        self.assertEqual(items[0]['published_at'],'2026-09-14')
        self.assertEqual(items[0]['publication_date_basis'],'publisher_url_date_discovery_hint')

    def test_gdp_subset_and_finance_regions_excluded(self):
        self.assertFalse(discovery._matches({'url':'https://www.stats.gov.cn/a','title':'2025年三新经济增加值占国内生产总值比重'},'nbs_gdp'))
        self.assertFalse(discovery._matches({'url':'https://www.pbc.gov.cn/a','title':'2026年上半年地区社会融资规模增量统计表'},'pbc_finance'))

    def test_distinct_months_precede_same_month_commentaries(self):
        items=[{'url':f'https://www.stats.gov.cn/{n}','title':title,'published_at':day} for n,title,day in [(1,'2026年8月份工业增加值','2026-09-15'),(2,'2026年8月工业生产数据解读','2026-09-15'),(3,'2026年7月份工业增加值','2026-08-17'),(4,'2026年6月份工业增加值','2026-07-15')]]
        result=discovery._diversify(items,'nbs_industry')
        self.assertEqual([item['discovery_period_hint'] for item in result[:3]],['2026-08','2026-07','2026-06'])

    def test_yearless_quarter_title_has_only_directory_period_hint(self):
        self.assertEqual(discovery._period_hint({'title':'郑学工：上半年经济运行在合理区间','published_at':'2026-07-16'}),'2026-Q2')
        self.assertEqual(discovery._period_hint({'title':'全年经济运行解读','published_at':'2027-01-20'}),'2026-Q4')
        self.assertEqual(discovery._period_hint({'title':'工业生产解读','published_at':'2026-07-16'}),'')

    def test_pbc_literal_pagination_attribute_parsed_without_script(self):
        raw="<a tagname='/goutongjiaoliu/113456/113469/11040-2.html' onclick=\"queryArticleByCondition(this,'/goutongjiaoliu/113456/113469/11040-2.html')\">下一页</a><a tagname='/evil' onclick=\"someOtherFunction('/evil')\">Bad</a>"
        result=discovery.extract_directory_links(raw,'https://www.pbc.gov.cn/goutongjiaoliu/113456/113469/index.html','2026-10-03')
        self.assertEqual(len(result),1)
        self.assertTrue(result[0]['url'].endswith('11040-2.html'))

    def test_pbc_original_tables_route_by_exact_caption_and_series(self):
        captions=['社会融资规模增量统计表','社会融资规模存量统计表','货币供应量','金融机构人民币信贷收支表','存款类金融机构人民币信贷收支表']
        docs=[{'url':f'https://www.pbc.gov.cn/diaochatongjisi/attachDir/2027/09/{n}.htm','title':'htm','published_at':'2027-09-14','attachment':False,'statistical_document':True,'table_context_quote':caption+' htm xls pdf'} for n,caption in enumerate(captions)]
        docs.append(dict(docs[0],url='https://www.pbc.gov.cn/1.xlsx',attachment=True))
        for cid,definition,caption in [('s25-shape9','社会融资规模增量',captions[0]),('s26-shape12','社会融资规模存量:同比',captions[1]),('s26-shape12','M2:同比',captions[2]),('s24-shape17','住户短期贷款',captions[3])]:
            items=discovery._pbc_html_tables({'chart_id':cid,'definition':definition},docs)
            self.assertEqual(len(items),1)
            self.assertTrue(items[0]['title'].startswith(caption+' '))
            self.assertFalse(items[0]['attachment'])
            self.assertEqual(items[0]['original_anchor_title'],'htm')
            self.assertNotIn('observations',items[0])

    def test_foreign_pmi_not_routed_to_china(self):
        request = {'id':'s4-shape10::美国','chart_id':'s4-shape10','source_domains':['ismworld.org']}
        self.assertEqual(discovery._family(request), '')

    def test_only_total_investment_amount_routes_to_main_indicators_appendix(self):
        request = investment_amount_request()
        self.assertEqual(discovery._family(request), 'nbs_macro_investment')
        for change in [{'series_name':'民间固定资产投资累计值'}, {'unit':'%'},
                       {'frequency':'quarterly'}, {'definition_aliases':['制造业投资']},
                       {'source_domains':['wind.com.cn']}]:
            self.assertNotEqual(discovery._family(dict(request, **change)), 'nbs_macro_investment')

    def test_macro_investment_yearless_month_halfyear_and_year_boundary_hints(self):
        cases = [
            ('8月份国民经济运行平稳、发展向新向优', '2026-09-15', '2026-08'),
            ('1—7月份国民经济保持总体平稳、向新向优发展态势', '2027-08-17', '2027-07'),
            ('上半年经济运行在合理区间 新动能快速成长', '2026-07-15', '2026-06'),
            ('2027年前三季度国民经济保持平稳运行', '2027-10-15', '2027-09'),
            ('全年国民经济平稳增长', '2027-01-20', '2026-12'),
            ('10月份国民经济保持平稳', '2026-09-15', ''),
            ('8月份国民经济保持平稳', '', ''),
        ]
        for title, published, expected in cases:
            item={'url':'https://www.stats.gov.cn/release.html','title':title,'published_at':published}
            self.assertEqual(discovery._period_hint(item, 'nbs_macro_investment'), expected)

    def test_macro_investment_release_not_interview_or_commentary(self):
        def item(title):
            return {'url':'https://www.stats.gov.cn/release.html','title':title,'published_at':'2026-09-15'}
        self.assertTrue(discovery._matches(item('8月份国民经济运行平稳、发展向新向优'),'nbs_macro_investment'))
        self.assertTrue(discovery._matches(item('上半年经济运行在合理区间 新动能快速成长'),'nbs_macro_investment'))
        for title in ['国家统计局副局长就2026年上半年国民经济运行情况答记者问',
                      '8月份国民经济运行情况解读', '郑学工：8月份国民经济运行情况',
                      '2026年8月份固定资产投资数据', '8月份企业经济运行情况答记者问']:
            self.assertFalse(discovery._matches(item(title),'nbs_macro_investment'))

    def test_macro_investment_saved_original_directory_anchors_cover_three_months(self):
        root = PATH.parents[3] / '.work/macro-public-run/directory-receipts'
        if not root.exists():
            self.skipTest('Original official-directory receipts are required for local replay')
        items=[]
        for file in root.glob('*.json'):
            page=json.loads(file.read_text(encoding='utf-8'))
            if 'stats.gov.cn/xxgk/sjfb/zxfb2020/' not in page.get('url',''):
                continue
            items += discovery.extract_directory_links(page['raw_html'],page['url'],'2026-10-03')
        matching=[i for i in items if discovery._matches(i,'nbs_macro_investment')]
        result=discovery._diversify(matching,'nbs_macro_investment')
        self.assertEqual([i['discovery_period_hint'] for i in result],['2026-08','2026-07','2026-06'])
        self.assertEqual([i['published_at'] for i in result],['2026-09-15','2026-08-17','2026-07-15'])
        self.assertEqual([i['url'].rsplit('/',1)[-1] for i in result],
                         ['t20260915_1965307.html','t20260817_1965056.html','t20260715_1964121.html'])
        self.assertTrue(all(i['discovery_only'] and i['publication_date_basis']=='directory_label' for i in result))
        self.assertTrue(all('value' not in i and 'observations' not in i for i in result))

    def test_national_annual_bulletin_exact_title_path_and_explicit_q4_year(self):
        item={'url':'https://www.stats.gov.cn/xxgk/sjfb/tjgb2020/202802/t20280228_1000001.html',
              'title':'中华人民共和国2027年国民经济和社会发展统计公报',
              'published_at':'2028-02-28',
              'directory_url':'https://www.stats.gov.cn/xxgk/sjfb/tjgb2020/index.html'}
        self.assertTrue(discovery._matches(item,'nbs_gdp_demand'))
        self.assertEqual(discovery._period_hint(item,'nbs_gdp_demand'),'2027-Q4')
        self.assertFalse(discovery._matches(item,'nbs_gdp'))
        for change in [
            {'title':'某省2027年国民经济和社会发展统计公报'},
            {'title':'中华人民共和国2027年全国科技经费投入统计公报'},
            {'title':item['title']+'解读'},
            {'url':'https://www.stats.gov.cn/xxgk/sjfb/zxfb2020/202802/t20280228_1000001.html'},
            {'directory_url':'https://evil.test/tjgb2020/index.html'},
        ]:
            self.assertFalse(discovery._matches(dict(item,**change),'nbs_gdp_demand'))

    def test_gdp_demand_annual_bulletin_prioritized_in_same_four_quarters(self):
        items=[
            {'url':'https://www.stats.gov.cn/q2','title':'郑学工：上半年经济运行在合理区间','published_at':'2026-07-16'},
            {'url':'https://www.stats.gov.cn/q1','title':'郑学工：一季度经济运行开局良好','published_at':'2026-04-17'},
            {'url':'https://www.stats.gov.cn/q4comment','title':'郑学工：全年经济运行稳中有进','published_at':'2026-01-20'},
            {'url':'https://www.stats.gov.cn/q3','title':'郑学工：前三季度国民经济运行保持总体平稳','published_at':'2025-10-20'},
            {'url':'https://www.stats.gov.cn/month','title':'郑学工：8月份经济运行保持平稳','published_at':'2026-09-16'},
        ]
        annual={'url':'https://www.stats.gov.cn/xxgk/sjfb/tjgb2020/202602/t20260228_1000001.html',
                'title':'中华人民共和国2025年国民经济和社会发展统计公报','published_at':'2026-02-28',
                'directory_url':'https://www.stats.gov.cn/xxgk/sjfb/tjgb2020/index.html'}
        # A republished older bulletin cannot crowd out Q1/Q2.
        older=dict(annual,url=annual['url'].replace('1000001','1000002'),
                   title='中华人民共和国2024年国民经济和社会发展统计公报',published_at='2026-09-25')
        result=discovery._diversify(items+[annual,older],'nbs_gdp_demand')
        self.assertEqual([i['discovery_period_hint'] for i in result],['2026-Q2','2026-Q1','2025-Q4','2025-Q3'])
        self.assertEqual(result[2]['url'],annual['url'])
        self.assertTrue(all('value' not in i for i in result))

    def test_annual_directory_added_only_for_gdp_demand(self):
        annual='https://www.stats.gov.cn/xxgk/sjfb/tjgb2020/index.html'
        self.assertIn(annual,discovery._directory_urls({'nbs_gdp_demand'},2026))
        self.assertEqual(len(discovery._directory_urls({'nbs_gdp_demand'},2026)),40)
        for families in [{'nbs_gdp'},{'nbs_investment'},{'nbs_macro_investment'},{'nbs_industry'}]:
            self.assertNotIn(annual,discovery._directory_urls(families,2026))


class DiscoveryPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_annual_directory_literal_anchor_backfills_gdp_q4(self):
        annual='https://www.stats.gov.cn/xxgk/sjfb/tjgb2020/index.html'
        annual_html='''<li><a href="./202602/t20260228_1000001.html">中华人民共和国2025年国民经济和社会发展统计公报</a>2026-02-28</li>
        <li><a href="./202702/t20270228_1000002.html">中华人民共和国2026年国民经济和社会发展统计公报</a>2027-02-28</li>'''
        quarters_html='''<li><a href="./202607/t20260716_1.html">郑学工：上半年经济运行在合理区间</a>2026-07-16</li>
        <li><a href="./202604/t20260417_2.html">郑学工：一季度经济运行开局良好</a>2026-04-17</li>
        <li><a href="./202601/t20260120_3.html">郑学工：全年经济运行稳中有进</a>2026-01-20</li>
        <li><a href="./202510/t20251020_4.html">郑学工：前三季度国民经济运行保持总体平稳</a>2025-10-20</li>'''
        async def fake(url):
            return {'url':url,'requested_url':url,'raw_html':annual_html if url==annual else quarters_html,
                    'raw_sha256':'x','fetched_at':'2026-10-03T00:00:00Z','fetch_provider':'mocked-unit-test'}
        request={'id':'demand','chart_id':'s10-shape28'}
        with patch.object(discovery,'_fetch_directory',side_effect=fake) as fetch:
            result=await discovery.discover_official_sources([request],'2026-09','2026-10-03')
        self.assertEqual(fetch.call_count,40)
        items=result['by_request']['demand']['items']
        self.assertEqual([i['discovery_period_hint'] for i in items],['2026-Q2','2026-Q1','2025-Q4','2025-Q3'])
        self.assertIn('/tjgb2020/',items[2]['url'])
        self.assertEqual(items[2]['original_href'],'./202602/t20260228_1000001.html')
        self.assertEqual(items[2]['published_at'],'2026-02-28')
        self.assertEqual(items[2]['publication_date_basis'],'directory_label')
        self.assertTrue(all(i['discovery_only'] and 'value' not in i and 'observations' not in i for i in items))

    async def test_investment_amount_pipeline_preserves_three_months_and_cutoff(self):
        raw = ''.join(f'<li><a href="2026{month+1:02}/t2026{month+1:02}15_{month}.html">{title}</a>2026-{month+1:02}-15</li>'
                      for month,title in [(6,'上半年经济运行在合理区间'),
                                          (7,'1—7月份国民经济保持总体平稳'),
                                          (8,'8月份国民经济运行平稳'),
                                          (9,'前三季度国民经济保持平稳')])
        raw += '<li><a href="202609/t20260916_1.html">8月份国民经济运行情况解读</a>2026-09-16</li>'
        async def fake(url):
            return {'url':url,'requested_url':url,'raw_html':raw,'raw_sha256':'x',
                    'fetched_at':'2026-10-03T00:00:00Z','fetch_provider':'mocked-unit-test'}
        request=investment_amount_request()
        with patch.object(discovery,'_fetch_directory',side_effect=fake):
            result=await discovery.discover_official_sources([request],'2026-09','2026-10-03')
            items=result['by_request'][request['id']]['items']
            self.assertEqual(result['by_request'][request['id']]['family'],'nbs_macro_investment')
            self.assertEqual([i['discovery_period_hint'] for i in items],['2026-08','2026-07','2026-06'])
            self.assertTrue(all(i['publication_date_basis']=='directory_label' for i in items))
            self.assertTrue(all(i['discovery_only'] for i in items))
            historical=await discovery.discover_official_sources([request],'2026-07','2026-10-03')
            self.assertEqual([i['discovery_period_hint'] for i in historical['by_request'][request['id']]['items']],
                             ['2026-07','2026-06'])

    async def test_shared_directory_discovery_returns_three_months_and_receipts(self):
        raw = ''.join(f'<li><a href="2026{month+1:02}/t2026{month+1:02}15_{month}.html">2026年{month}月份工业增加值</a>2026-{month+1:02}-15</li>' for month in [6,7,8])
        async def fake(url):
            return {'url':url,'requested_url':url,'raw_html':raw,'raw_sha256':'x','fetched_at':'2026-10-03T00:00:00Z','fetch_provider':'mocked-unit-test'}
        requests = [{'id':'A','chart_id':'s13-shape17'},{'id':'B','chart_id':'s13-shape10'}]
        with TemporaryDirectory() as temporary, patch.object(discovery, '_fetch_directory', side_effect=fake) as fetch:
            result = await discovery.discover_official_sources(requests,'2026-09','2026-10-03',temporary)
            self.assertEqual(len(result['by_request']['A']['items']), 3)
            self.assertEqual(result['by_request']['A']['items'], result['by_request']['B']['items'])
            self.assertEqual(fetch.call_count, 12)
            self.assertTrue(all(Path(item['evidence_path']).is_file() for item in result['directories']))
            self.assertTrue(result['discovery_only'])
            self.assertFalse(any('observations' in item for item in result['by_request'].values()))

    async def test_directory_failure_stays_explicit_and_never_bypasses_tls(self):
        request = {'id':'fiscal','chart_id':'s30-shape13'}
        with patch.object(discovery,'_fetch_directory', new=AsyncMock(side_effect=ValueError('TLS verification failed'))):
            result = await discovery.discover_official_sources([request], '2026-09', '2026-10-03')
        self.assertEqual(result['directories'][0]['status'], 'retrieval_failed')
        self.assertEqual(result['by_request']['fiscal']['items'], [])
        self.assertNotIn('observations',result)

    async def test_unknown_unsupported_source_family_not_silently_substituted(self):
        request = {'id':'oil','chart_id':'s8-shape11'}
        with patch.object(discovery,'_fetch_directory', new=AsyncMock()) as fetch:
            result = await discovery.discover_official_sources([request], '2026-09', '2026-10-03')
        fetch.assert_not_called()
        self.assertEqual(result['by_request']['oil']['issues'][0]['code'], 'directory_family_not_supported')

    async def test_pbc_annual_pdf_locators_not_observations(self):
        raw = '<a href="/diaochatongjisi/attachDir/2026/09/2026091417000000000.pdf">PDF</a>'
        async def fake(url):
            return {'url':url,'requested_url':url,'raw_html':raw,'raw_sha256':'x','fetched_at':'2026-10-03T00:00:00Z','fetch_provider':'mocked-unit-test'}
        with patch.object(discovery,'_fetch_directory',side_effect=fake):
            result = await discovery.discover_official_sources([{'id':'loan','chart_id':'s24-shape9'}], '2026-09', '2026-10-03')
        self.assertEqual(len(result['pbc_attachment_candidates']),1)
        self.assertTrue(result['pbc_attachment_candidates'][0]['attachment'])
        self.assertEqual(result['by_request']['loan']['items'],[])

    async def test_pbc_follows_only_reviewed_category_anchor(self):
        annual='https://www.pbc.gov.cn/diaochatongjisi/116219/116319/2027ntjsj/index.html'
        child='https://www.pbc.gov.cn/diaochatongjisi/116219/116319/2027ntjsj/shrzgm/index.html'
        async def fake(url):
            raw='<a href="shrzgm/index.html">社会融资规模</a><a href="evil/index.html">other</a>' if url==annual else '<tr><td>社会融资规模增量统计表</td><td><a href="/diaochatongjisi/attachDir/2027/09/2027091418000000000.xlsx">xls</a></td></tr>' if url==child else ''
            return {'url':url,'requested_url':url,'raw_html':raw,'raw_sha256':'x','fetched_at':'2027-10-03T00:00:00Z','fetch_provider':'mocked-unit-test'}
        with patch.object(discovery,'_fetch_directory',side_effect=fake) as fetch:
            result=await discovery.discover_official_sources([{'id':'loan','chart_id':'s24-shape9'}],'2027-09','2027-10-03')
        self.assertEqual(fetch.call_count,3)
        self.assertEqual(len(result['pbc_attachment_candidates']),1)
        self.assertIn('社会融资规模增量统计表',result['pbc_attachment_candidates'][0]['table_context_quote'])

    async def test_transient_timeout_retried_but_tls_failure_not_retried(self):
        request={'id':'fiscal','chart_id':'s30-shape13'}
        page={'url':'https://www.mof.gov.cn/','requested_url':'https://www.mof.gov.cn/','raw_html':'','raw_sha256':'x','fetched_at':'x','fetch_provider':'mock'}
        with patch.object(discovery,'_fetch_directory',new=AsyncMock(side_effect=[TimeoutError('timeout'),page])) as fetch:
            result=await discovery.discover_official_sources([request],'2027-09','2027-10-03')
        self.assertEqual(fetch.call_count,2)
        self.assertEqual(result['directories'][0]['status'],'retrieved')
        with patch.object(discovery,'_fetch_directory',new=AsyncMock(side_effect=ValueError('certificate verify failed'))) as fetch:
            result=await discovery.discover_official_sources([request],'2027-09','2027-10-03')
        self.assertEqual(fetch.call_count,1)


if __name__ == '__main__':
    unittest.main()
