import copy
from datetime import date
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


reader = load("experimental_realestate", PROJECT / "skills/macro-monthly-report/scripts/macro_nbs_realestate.py")
source = load("realestate_source_fixture", PROJECT / "skills/macro-monthly-report/scripts/macro_sources.py")
contract = load("realestate_contract_fixture", PROJECT / "skills/macro-monthly-report/scripts/macro_contract.py")


def requests():
    result = []
    for cid, names in (("s14-shape11", ["房地产", "制造业", "基建"]),
                       ("s17-shape15", ["商品房销售额:累计同比", "商品房销售面积:累计同比", "商品房待售面积:累计同比"])):
        chart = {"id": cid, "categories": ["2026-08"], "series": [{"name": n, "values": [None]} for n in names]}
        result.extend(contract.request_contract(chart))
    return result


def page(extra_row=""):
    html = '''<html><meta name="PublishDate" content="2026-09-15"><p>表1 2026年1—8月份全国房地产开发和销售情况</p>
    <table><tr><th>指标</th><th>绝对量</th><th>同比增长（%）</th></tr>
    <tr><td>房地产开发投资（亿元）</td><td>47979</td><td>-19.9</td></tr>
    <tr><td>其中：住宅</td><td>37017</td><td>-19.7</td></tr>
    <tr><td>新建商品房销售面积（万平方米）</td><td>49880</td><td>-12.1</td></tr>''' + extra_row + '''
    <tr><td>新建商品房销售额（亿元）</td><td>47470</td><td>-13.0</td></tr>
    <tr><td>商品房待售面积（万平方米）</td><td>75349</td><td>-1.1</td></tr></table></html>'''
    return source.parse_page(html, "https://www.stats.gov.cn/sj/zxfb/202609/t20260915_1965310.html")


class RealestatePrototypeTests(unittest.TestCase):
    def test_three_roles_only_without_stock_or_other_investment(self):
        cs = reader.reviewed_realestate_candidates(page(), requests(), "2026-10-03", "2026-09")
        self.assertEqual(len(cs), 3)
        self.assertEqual(sorted(c["value"] for c in cs), [-19.9, -13.0, -12.1])
        by_id = {r["id"]: r for r in requests()}
        for candidate in cs:
            self.assertIn("同比增长", reader.verify_realestate_table_candidate(candidate, by_id[candidate["request_id"]], page())["semantic_text"])

    def test_exact_label_not_fixed_row_number(self):
        extra = '<tr><td>二手房交易网签面积（万平方米）</td><td>54923</td><td>10.6</td></tr>'
        a = reader.reviewed_realestate_candidates(page(), requests())
        b = reader.reviewed_realestate_candidates(page(extra), requests())
        self.assertEqual({c["request_id"]: c["value"] for c in a}, {c["request_id"]: c["value"] for c in b})
        sale = next(c for c in b if "销售额" in c["request_id"])
        self.assertEqual(sale["table_proof"]["row_index"], 5)

    def test_value_or_absolute_column_or_period_tamper(self):
        req = next(r for r in requests() if r["series_name"] == "房地产")
        candidate = reader.reviewed_realestate_candidates(page(), [req])[0]
        for key, value in (("value", -19.8), ("value", True), ("period", "2026-09"), ("unit", "亿元")):
            changed = copy.deepcopy(candidate); changed[key] = value
            with self.assertRaises(ValueError): reader.verify_realestate_table_candidate(changed, req, page())
        for key, value in (("column_index", 1), ("row_index", True), ("row_index", -1)):
            changed = copy.deepcopy(candidate); changed["table_proof"][key] = value
            with self.assertRaises(ValueError): reader.verify_realestate_table_candidate(changed, req, page())

    def test_original_and_header_tamper(self):
        req = next(r for r in requests() if r["series_name"] == "房地产")
        candidate = reader.reviewed_realestate_candidates(page(), [req])[0]
        for key in ("html", "cell", "quote"):
            changed = page()
            if key == "html": changed["tables"][0]["source_html"] += "tamper"
            elif key == "cell": changed["tables"][0]["rows"][0]["cells"][2] = "环比增长（%）"
            else: changed["tables"][0]["rows"][1]["quote"] += "tamper"
            with self.assertRaises(ValueError): reader.verify_realestate_table_candidate(candidate, req, changed)

    def test_target_publication_window_and_https(self):
        self.assertEqual(reader.reviewed_realestate_candidates(page(), requests(), "2026-09-14", "2026-09"), [])
        self.assertEqual(reader.reviewed_realestate_candidates(page(), requests(), "2026-10-03", "2026-07"), [])
        changed = page(); changed["url"] = "https://regional.stats.gov.cn/a"
        self.assertEqual(reader.reviewed_realestate_candidates(changed, requests()), [])


class RealestateCoreTests(unittest.TestCase):
    def test_three_real_contract_roles_validate_and_replay(self):
        body = page()
        body["receipt_id"] = "synthetic-realestate-test"
        by_id = {r["id"]: r for r in requests()}
        candidates = source._table_candidates(body, requests())
        reviewed = [c for c in candidates if c.get("table_proof", {}).get("orientation") == reader.ORIENTATION]
        self.assertEqual(len(reviewed), 3)
        outputs = []
        for c in reviewed:
            observed = source.validate_observation(c, by_id[c["request_id"]], body, date(2026, 10, 3), "2026-09")
            self.assertEqual(observed, source.validate_observation(observed, by_id[c["request_id"]], body, date(2026, 10, 3), "2026-09"))
            outputs.append(observed)
        package = {"report_month": "2026-09", "cutoff_date": "2026-10-03", "evidence_observations": outputs}
        checked = source.verify_source_corroboration(package, {"source_requests": list(by_id.values())}, {body["receipt_id"]: body})
        self.assertEqual(checked["issues"], [])
        self.assertEqual(len(checked["observations"]), 3)

    def test_stock_is_not_cumulative_and_national_header_cannot_be_borrowed(self):
        req = next(r for r in requests() if "待售" in r["series_name"])
        self.assertEqual(reader.reviewed_realestate_candidates(page(), [req]), [])
        body = page(); body["tables"][0]["context"] = "全国房地产 " + body["tables"][0]["context"].replace("全国", "某省")
        self.assertEqual(reader.reviewed_realestate_candidates(body, requests()), [])

if __name__ == "__main__": unittest.main()
