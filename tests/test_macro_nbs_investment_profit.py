import copy
import importlib.util
import json
from pathlib import Path
import unittest

PROJECT = Path(__file__).resolve().parents[1]
SCRIPTS = PROJECT / "skills/macro-monthly-report/scripts"


def load(name):
    spec = importlib.util.spec_from_file_location("investment_profit_test_" + name, SCRIPTS / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reader = load("macro_nbs_investment_profit")
sources = load("macro_sources")


def requests():
    result = []
    for (cid, name), (aliases, unit, kind) in reader.ROLES.items():
        definition = name if kind == "total_level" else "累计同比：" + name
        result.append({"id": cid + "::" + name, "chart_id": cid, "series_name": name,
                       "definition": definition, "definition_aliases": sorted(aliases),
                       "unit": unit, "frequency": "monthly"})
    return result


def request(kind):
    return next(r for r in requests() if reader.ROLES[(r["chart_id"], r["series_name"])][2] == kind)


def parse(caption, body, published="2026-09-15"):
    html = f'<html><meta name="PublishDate" content="{published}"><p>{caption}</p>{body}</html>'
    return sources.parse_page(html, "https://www.stats.gov.cn/xxgk/sjfb/zxfb2020/202609/fixture.html")


def investment(body=None):
    return parse("2026年1—8月份固定资产投资（不含农户）主要数据", body or """<table>
    <tr><th>指 标</th><th>同比增长（%）</th></tr>
    <tr><td>固定资产投资（不含农户）</td><td>-7.2</td></tr>
    <tr><td>其中：国有控股</td><td>-3.6</td></tr>
    <tr><td>其中：民间投资</td><td>-10.1</td></tr>
    <tr><td>按构成分</td><td></td></tr>
    <tr><td>建筑安装工程</td><td>-9.8</td></tr>
    <tr><td>分产业</td><td></td></tr>
    <tr><td>第二产业</td><td>-2.9</td></tr>
    <tr><td>分行业</td><td></td></tr>
    <tr><td>采矿业</td><td>3.4</td></tr>
    <tr><td>制造业</td><td>-2.3</td></tr>
    <tr><td>汽车制造业</td><td>-6.0</td></tr>
    <tr><td>分登记注册统计类别</td><td></td></tr>
    <tr><td>其中：内资企业</td><td>-7.1</td></tr></table>""")


def macro():
    return parse("2026年1—8月份主要指标数据", """<table>
    <tr><td rowspan="2">指 标</td><td colspan="2">8月</td><td colspan="2">1—8月</td></tr>
    <tr><td>绝对量</td><td>同比增长（%）</td><td>绝对量</td><td>同比增长（%）</td></tr>
    <tr><td>三、固定资产投资（不含农户）（亿元）</td><td>…</td><td>…</td><td>293092</td><td>-7.2</td></tr>
    <tr><td>民间投资</td><td>…</td><td>…</td><td>99999</td><td>-10.1</td></tr></table>""")


def profit():
    return parse("表3　2026年1-8月份规模以上工业企业主要财务指标（分行业）", """<table>
    <tr><td rowspan="3">行 业</td><td colspan="2">营业收入</td><td colspan="2">营业成本</td><td colspan="2">利润总额</td></tr>
    <tr><td>金额</td><td>同比增长</td><td>金额</td><td>同比增长</td><td>金额</td><td>同比增长</td></tr>
    <tr><td>(亿元)</td><td>(%)</td><td>(亿元)</td><td>(%)</td><td>(亿元)</td><td>(%)</td></tr>
    <tr><td>总计</td><td>10000</td><td>6.5</td><td>9000</td><td>5.9</td><td>1000</td><td>18.7</td></tr>
    <tr><td>汽车制造业</td><td>51893.2</td><td>2.9</td><td>46100.3</td><td>2.8</td><td>1953.5</td><td>-16.0</td></tr></table>""")


class NbsInvestmentProfitTests(unittest.TestCase):
    def candidate(self, kind, page=None):
        page = page or (profit() if kind == "auto_profit_yoy" else macro() if kind == "total_level" else investment())
        return reader.reviewed_investment_profit_candidates(page, [request(kind)])[0]

    def test_investment_total_private_manufacturing_and_duplicate_chart(self):
        candidates = reader.reviewed_investment_profit_candidates(investment(), requests())
        self.assertEqual(len(candidates), 4)
        by_id = {c["request_id"]: c for c in candidates}
        for req in requests():
            kind = reader.ROLES[(req["chart_id"], req["series_name"])][2]
            if kind not in {"total_yoy", "private_yoy", "manufacturing_yoy"}:
                continue
            candidate = by_id[req["id"]]
            self.assertEqual(candidate["value"], {"total_yoy": -7.2, "private_yoy": -10.1, "manufacturing_yoy": -2.3}[kind])
            verified = reader.verify_investment_profit_table_candidate(candidate, req, investment())
            self.assertEqual(candidate["period"], "2026-08")
            self.assertTrue(verified["reviewed_period_and_definition"])
            if kind == "manufacturing_yoy":
                self.assertIn("分行业", verified["semantic_text"])
                self.assertIn("固定资产投资", verified["semantic_text"])

    def test_macro_amount_is_ytd_column_with_own_yuan_unit(self):
        candidates = reader.reviewed_investment_profit_candidates(macro(), requests())
        self.assertEqual(len(candidates), 2)
        candidate = self.candidate("total_level", macro())
        self.assertEqual(candidate["value"], 293092)
        self.assertEqual(candidate["table_proof"]["column_index"], 3)
        self.assertIn("亿元", candidate["table_proof"]["unit_quote"])
        reader.verify_investment_profit_table_candidate(candidate, request("total_level"), macro())

    def test_profit_hierarchical_header_excludes_revenue(self):
        page = profit()
        candidate = self.candidate("auto_profit_yoy", page)
        self.assertEqual(candidate["value"], -16.0)
        self.assertEqual(candidate["table_proof"]["column_index"], 6)
        result = reader.verify_investment_profit_table_candidate(candidate, request("auto_profit_yoy"), page)
        self.assertIn("利润总额", result["semantic_text"])
        self.assertEqual(candidate["table_proof"]["unit_quote"], "(%)")
        for column, value in [(2, 2.9), (5, 1953.5)]:
            forged = copy.deepcopy(candidate)
            forged["table_proof"]["column_index"] = column
            forged["value"], forged["value_text"] = value, str(value)
            with self.assertRaisesRegex(ValueError, "binding_changed"):
                reader.verify_investment_profit_table_candidate(forged, request("auto_profit_yoy"), page)

    def test_profit_fullwidth_parentheses_are_only_typographical_unit_variant(self):
        raw = profit()["tables"][0]["source_html"].replace("(亿元)", "（亿元）").replace("(%)", "（%）")
        page = parse("表3 2026年1-8月份规模以上工业企业主要财务指标（分行业）", raw)
        candidate = self.candidate("auto_profit_yoy", page)
        self.assertEqual(candidate["value"], -16.0)
        self.assertEqual(candidate["table_proof"]["unit_quote"], "（%）")
        reader.verify_investment_profit_table_candidate(candidate, request("auto_profit_yoy"), page)
        raw = raw.replace("（%）", "（美元）")
        page = parse("表3 2026年1-8月份规模以上工业企业主要财务指标（分行业）", raw)
        self.assertEqual(reader.reviewed_investment_profit_candidates(page, [request("auto_profit_yoy")]), [])

    def test_no_private_amount_or_infrastructure_including_power(self):
        private_amount = copy.deepcopy(request("private_yoy"))
        private_amount.update(series_name="民间固定资产投资累计值", unit="亿元")
        infrastructure = copy.deepcopy(request("manufacturing_yoy"))
        infrastructure.update(series_name="基建", definition_aliases=["基础设施投资"])
        self.assertEqual(reader.reviewed_investment_profit_candidates(macro(), [private_amount]), [])
        self.assertEqual(reader.reviewed_investment_profit_candidates(investment(), [infrastructure]), [])

    def test_manufacturing_requires_investment_section_not_borrowed_context(self):
        raw = investment()["tables"][0]["source_html"].replace("分行业", "工业增加值分行业")
        page = investment(raw)
        self.assertEqual(reader.reviewed_investment_profit_candidates(page, [request("manufacturing_yoy")]), [])
        raw = investment()["tables"][0]["source_html"].replace("其中：民间投资", "民间投资")
        self.assertEqual(reader.reviewed_investment_profit_candidates(investment(raw), [request("private_yoy")]), [])

    def test_exact_row_duplicates_or_non_numeric_cells_not_guessed(self):
        raw = investment()["tables"][0]["source_html"]
        altered = raw.replace("</table>", "<tr><td>制造业</td><td>99</td></tr></table>")
        self.assertEqual(reader.reviewed_investment_profit_candidates(investment(altered), [request("manufacturing_yoy")]), [])
        altered = raw.replace("<td>-10.1</td>", "<td>…</td>")
        self.assertEqual(reader.reviewed_investment_profit_candidates(investment(altered), [request("private_yoy")]), [])

    def test_changed_coordinates_values_quotes_and_period_rejected(self):
        page, req = investment(), request("manufacturing_yoy")
        candidate = self.candidate("manufacturing_yoy", page)
        for change in [{"period": "2026-09"}, {"value": 99}, {"value": True}, {"value": float("nan")},
                       {"value_text": "-23"}, {"quote": candidate["quote"] + " 投资"}, {"unit": "亿元"},
                       {"request_id": "different"}]:
            forged = copy.deepcopy(candidate)
            forged.update(change)
            with self.assertRaises(ValueError):
                reader.verify_investment_profit_table_candidate(forged, req, page)
        for change in [{"row_index": True}, {"parent_row_index": 8}, {"section_row_index": 6},
                       {"column_index": 0}, {"caption_quote": "2026年1—7月份"}, {"unit_quote": "亿元"}]:
            forged = copy.deepcopy(candidate)
            forged["table_proof"].update(change)
            with self.assertRaises(ValueError):
                reader.verify_investment_profit_table_candidate(forged, req, page)

    def test_original_table_integrity_and_headers_replayed(self):
        original = profit()
        candidate = self.candidate("auto_profit_yoy", original)
        for mutation in ("html", "cells", "quote"):
            page = copy.deepcopy(original)
            if mutation == "html":
                page["tables"][0]["source_html"] += "tampered"
            elif mutation == "cells":
                page["tables"][0]["rows"][4]["cells"][6] = "99"
            else:
                page["tables"][0]["rows"][4]["quote"] += " 利润同比99%"
            with self.assertRaises(ValueError):
                reader.verify_investment_profit_table_candidate(candidate, request("auto_profit_yoy"), page)
        altered = original["tables"][0]["source_html"].replace('rowspan="3"', 'rowspan="2"')
        page = parse("表3 2026年1-8月份规模以上工业企业主要财务指标（分行业）", altered)
        self.assertEqual(reader.reviewed_investment_profit_candidates(page, [request("auto_profit_yoy")]), [])

    def test_publisher_publication_cutoff_and_target_month_not_guessed(self):
        for change in [{"url": "https://example.com/table.html"}, {"url": "http://www.stats.gov.cn/table.html"},
                       {"published_at": ""}, {"published_at": "2026-07-15"}]:
            page = investment()
            page.update(change)
            self.assertEqual(reader.reviewed_investment_profit_candidates(page, requests()), [])
        self.assertEqual(reader.reviewed_investment_profit_candidates(investment(), requests(), cutoff_date="2026-09-14"), [])
        self.assertEqual(reader.reviewed_investment_profit_candidates(investment(), requests(), report_month="2026-07"), [])
        forged = self.candidate("private_yoy")
        with self.assertRaisesRegex(ValueError, "after_cutoff"):
            reader.verify_investment_profit_table_candidate(forged, request("private_yoy"), investment(), cutoff_date="2026-09-14")

    def test_reader_not_fixed_to_2026(self):
        page = investment()
        raw = page["tables"][0]["source_html"]
        page = parse("2025年1—8月份固定资产投资（不含农户）主要数据", raw, published="2025-09-15")
        candidate = self.candidate("private_yoy", page)
        self.assertEqual(candidate["period"], "2025-08")
        reader.verify_investment_profit_table_candidate(candidate, request("private_yoy"), page)

    def test_real_official_june_july_august_contract_replay(self):
        cache = PROJECT / ".work/macro-public-run/codex-run-v3/working/macro-sources/pages"
        originals = PROJECT / ".work/macro-public-run/original-pages"
        contract = PROJECT / "runtime/skill-runs/macro-20261004-005541-c8ad8701/working/template-contract.json"
        if not cache.exists() or not contract.exists():
            self.skipTest("Saved official receipts/contract are required for local integration replay")
        real_requests = [r for r in json.loads(contract.read_text(encoding="utf-8"))["source_requests"]
                         if (r["chart_id"], r["series_name"]) in reader.ROLES]
        self.assertEqual(len(real_requests), 6)
        page_files = [
            cache / "1a02f07e44d37112f3b494c6f5114d8b2fb81ce2e6fb2826318d6032f1e4fda4.json",
            cache / "5bb23da8a0163bbdf54c2eefe8abbc343eb0d3f05442b7fef6cc968c773a8481.json",
            cache / "c23aa6e0d5281cca58c5f984d2677a22929541ba5decda7a80e6e055a451c0cd.json",
            cache / "77bdf8545c1a3d26fb1a1504f9121868e8eee79d2687f9dfbfd3cbdf6a4e584a.json",
            cache / "e82c2f5f854508c0c7399769a652661d2ccde5c934357e0ef2268b9f885dd276.json",
            cache / "bb256b38c65d55137d31bb0aa775e62b4115d03fe4efacf43330f8e11cf991d6.json",
        ] + [originals / ("nbs_macro_" + m + ".json") for m in ["jun", "jul", "aug"]]
        expected = {
            "total_level": [226370, 260328, 293092], "total_yoy": [-5.7, -6.7, -7.2],
            "private_yoy": [-8.5, -9.4, -10.1], "manufacturing_yoy": [-1.2, -1.7, -2.3],
            "auto_profit_yoy": [-19.5, -20.4, -16.0],
        }
        by_request = {r["id"]: r for r in real_requests}
        replayed = {}
        for file in page_files:
            page = json.loads(file.read_text(encoding="utf-8"))
            candidates = reader.reviewed_investment_profit_candidates(page, real_requests,
                                                                      cutoff_date="2026-10-03", report_month="2026-09")
            self.assertTrue(candidates, str(file))
            for candidate in candidates:
                req = by_request[candidate["request_id"]]
                reviewed = reader.verify_investment_profit_table_candidate(candidate, req, page,
                                                                            cutoff_date="2026-10-03", report_month="2026-09")
                self.assertTrue(reviewed["semantic_text"])
                kind = reader.ROLES[(req["chart_id"], req["series_name"])][2]
                self.assertEqual(candidate["value"], expected[kind][int(candidate["period"][-2:]) - 6])
                key = (req["id"], candidate["period"])
                if key in replayed:
                    self.assertEqual(replayed[key], candidate["value"])
                replayed[key] = candidate["value"]
        self.assertEqual(len(replayed), 18)


if __name__ == "__main__":
    unittest.main()
