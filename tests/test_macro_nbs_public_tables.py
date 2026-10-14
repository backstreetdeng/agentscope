import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / "skills/macro-monthly-report/scripts"


def load(name):
    spec = importlib.util.spec_from_file_location("public_test_" + name, ROOT / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tables = load("macro_nbs_public_tables")
sources = load("macro_sources")


def retail(body="", caption="2026年8月份社会消费品零售总额主要数据"):
    rows = '''<tr><td>社会消费品零售总额</td><td>39824</td><td>0.4</td><td>327569</td><td>1.1</td></tr>
    <tr><td>餐饮收入</td><td>4544</td><td>1.1</td><td>37366</td><td>2.4</td></tr>
    <tr><td>商品零售额</td><td>35280</td><td>0.3</td><td>290203</td><td>1.0</td></tr>
    <tr><td>其中：限额以上单位商品零售额</td><td>13504</td><td>-4.0</td><td>112427</td><td>-1.7</td></tr>
    <tr><td>其中：粮油、食品类</td><td>1802</td><td>4.0</td><td>15500</td><td>6.8</td></tr>
    <tr><td>服装、鞋帽、针纺织品类</td><td>1013</td><td>-0.5</td><td>9615</td><td>5.1</td></tr>
    <tr><td>汽车类</td><td>3279</td><td>-18.5</td><td>25805</td><td>-13.9</td></tr>'''
    html = f'''<html><meta name="PublishDate" content="2026-09-15"><p>{caption}</p>
    <table><tr><td rowspan="2">指 标</td><td colspan="2">8月</td><td colspan="2">1—8月</td></tr>
    <tr><td>绝对量（亿元）</td><td>同比增长（%）</td><td>绝对量（亿元）</td><td>同比增长（%）</td></tr>{body or rows}</table></html>'''
    return sources.parse_page(html, "https://www.stats.gov.cn/sj/zxfb/202609/example.html")


def ppi():
    html = '''<html><p>2026年8月工业生产者价格主要数据</p><table>
    <tr><td></td><td>环比涨跌幅（%）</td><td>同比涨跌幅（%）</td><td>1—8月同比涨跌幅（%）</td></tr>
    <tr><td>一、工业生产者出厂价格</td><td>0.4</td><td>3.8</td><td>2.0</td></tr>
    <tr><td>生产资料</td><td>0.4</td><td>5.0</td><td>2.9</td></tr>
    <tr><td>生活资料</td><td>0.2</td><td>-0.5</td><td>-1.1</td></tr>
    <tr><td>二、工业生产者购进价格</td><td>0.3</td><td>5.8</td><td>3.2</td></tr>
    <tr><td>生产资料</td><td>99</td><td>88</td><td>77</td></tr></table></html>'''
    return sources.parse_page(html, "https://www.stats.gov.cn/sj/zxfb/202609/example.html")


def req(name="社会消费品零售总额:当月同比(%,右轴)", cid="s15-shape9", aliases=None, unit="%"):
    return {"id": "q", "chart_id": cid, "series_name": name, "definition": "社会消费品零售总额：" + name,
            "definition_aliases": aliases or ["社会消费品零售总额"], "frequency": "monthly", "unit": unit}


class PublicNbsTableTests(unittest.TestCase):
    def candidate(self, request=None, page=None):
        return tables.reviewed_public_candidates(page or retail(), [request or req()])[0]

    def test_retail_month_ytd_and_absolute_roles(self):
        for name, unit, value, column in [
            ("社会消费品零售总额:当月值", "亿元", 39824, 1),
            ("社会消费品零售总额:当月同比(%,右轴)", "%", 0.4, 2),
            ("社会消费品零售总额:累计同比(%,右轴)", "%", 1.1, 4),
        ]:
            request = req(name, unit=unit)
            candidate = self.candidate(request)
            self.assertEqual(candidate["value"], value)
            self.assertEqual(candidate["table_proof"]["column_index"], column)
            self.assertEqual(candidate["period"], "2026-08")
            self.assertTrue(tables.verify_public_table_candidate(candidate, request, retail())["semantic_text"])

    def test_limited_scope_and_punctuation_only_alias(self):
        request = req("snapshot", "s16-shape8", ["粮油食品类"])
        candidate = self.candidate(request)
        self.assertEqual(candidate["value"], 4.0)
        semantic = tables.verify_public_table_candidate(candidate, request, retail())["semantic_text"]
        self.assertIn("限额以上单位商品零售额", semantic)

    def test_apparel_aggregate_not_clothing_only(self):
        request = req("snapshot", "s16-shape8", ["服装类"])
        self.assertEqual(tables.reviewed_public_candidates(retail(), [request]), [])

    def test_limited_parent_cannot_be_borrowed_from_full_page(self):
        body = retail()
        body["tables"][0]["source_html"] = body["tables"][0]["source_html"].replace("限额以上单位商品零售额", "全国商品零售额")
        # Reparse a genuinely different original, not only its extracted cells.
        body = sources.parse_page('<p>2026年8月份社会消费品零售总额主要数据</p>' + body["tables"][0]["source_html"], body["url"])
        self.assertEqual(tables.reviewed_public_candidates(body, [req("snapshot", "s16-shape8", ["汽车类"])]), [])

    def test_ppi_scope_yoy_mom_not_purchase_or_ytd(self):
        for name, cid, aliases, value in [("PPI同比", "s22-shape9", ["工业生产者出厂价格", "PPI"], 3.8),
                                        ("PPI环比", "s22-shape9", ["工业生产者出厂价格", "PPI"], 0.4),
                                        ("生产资料", "s22-shape10", ["生产资料"], 5.0)]:
            request = req(name, cid, aliases)
            candidates = tables.reviewed_public_candidates(ppi(), [request])
            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0]["value"], value)
            tables.verify_public_table_candidate(candidates[0], request, ppi())

    def test_wrong_month_caption_and_changed_html_rejected(self):
        self.assertEqual(tables.reviewed_public_candidates(retail(caption="2026年9月份社会消费品零售总额主要数据"), [req()]), [])
        page = retail()
        candidate = self.candidate(page=page)
        page["tables"][0]["source_html"] += "tamper"
        with self.assertRaisesRegex(ValueError, "html_hash"):
            tables.verify_public_table_candidate(candidate, req(), page)

    def test_changed_coordinates_numeric_or_request_rejected(self):
        for change in [{"value": 77}, {"request_id": "other"}, {"period": "2026-09"}, {"unit": "亿元"}]:
            candidate = self.candidate()
            candidate.update(change)
            with self.assertRaises(ValueError):
                tables.verify_public_table_candidate(candidate, req(), retail())
        for change in [{"column_index": 4}, {"row_index": True}, {"profile": "generic"}]:
            candidate = self.candidate()
            candidate["table_proof"].update(change)
            with self.assertRaises(ValueError):
                tables.verify_public_table_candidate(candidate, req(), retail())

    def test_cell_tampering_and_header_merge_change_rejected(self):
        page = retail()
        candidate = self.candidate(page=page)
        page["tables"][0]["rows"][2]["cells"][2] = "99"
        with self.assertRaisesRegex(ValueError, "cells_changed"):
            tables.verify_public_table_candidate(candidate, req(), page)
        page = retail()
        altered = page["tables"][0]["source_html"].replace('colspan="2"', 'colspan="1"')
        page = sources.parse_page('<p>2026年8月份社会消费品零售总额主要数据</p>' + altered, page["url"])
        self.assertEqual(tables.reviewed_public_candidates(page, [req()]), [])

    def test_arbitrary_semantic_text_in_row_quote_rejected(self):
        page = retail()
        candidate = self.candidate(page=page)
        page["tables"][0]["rows"][2]["quote"] += " 另一个表的同比增长99%"
        with self.assertRaisesRegex(ValueError, "row_quote_changed"):
            tables.verify_public_table_candidate(candidate, req(), page)

    def test_missing_publication_not_fabricated(self):
        page = ppi()
        request = req("PPI同比", "s22-shape9", ["工业生产者出厂价格", "PPI"])
        candidate = self.candidate(request, page)
        self.assertFalse(page["published_at"])
        self.assertNotIn("published_at", candidate)


if __name__ == "__main__":
    unittest.main()
