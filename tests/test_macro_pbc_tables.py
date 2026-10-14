import copy
from datetime import date
from hashlib import sha256
import importlib.util
import re
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / "skills/macro-monthly-report/scripts"


def load(name):
    spec = importlib.util.spec_from_file_location("pbc_test_" + name, ROOT / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tables = load("macro_pbc_tables")
source = load("macro_sources")
contract = load("macro_contract")


def actual_contract_requests():
    """Use the real reviewed contract builder; charts contain no source values."""
    seasonal = {"id": "s25-shape9", "reference_month": "2026-08", "categories": [],
                "series": [{"name": "2026", "values": [None] * 12}]}
    time_chart = {"id": "s25-shape10", "categories": ["2026-06", "2026-07", "2026-08"],
                  "series": [{"name": name, "values": [None] * 3}
                             for name in ("贷款", "非标融资", "直接融资", "政府债券")]}
    return contract.request_contract(seasonal) + contract.request_contract(time_chart)


def request(name="current"):
    cid = "s25-shape9" if name == "current" else "s25-shape10"
    return {"id": cid + "::" + name, "chart_id": cid, "series_name": name,
            "frequency": "monthly", "unit": "亿元",
            "definition": "社会融资规模增量" if name == "current" else "社会融资规模增量结构：" + name}


def raw_page(year=2026):
    chinese = "".join("<td>" + name + "</td>" for name in tables.HEADERS)
    english = ("AFRE(flow)", "RMB loans", "Foreign currency-denominated loans (RMB equivalent)",
               "Entrusted loans", "Trust loans", "Undiscounted bankers' acceptances",
               "Net financing of corporate bonds", "Government bonds",
               "Equity financing on the domestic stock market by non-financial enterprises",
               "Asset-backed securities of depository financial institutions", "Loans written off")
    english = "".join("<td>" + name + "</td>" for name in english)
    parent = '<td rowspan="3">项目 Items 月份 Month</td><td></td><td>其中 Of which</td>' + "<td></td>" * 9
    rows = ""
    for month, values in ((6, (33671, 17650, 455, 243, -503, -1084, 4012, 7683, 628, 322, 3188)),
                          (7, (14068, -5896, 85, -22, -226, -530, 4536, 13176, 1128, -159, 798)),
                          (8, (16577, 552, 409, 229, -233, 382, 2712, 10097, 639, -176, 906)),
                          (9, ("",) * 11)):
        rows += "<tr><td>" + f"{year}.{month:02d}" + "</td>" + "".join("<td>" + str(x) + "</td>" for x in values) + "</tr>"
    return f'''<html><meta name="PublishDate" content="{year}-09-14"><table>
    <tr><td colspan="12">社会融资规模增量统计表</td></tr>
    <tr><td colspan="12">Aggregate Financing to the Real Economy (Flow)</td></tr>
    <tr><td colspan="12">单位：亿元人民币</td></tr>
    <tr><td colspan="12">Unit: 100 million Yuan</td></tr>
    <tr>{parent}</tr><tr>{chinese}</tr><tr>{english}</tr>{rows}
    <tr><td colspan="12">注：1.社会融资规模增量是指一定时期内实体经济从金融体系获得的资金额。</td></tr>
    </table></html>'''


def page(year=2026, raw=None):
    original = raw or raw_page(year)
    body = source.parse_page(original, f"https://www.pbc.gov.cn/diaochatongjisi/attachDir/{year}/09/{year}0914.htm")
    body["receipt_id"] = "fixture-" + sha256(original.encode()).hexdigest()
    return body


class PbcFlowTests(unittest.TestCase):
    def candidate(self, req=None, body=None, period="2026-08"):
        return next(c for c in tables.reviewed_pbc_candidates(body or page(), [req or request()]) if c["period"] == period)

    def test_three_original_series_and_negative_month(self):
        candidates = tables.reviewed_pbc_candidates(page(), [request(), request("贷款"), request("政府债券")])
        self.assertEqual(len(candidates), 9)
        self.assertEqual(self.candidate()["value"], 16577)
        self.assertEqual(self.candidate(request("贷款"), period="2026-07")["value"], -5896)
        self.assertEqual(self.candidate(request("政府债券"))["value"], 10097)
        for c in candidates:
            req = request(c["request_id"].split("::")[1])
            self.assertIn("亿元人民币", tables.verify_pbc_table_candidate(c, req, page())["semantic_text"])

    def test_raw_header_is_shifted_but_grid_binding_is_proved(self):
        candidate = self.candidate(request("贷款"))
        self.assertEqual(candidate["table_proof"]["column_index"], 2)
        self.assertEqual(candidate["table_proof"]["header_column_index"], 1)
        self.assertEqual(candidate["definition_quote"], "人民币贷款")

    def test_future_blank_not_zero(self):
        self.assertNotIn("2026-09", {c["period"] for c in tables.reviewed_pbc_candidates(page(), [request()])})

    def test_not_hardcoded_to_current_year(self):
        candidate = self.candidate(body=page(2025), period="2025-08")
        self.assertEqual(candidate["period"], "2025-08")

    def test_no_other_financial_requests(self):
        for name in ("M2", "人民币贷款"):
            self.assertEqual(tables.reviewed_pbc_candidates(page(), [request(name)]), [])
        req = request(); req["chart_id"] = "s24-shape9"
        self.assertEqual(tables.reviewed_pbc_candidates(page(), [req]), [])

    def test_wrong_unit_or_frequency(self):
        for key, value in (("unit", "万亿元"), ("frequency", "quarterly")):
            req = request(); req[key] = value
            self.assertEqual(tables.reviewed_pbc_candidates(page(), [req]), [])

    def test_stock_caption_and_banking_table_not_substituted(self):
        for title in ("社会融资规模存量统计表", "金融机构人民币信贷收支表"):
            self.assertEqual(tables.reviewed_pbc_candidates(page(raw=raw_page().replace(tables.CAPTION, title)), [request()]), [])

    def test_original_host_and_tls_required(self):
        for url in ("http://www.pbc.gov.cn/a.htm", "https://regional.pbc.gov.cn/a.htm", "https://www.pbc.gov.cn.evil.test/a"):
            body = page(); body["url"] = url
            self.assertEqual(tables.reviewed_pbc_candidates(body, [request()]), [])

    def test_original_html_and_parsed_cell_tamper_rejected(self):
        for kind in ("html", "cells", "quote"):
            body = page(); candidate = self.candidate(body=body)
            if kind == "html": body["tables"][0]["source_html"] += "tamper"
            elif kind == "cells": body["tables"][0]["rows"][9]["cells"][1] = "999"
            else: body["tables"][0]["rows"][9]["quote"] += "999"
            with self.assertRaisesRegex(ValueError, "original_"):
                tables.verify_pbc_table_candidate(candidate, request(), body)

    def test_wrong_header_order_or_month_row_span_rejected(self):
        for raw in (raw_page().replace("<td>人民币贷款</td>", "<td>外币贷款</td>"),
                    raw_page().replace('rowspan="3"', 'rowspan="2"'),
                    raw_page().replace("月份 Month", "年份 Year")):
            self.assertEqual(tables.reviewed_pbc_candidates(page(raw=raw), [request()]), [])

    def test_no_page_wide_borrowing_of_scope_or_units(self):
        for raw in (raw_page().replace("单位：亿元人民币", "单位：万元人民币"),
                    raw_page().replace("实体经济从金融体系获得的资金额", "金融机构贷款余额")):
            self.assertEqual(tables.reviewed_pbc_candidates(page(raw=raw), [request()]), [])

    def test_candidate_value_period_quote_and_metric_mutations_rejected(self):
        for key, value in (("value", 999), ("value", True), ("period", "2026-09"),
                           ("value_text", "999"), ("definition_quote", "政府债券"), ("unit", "万亿元")):
            candidate = self.candidate(); candidate[key] = value
            with self.assertRaises(ValueError):
                tables.verify_pbc_table_candidate(candidate, request(), page())

    def test_coordinates_profile_and_hash_mutations_rejected(self):
        for key, value in (("row_index", -1), ("row_index", True), ("row_index", "9"),
                           ("column_index", 2), ("header_column_index", 1),
                           ("profile", "generic"), ("table_html_sha256", "false")):
            candidate = self.candidate(); candidate["table_proof"][key] = value
            with self.assertRaises(ValueError):
                tables.verify_pbc_table_candidate(candidate, request(), page())

    def test_duplicate_month_or_invalid_month_denied(self):
        for raw in (raw_page().replace("2026.07", "2026.06"), raw_page().replace("2026.07", "2026.13")):
            self.assertEqual(tables.reviewed_pbc_candidates(page(raw=raw), [request()]), [])

    def test_claimed_zero_for_blank_month_denied(self):
        candidate = self.candidate(); candidate["period"] = "2026-09"; candidate["table_proof"]["row_index"] = 10
        candidate["value"] = 0; candidate["value_text"] = "0"
        with self.assertRaisesRegex(ValueError, "missing_value_not_zero"):
            tables.verify_pbc_table_candidate(candidate, request(), page())

    def test_two_reviewed_same_row_sums_recomputed(self):
        expected = {"非标融资": [-1344, -778, 378], "直接融资": [4640, 5664, 3351]}
        for name, values in expected.items():
            for month, value in zip((6, 7, 8), values):
                req = request(name)
                candidate = self.candidate(req, period=f"2026-{month:02d}")
                verified = tables.verify_pbc_table_candidate(candidate, req, page())
                self.assertEqual(candidate["value"], value)
                self.assertTrue(verified["derived_value_verified"])
                self.assertEqual(candidate["observation_kind"], "derived")
                self.assertEqual(verified["derivation_proof"], candidate["derivation_proof"])
                self.assertNotIn("政府债券", candidate["derivation_proof"]["components"])

    def test_derived_proof_external_formula_component_coordinates_denied(self):
        req = request("非标融资")
        changes = (("formula_id", "arbitrary_sum"), ("formula_version", True),
                   ("operator", "subtract"), ("unit", "万亿元"), ("period", "2026-07"),
                   ("components", ["企业债券", "政府债券"]))
        for key, value in changes:
            candidate = self.candidate(req); candidate["derivation_proof"][key] = value
            with self.assertRaisesRegex(ValueError, "derived_proof_changed"):
                tables.verify_pbc_table_candidate(candidate, req, page())
        for key, value in (("column_index", 7), ("row_index", True), ("value", 999),
                           ("value_text", "999"), ("definition_quote", "政府债券")):
            candidate = self.candidate(req); candidate["derivation_proof"]["inputs"][0][key] = value
            with self.assertRaisesRegex(ValueError, "derived_proof_changed"):
                tables.verify_pbc_table_candidate(candidate, req, page())

    def test_derived_total_kind_or_value_cannot_be_forged(self):
        req = request("直接融资")
        for key, value in (("value", 999), ("value_text", "999"), ("observation_kind", "actual")):
            candidate = self.candidate(req); candidate[key] = value
            with self.assertRaises(ValueError):
                tables.verify_pbc_table_candidate(candidate, req, page())
        candidate = self.candidate(); candidate["observation_kind"] = "derived"
        with self.assertRaisesRegex(ValueError, "direct_cannot_claim"):
            tables.verify_pbc_table_candidate(candidate, request(), page())

    def test_one_missing_input_makes_sum_unavailable_not_partial(self):
        raw = raw_page().replace("<td>229</td>", "<td></td>")
        candidates = tables.reviewed_pbc_candidates(page(raw=raw), [request("非标融资")])
        self.assertNotIn("2026-08", {c["period"] for c in candidates})
        self.assertEqual(len(candidates), 2)


class PbcCoreIntegrationTests(unittest.TestCase):
    cutoff = date(2026, 10, 3)

    def test_real_five_request_contract_through_core_then_replay(self):
        requests = actual_contract_requests()
        self.assertEqual(len(requests), 5)
        body = page()
        candidates = tables.reviewed_pbc_candidates(body, requests)
        self.assertEqual(len(candidates), 15)
        by_id = {req["id"]: req for req in requests}
        for candidate in candidates:
            req = by_id[candidate["request_id"]]
            observed = source.validate_observation(candidate, req, body, self.cutoff, "2026-09")
            replayed = source.validate_observation(observed, req, body, self.cutoff, "2026-09")
            self.assertEqual(observed, replayed)
            self.assertEqual(observed["source_grade"], "primary")
            if candidate.get("observation_kind") == "derived":
                self.assertEqual(observed["observation_kind"], "derived")
                self.assertEqual(observed["derivation_proof"], candidate["derivation_proof"])
            else:
                self.assertNotIn("derivation_proof", observed)

    def test_sum_absent_from_original_text_is_accepted_only_by_recomputed_formula(self):
        req = next(r for r in actual_contract_requests() if r["series_name"] == "非标融资")
        body = page()
        candidate = next(c for c in tables.reviewed_pbc_candidates(body, [req]) if c["period"] == "2026-08")
        self.assertEqual(candidate["value"], 378)
        self.assertIsNone(re.search(r"(?<![\d.])378(?![\d.])", body["text"]))
        observed = source.validate_observation(candidate, req, body, self.cutoff, "2026-09")
        self.assertEqual(observed["observation_kind"], "derived")
        self.assertEqual(observed["value"], 378)
        changed = copy.deepcopy(observed); changed["value"] = 379; changed["value_text"] = "379"
        with self.assertRaises(ValueError):
            source.validate_observation(changed, req, body, self.cutoff, "2026-09")
        changed = copy.deepcopy(observed); changed["derivation_proof"]["inputs"][0]["value"] = 230
        with self.assertRaisesRegex(ValueError, "derived_proof_changed"):
            source.validate_observation(changed, req, body, self.cutoff, "2026-09")

    def test_arbitrary_proof_does_not_bypass_nontable_literal_validation(self):
        req = next(r for r in actual_contract_requests() if r["chart_id"] == "s25-shape9")
        quote = "2026年8月社会融资规模增量为16577亿元。"
        body = source.parse_page('<html><meta name="PublishDate" content="2026-09-14"><p>' + quote + '</p></html>',
                                 "https://www.pbc.gov.cn/diaochatongjisi/20260914.htm")
        body["receipt_id"] = "literal-fixture"
        candidate = {"request_id": req["id"], "definition": req["definition"], "unit": "亿元",
                     "period": "2026-08", "period_quote": "2026年8月", "definition_quote": "社会融资规模增量",
                     "quote": quote, "value": 16577, "value_text": "16577", "observation_kind": "derived",
                     "derivation_proof": {"formula_id": "arbitrary", "formula_version": 1, "inputs": [],
                                           "derived_value_verified": True}}
        observed = source.validate_observation(candidate, req, body, self.cutoff, "2026-09")
        self.assertNotIn("derivation_proof", observed)
        self.assertNotEqual(observed.get("observation_kind"), "derived")
        for value, token in ((99999, "99999"), (16578, "16577")):
            changed = copy.deepcopy(candidate); changed.update({"value": value, "value_text": token})
            with self.assertRaises(ValueError):
                source.validate_observation(changed, req, body, self.cutoff, "2026-09")

    def test_arbitrary_proof_does_not_upgrade_direct_table_observation(self):
        req = next(r for r in actual_contract_requests() if r["series_name"] == "贷款")
        body = page()
        candidate = next(c for c in tables.reviewed_pbc_candidates(body, [req]) if c["period"] == "2026-08")
        candidate["derivation_proof"] = {"formula_id": "arbitrary", "derived_value_verified": True}
        candidate["observation_kind"] = "derived"
        with self.assertRaisesRegex(ValueError, "direct_cannot_claim_derivation"):
            source.validate_observation(candidate, req, body, self.cutoff, "2026-09")

    def test_arbitrary_verified_flag_cannot_bypass_generic_table_literal_value(self):
        req = next(r for r in actual_contract_requests() if r["chart_id"] == "s25-shape9")
        raw = '<html><meta name="PublishDate" content="2026-09-14"><table><tr><th>月份</th><th>社会融资规模增量（亿元）</th></tr><tr><td>2026年8月</td><td>16577</td></tr></table></html>'
        body = source.parse_page(raw, "https://www.pbc.gov.cn/diaochatongjisi/20260914.htm")
        body["receipt_id"] = "generic-table-fixture"
        candidate = {"request_id": req["id"], "definition": req["definition"], "unit": "亿元",
                     "period": "2026-08", "period_quote": "2026年8月",
                     "definition_quote": "社会融资规模增量（亿元）", "quote": body["tables"][0]["rows"][1]["quote"],
                     "value": 16577, "value_text": "16577", "observation_kind": "derived",
                     "derived_value_verified": True,
                     "derivation_proof": {"formula_id": "arbitrary", "derived_value_verified": True},
                     "table_proof": {"table_index": 0, "row_index": 1, "column_index": 1,
                                     "period_column_index": 0, "header_row_index": 0}}
        observed = source.validate_observation(candidate, req, body, self.cutoff, "2026-09")
        self.assertNotIn("derivation_proof", observed)
        self.assertNotEqual(observed.get("observation_kind"), "derived")
        self.assertEqual(observed, source.validate_observation(observed, req, body, self.cutoff, "2026-09"))
        changed = copy.deepcopy(candidate); changed["value"] = 99999
        with self.assertRaisesRegex(ValueError, "observation_value_changed"):
            source.validate_observation(changed, req, body, self.cutoff, "2026-09")
        changed = copy.deepcopy(candidate); changed.update(value=99999, value_text="99999")
        with self.assertRaisesRegex(ValueError, "observation_table_cell_mismatch"):
            source.validate_observation(changed, req, body, self.cutoff, "2026-09")

    def test_all_five_outputs_are_independently_replayed_in_source_package(self):
        requests = actual_contract_requests()
        by_id = {req["id"]: req for req in requests}
        body = page()
        outputs = [source.validate_observation(candidate, by_id[candidate["request_id"]], body, self.cutoff, "2026-09")
                   for candidate in tables.reviewed_pbc_candidates(body, requests)]
        package = {"report_month": "2026-09", "cutoff_date": "2026-10-03", "evidence_observations": outputs}
        replayed = source.verify_source_corroboration(package, {"source_requests": requests}, {body["receipt_id"]: body})
        self.assertEqual(replayed["issues"], [])
        self.assertEqual(len(replayed["observations"]), 15)
        self.assertEqual(sum(item.get("observation_kind") == "derived" for item in replayed["observations"]), 6)
        self.assertEqual({item["request_id"] for item in replayed["observations"]}, set(by_id))
        corrupted = copy.deepcopy(package)
        derived = next(item for item in corrupted["evidence_observations"] if item.get("observation_kind") == "derived")
        derived["derivation_proof"]["inputs"][0]["period"] = "2026-07" if derived["period"] != "2026-07" else "2026-08"
        with self.assertRaisesRegex(ValueError, "pbc_derived_proof_changed"):
            source.verify_source_corroboration(corrupted, {"source_requests": requests}, {body["receipt_id"]: body})

    def test_core_rejects_cross_row_unit_hash_and_formula_proof_changes(self):
        req = next(r for r in actual_contract_requests() if r["series_name"] == "非标融资")
        body = page()
        original = next(c for c in tables.reviewed_pbc_candidates(body, [req]) if c["period"] == "2026-08")
        mutations = (("period", "2026-07"), ("unit", "万亿元"), ("table_html_sha256", "invented"),
                     ("formula_id", "arbitrary_sum"), ("operator", "subtract"))
        for key, value in mutations:
            with self.subTest(field=key):
                candidate = copy.deepcopy(original)
                candidate["derivation_proof"][key] = value
                with self.assertRaisesRegex(ValueError, "pbc_derived_proof_changed"):
                    source.validate_observation(candidate, req, body, self.cutoff, "2026-09")
        candidate = copy.deepcopy(original)
        candidate["derivation_proof"]["inputs"][0]["row_index"] -= 1
        with self.assertRaisesRegex(ValueError, "pbc_derived_proof_changed"):
            source.validate_observation(candidate, req, body, self.cutoff, "2026-09")


if __name__ == "__main__":
    unittest.main()
