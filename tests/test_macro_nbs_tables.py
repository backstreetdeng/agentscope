import copy
import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]/"skills/macro-monthly-report/scripts"


def load(name):
    specification=importlib.util.spec_from_file_location("nbs_test_"+name,ROOT/(name+".py"))
    module=importlib.util.module_from_spec(specification);specification.loader.exec_module(module)
    return module


tables=load("macro_nbs_tables")
source=load("macro_sources")


def page():
    raw='''<html><meta name="PublishDate" content="2026-09-15"><p>2026年8月份规模以上工业生产主要数据</p>
    <table><tr><th rowspan="2">指标</th><th colspan="2">8月</th><th colspan="2">1—8月</th></tr>
    <tr><th>绝对量</th><th>同比增长（%）</th><th>绝对量</th><th>同比增长（%）</th></tr>
    <tr><td>规模以上工业增加值</td><td>…</td><td>5.2</td><td>…</td><td>5.3</td></tr>
    <tr><td>采矿业</td><td>…</td><td>-1.4</td><td>…</td><td>2.1</td></tr>
    <tr><td>其中：高技术制造业</td><td>…</td><td>16.7</td><td>…</td><td>14.2</td></tr>
    <tr><td>钢材（万吨）</td><td>11475</td><td>-5.5</td><td>95075</td><td>-1.7</td></tr></table></html>'''
    return source.parse_page(raw,"https://www.stats.gov.cn/sj/zxfb/202609/t20260915_123.html")


def request(cumulative=False,aliases=None,cid="s13-shape17"):
    return {"id":"test", "chart_id":cid,"series_name":"累计同比" if cumulative else "当月同比",
            "definition":"工业增加值累计同比" if cumulative else "工业增加值当月同比",
            "definition_aliases":aliases or ["规模以上工业增加值"],"unit":"%","frequency":"monthly"}


class ReviewedIndustryTableTests(unittest.TestCase):
    def candidate(self,req=None,body=None):
        return tables.reviewed_nbs_candidates(body or page(),[req or request()])[0]

    def test_monthly_and_cumulative_not_swapped(self):
        monthly=self.candidate();cumulative=self.candidate(request(True))
        self.assertEqual(monthly["value"],5.2);self.assertEqual(cumulative["value"],5.3)
        self.assertEqual(monthly["period"],"2026-08")
        self.assertEqual(monthly["table_proof"]["column_index"],2)
        self.assertEqual(cumulative["table_proof"]["column_index"],4)
        self.assertIn("当月同比",tables.verify_nbs_table_candidate(monthly,request(),page())["semantic_text"])

    def test_exact_industry_row(self):
        req=request(True,["采矿业"],"s13-shape10")
        self.assertEqual(self.candidate(req)["value"],2.1)
        req=request(True,["高技术制造业"],"s13-shape10")
        self.assertEqual(self.candidate(req)["value"],14.2)

    def test_product_yoy_not_output_level(self):
        req=request(False,["钢材"],"overview")
        self.assertEqual(self.candidate(req)["value"],-5.5)
        self.assertNotIn("增加值",tables.verify_nbs_table_candidate(self.candidate(req),req,page())["semantic_text"])

    def test_industry_children_inherit_only_reviewed_parent_metric(self):
        req=request(True,["采矿业"],"s13-shape10")
        proof=tables.verify_nbs_table_candidate(self.candidate(req),req,page())
        self.assertIn("规模以上工业增加值",proof["semantic_text"])

    def test_unreviewed_chart_or_unit_not_guessed(self):
        req=request(cid="s19-shape13")
        self.assertEqual(tables.reviewed_nbs_candidates(page(),[req]),[])
        req=request();req["unit"]="亿元"
        self.assertEqual(tables.reviewed_nbs_candidates(page(),[req]),[])

    def test_regional_host_rejected(self):
        body=page();body["url"]="https://regional.stats.gov.cn/a"
        self.assertEqual(tables.reviewed_nbs_candidates(body,[request()]),[])

    def test_changed_original_html_rejected(self):
        body=page();candidate=self.candidate(body=body)
        body["tables"][0]["source_html"]+="tamper"
        with self.assertRaisesRegex(ValueError,"original_html_hash"):
            tables.verify_nbs_table_candidate(candidate,request(),body)

    def test_changed_parsed_cell_rejected(self):
        body=page();candidate=self.candidate(body=body)
        body["tables"][0]["rows"][2]["cells"][2]="999"
        with self.assertRaisesRegex(ValueError,"original_cells_changed"):
            tables.verify_nbs_table_candidate(candidate,request(),body)

    def test_model_claimed_column_cannot_override_reviewed_mapping(self):
        candidate=self.candidate();candidate["table_proof"]["column_index"]=4
        with self.assertRaisesRegex(ValueError,"metric_column_mismatch"):
            tables.verify_nbs_table_candidate(candidate,request(),page())

    def test_nonnumeric_missing_is_not_zero(self):
        body=page();req=request(aliases=["不存在的分类"])
        self.assertEqual(tables.reviewed_nbs_candidates(body,[req]),[])

    def test_changed_caption_cannot_make_source_a_new_month(self):
        candidate=self.candidate();candidate["period"]="2026-09"
        with self.assertRaisesRegex(ValueError,"not_original_cell"):
            tables.verify_nbs_table_candidate(candidate,request(),page())

    def test_negative_boolean_coordinates_rejected(self):
        for value in (-1,True,"2"):
            candidate=self.candidate();candidate["table_proof"]["row_index"]=value
            with self.assertRaisesRegex(ValueError,"coordinates_invalid"):
                tables.verify_nbs_table_candidate(candidate,request(),page())


if __name__=="__main__":unittest.main()
