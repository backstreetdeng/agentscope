import copy
from datetime import date
from hashlib import sha256
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / "skills/macro-monthly-report/scripts"


def load(name):
    spec = importlib.util.spec_from_file_location("customs_test_" + name, ROOT / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tables = load("macro_customs_trade")
sources = load("macro_sources")
URL = "http://english.customs.gov.cn/Statics/00000000-0000-0000-0000-000000000001.html"


def req(name="出口金额:当月同比(%,右轴)"):
    return {"id": "s19-shape13::" + name, "chart_id": "s19-shape13", "series_name": name,
            "definition": "美元计价进出口：" + name, "frequency": "monthly",
            "unit": "亿美元" if name == "贸易差额(亿美元)" else "%"}


def document(html, caption):
    page = sources.parse_page(f'<div class="atcl-ttl">{caption}</div><div class="atcl-date">2026/09/18</div>' + html, URL)
    page["text_sha256"] = sha256(page["text"].encode()).hexdigest()
    return page


def trade_mode(month="Aug", month_number=8, unit="Unit: USD1 Million", total_label="Total Value"):
    caption = f"(2) China's Total Export &amp; Import Values by Trade Mode, {month} 2026 (in USD)"
    html = f'''<table><tr><td colspan="7">{caption}</td></tr>
    <tr><td colspan="7">{unit}</td></tr>
    <tr><td rowspan="2">Trade Mode</td><td colspan="3">{month_number}</td><td colspan="3">Year-on-Year (±%)</td></tr>
    <tr><td>Export &amp; Import</td><td>Export</td><td>Import</td><td>Export &amp; Import</td><td>Export</td><td>Import</td></tr>
    <tr><td>{total_label}</td><td>683,796.7</td><td>401,441.0</td><td>282,355.8</td><td>26.3</td><td>25.0</td><td>28.2</td></tr>
    <tr><td>Ordinary Trade</td><td>405,604.2</td><td>252,800.2</td><td>152,804.0</td><td>18.0</td><td>19.1</td><td>16.1</td></tr></table>'''
    return document(html, caption)


def balance(unit="Unit:US$ million", kind="B：Monthly", body=None):
    caption = "1.Summary of Imports and Exports (In USD) " + kind
    body = body or '''<tr><td>2026.06</td><td>698,208</td><td>411,837</td><td>286,370</td><td>125,467</td><td>3,675,209</td><td>2,124,565</td><td>1,550,644</td><td>573,921</td></tr>
    <tr><td>2026.07</td><td>683,166</td><td>397,833</td><td>285,333</td><td>112,500</td><td>4,358,375</td><td>2,522,398</td><td>1,835,977</td><td>686,421</td></tr>
    <tr><td>2026.08</td><td>683,797</td><td>401,441</td><td>282,356</td><td>119,085</td><td>5,042,172</td><td>2,923,839</td><td>2,118,333</td><td>805,506</td></tr>'''
    html = f'''<table><tr><td colspan="9">{caption}</td></tr><tr><td colspan="9">{unit}</td></tr>
    <tr><td rowspan="2">Year&amp;Month</td><td rowspan="2">Total</td><td rowspan="2">Export</td><td rowspan="2">Import</td><td rowspan="2">Balance</td><td colspan="4">1to8</td></tr>
    <tr><td>Total</td><td>Export</td><td>Import</td><td>Balance</td></tr>{body}</table>'''
    return document(html, caption)


class CustomsTradeTests(unittest.TestCase):
    def test_original_article_publication_header_scoped_parser(self):
        self.assertEqual(trade_mode()["published_at"], "2026-09-18")
        self.assertEqual(balance()["publication_date_basis"], "reviewed_customs_statistical_article_header")
        caption = "1.Summary of Imports and Exports (In USD) B：Monthly"
        for raw in [
            f'<div class="atcl-ttl">{caption}</div><p>2026/09/18</p>',
            '<div class="atcl-ttl">Unrelated article</div><div class="atcl-date">2026/09/18</div>',
            f'<div class="atcl-ttl">{caption}</div><script>var x="2026/09/18"</script>',
            f'<div class="atcl-ttl">{caption}</div><div class="atcl-date">2026/09/18</div><div class="atcl-date">2026/09/19</div>',
        ]:
            self.assertEqual(sources.parse_page(raw, URL)["published_at"], "")
        self.assertEqual(sources.parse_page(f'<div class="atcl-ttl">{caption}</div><div class="atcl-date">2026/09/18</div>',
                                           URL.replace("english.customs.gov.cn", "evil.test"))["published_at"], "")

    def test_publication_receipt_date_and_port_cannot_be_changed(self):
        request, page = req(), trade_mode()
        candidate = tables.reviewed_public_candidates(page, [request])[0]
        for change in [{"published_at": "2026-09-19"}, {"published_at": ""},
                       {"url": URL.replace("english.customs.gov.cn", "english.customs.gov.cn:8080")}]:
            changed = dict(page, **change)
            self.assertEqual(tables.reviewed_public_candidates(changed, [request]), [])
            with self.assertRaises(ValueError):
                tables.verify_public_table_candidate(candidate, request, changed)

    def test_core_double_replay_and_exact_unit_scale(self):
        for name, page in [("出口金额:当月同比(%,右轴)", trade_mode()),
                           ("进口金额:当月同比(%,右轴)", trade_mode()),
                           ("贸易差额(亿美元)", balance())]:
            request = dict(req(name), original_publisher_domains=["customs.gov.cn"], source_domains=["customs.gov.cn"],
                           definition_aliases=["Export" if name.startswith("出口") else "Import" if name.startswith("进口") else "Balance"],
                           context_groups=[["美元", "US dollar", "USD"]] + ([] if name == "贸易差额(亿美元)" else [["同比", "year-on-year"]]))
            page["receipt_id"] = "customs-fixture-original"
            candidates = sources._table_candidates(page, [request])
            self.assertTrue(candidates)
            for candidate in candidates:
                checked = sources.validate_observation(sources._canonical_table_candidate(candidate, page), request, page,
                                                        date(2026, 10, 3), "2026-09")
                self.assertEqual(checked, sources.validate_observation(checked, request, page, date(2026, 10, 3), "2026-09"))
                self.assertEqual(checked["publisher_id"], "primary:english.customs.gov.cn")
                if name == "贸易差额(亿美元)":
                    self.assertEqual(checked["observation_kind"], "derived")
                    self.assertEqual(checked["derivation_proof"]["divisor"], 100)
                    changed = copy.deepcopy(candidate)
                    changed["derivation_proof"]["divisor"] = 1
                    with self.assertRaisesRegex(ValueError, "customs_derived_proof_changed"):
                        sources.validate_observation(changed, request, page, date(2026, 10, 3), "2026-09")

    def test_unregistered_unit_conversion_flag_cannot_bypass_core(self):
        request, page = req("贸易差额(亿美元)"), balance()
        request.update(source_domains=["customs.gov.cn"], original_publisher_domains=["customs.gov.cn"], definition_aliases=["Balance"])
        page["receipt_id"] = "customs-fixture-original"
        candidate = tables.reviewed_public_candidates(page, [request])[-1]
        candidate.pop("table_proof")
        candidate.update(unit_conversion_verified=True, exact_unit_scale_verified=True)
        with self.assertRaises(ValueError):
            sources.validate_observation(candidate, request, page, date(2026, 10, 3), "2026-09")

    def test_monthly_yoy_national_total_exact_columns(self):
        page = trade_mode()
        for name, expected, column in [("出口金额:当月同比(%,右轴)", 25.0, 5), ("进口金额:当月同比(%,右轴)", 28.2, 6)]:
            request = req(name)
            candidate = tables.reviewed_public_candidates(page, [request])[0]
            self.assertEqual((candidate["period"], candidate["value"], candidate["table_proof"]["column_index"]), ("2026-08", expected, column))
            self.assertTrue(tables.verify_public_table_candidate(candidate, request, page)["reviewed_period_and_definition"])

    def test_balance_direct_published_cell_not_amount_subtraction(self):
        request, page = req("贸易差额(亿美元)"), balance()
        candidates = tables.reviewed_public_candidates(page, [request])
        self.assertEqual([(x["period"], x["value"]) for x in candidates], [("2026-06", 1254.67), ("2026-07", 1125.0), ("2026-08", 1190.85)])
        for candidate in candidates:
            checked = tables.verify_public_table_candidate(candidate, request, page)
            self.assertTrue(checked["derived_value_verified"])
            self.assertTrue(checked["unit_conversion_verified"])
            proof = checked["derivation_proof"]
            self.assertEqual((proof["input_unit"], proof["scale"], proof["output_unit"]), ("US$ million", 0.01, "亿美元"))
            self.assertEqual(len(proof["inputs"]), 1)
            self.assertEqual(proof["inputs"][0]["column_index"], 4)
        self.assertEqual(candidates[2]["derivation_proof"]["inputs"][0]["value_text"], "119,085")

    def test_original_published_balance_wins_over_rounded_amount_subtraction(self):
        # The official August-vintage historical March2025 row has rounded
        # exports 313044 and imports211149 but directly published balance101894.
        body = '<tr><td>2025.03</td><td>524,193</td><td>313,044</td><td>211,149</td><td>101,894</td><td>1,433,180</td><td>852,077</td><td>581,102</td><td>270,975</td></tr>'
        request, page = req("贸易差额(亿美元)"), balance(body=body)
        candidate = tables.reviewed_public_candidates(page, [request])[0]
        self.assertEqual(candidate["value"], 1018.94)
        self.assertNotEqual(candidate["value"], (313044 - 211149) / 100)
        tables.verify_public_table_candidate(candidate, request, page)

    def test_rmb_regional_cumulative_annual_wrong_profiles_rejected(self):
        self.assertEqual(tables.reviewed_public_candidates(trade_mode(unit="Unit: CNY1 Million"), [req()]), [])
        self.assertEqual(tables.reviewed_public_candidates(trade_mode(total_label="Shanghai"), [req()]), [])
        self.assertEqual(tables.reviewed_public_candidates(balance(kind="A：Annually"), [req("贸易差额(亿美元)")]), [])
        self.assertEqual(tables.reviewed_public_candidates(balance(unit="Unit:CNY million"), [req("贸易差额(亿美元)")]), [])
        self.assertEqual(tables.reviewed_public_candidates(trade_mode(), [req("贸易差额(亿美元)")]), [])

    def test_caption_month_cannot_override_header_month(self):
        self.assertEqual(tables.reviewed_public_candidates(trade_mode(month="Jul", month_number=8), [req()]), [])

    def test_unreviewed_request_identity_definition_unit_frequency_rejected(self):
        for change in [{"chart_id": "s19-shape18"}, {"id": "other"}, {"unit": "亿元"}, {"frequency": "quarterly"}, {"definition": "人民币计价进出口"}]:
            request = req()
            request.update(change)
            self.assertEqual(tables.reviewed_public_candidates(trade_mode(), [request]), [])

    def test_wrong_scope_and_original_receipt_hash_rejected(self):
        for change in [{"url": "https://shanghai.customs.gov.cn/Statics/00000000-0000-0000-0000-000000000001.html"}, {"text_sha256": "fake"}, {"truncated": True}]:
            page = trade_mode()
            page.update(change)
            self.assertEqual(tables.reviewed_public_candidates(page, [req()]), [])

    def test_original_cells_quotes_and_html_cannot_be_mutated(self):
        request, page = req(), trade_mode()
        candidate = tables.reviewed_public_candidates(page, [request])[0]
        for mutate in [lambda p:p["tables"][0]["rows"][4]["cells"].__setitem__(5, "99"),
                       lambda p:p["tables"][0].__setitem__("source_html", p["tables"][0]["source_html"] + "tamper"),
                       lambda p:p["tables"][0]["rows"][4].__setitem__("quote", "99")]:
            changed = copy.deepcopy(page)
            mutate(changed)
            with self.assertRaises(ValueError):
                tables.verify_public_table_candidate(candidate, request, changed)

    def test_candidate_values_coordinates_period_and_profile_rejected(self):
        for change in [{"value": True}, {"value": 99}, {"period": "2026-09"}, {"unit": "亿元"}]:
            candidate = tables.reviewed_public_candidates(trade_mode(), [req()])[0]
            candidate.update(change)
            with self.assertRaises(ValueError):
                tables.verify_public_table_candidate(candidate, req(), trade_mode())
        for change in [{"column_index": 2}, {"row_index": True}, {"profile": "generic"}]:
            candidate = tables.reviewed_public_candidates(trade_mode(), [req()])[0]
            candidate["table_proof"].update(change)
            with self.assertRaises(ValueError):
                tables.verify_public_table_candidate(candidate, req(), trade_mode())

    def test_balance_unit_scale_and_cumulative_coordinate_tampering_rejected(self):
        request, page = req("贸易差额(亿美元)"), balance()
        for mutate in [lambda c:c["table_proof"].__setitem__("column_index", 8),
                       lambda c:c["derivation_proof"].__setitem__("scale", 1.0),
                       lambda c:c["derivation_proof"]["inputs"][0].__setitem__("value", 805506),
                       lambda c:c["derivation_proof"]["inputs"][0].__setitem__("column_index", True),
                       lambda c:c["derivation_proof"].__setitem__("input_unit", "CNY million")]:
            candidate = tables.reviewed_public_candidates(page, [request])[-1]
            mutate(candidate)
            with self.assertRaises(ValueError):
                tables.verify_public_table_candidate(candidate, request, page)

    def test_duplicate_period_and_missing_balance_not_zero(self):
        row = '<tr><td>2026.08</td>' + '<td>1</td>' * 8 + '</tr>'
        self.assertEqual(tables.reviewed_public_candidates(balance(body=row + row), [req("贸易差额(亿美元)")]), [])
        row = '<tr><td>2026.08</td><td>1</td><td>1</td><td>1</td><td>-</td>' + '<td>1</td>' * 4 + '</tr>'
        self.assertEqual(tables.reviewed_public_candidates(balance(body=row), [req("贸易差额(亿美元)")]), [])

    def test_unperioded_percent_children_and_future_rows_not_carried_forward(self):
        row = '<tr><td>2026.08</td>' + '<td>100</td>' * 8 + '</tr>'
        child = '<tr><td></td><td>26.3</td><td>25.0</td><td>28.2</td><td></td><td>22.4</td><td>19.3</td><td>27.0</td><td></td></tr>'
        future = '<tr><td></td>' + '<td>-</td>' * 8 + '</tr>'
        candidates = tables.reviewed_public_candidates(balance(body=row + child + future), [req("贸易差额(亿美元)")])
        self.assertEqual(len(candidates), 1)
        self.assertEqual((candidates[0]["period"], candidates[0]["value"]), ("2026-08", 1.0))

    def test_no_publication_date_invented(self):
        page = trade_mode()
        candidate = tables.reviewed_public_candidates(page, [req()])[0]
        self.assertNotIn("published_at", candidate)
        self.assertEqual(candidate["table_proof"]["publication_date_quote"], "2026/09/18")

    def test_other_page_date_cannot_be_borrowed_as_vintage(self):
        page = trade_mode()
        page["tables"][0]["context"] = page["tables"][0]["context"].replace("2026/09/18", "2026/09/19")
        self.assertEqual(tables.reviewed_public_candidates(page, [req()]), [])


if __name__ == "__main__":
    unittest.main()
