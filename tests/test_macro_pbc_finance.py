import copy
from datetime import date
from hashlib import sha256
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / "skills/macro-monthly-report/scripts"


def load(name):
    spec = importlib.util.spec_from_file_location("finance_test_" + name, ROOT / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


finance = load("macro_pbc_finance")
source = load("macro_sources")
contract = load("macro_contract")
CUTOFF = date(2026, 10, 3)


def actual_requests():
    charts = [{"id": cid, "categories": ["2026-06", "2026-07", "2026-08"],
               "series": [{"name": name, "values": [None] * 3} for name in names]}
              for cid, names in (("s26-shape11", ("M1:同比", "M2:同比")),
                                 ("s26-shape12", ("M2:同比", "社会融资规模存量:同比")))]
    return [request for chart in charts for request in contract.request_contract(chart)]


def report(month=8, year=2026, m1_note=True, title=None):
    text = (title or f"{year}年{month}月金融统计数据报告") + "\n一、社会融资规模存量同比增长7.2%\n"
    text += f"初步统计，{year}年{month}月末社会融资规模存量为464.8万亿元，同比增长7.2%。\n"
    text += "二、前八个月社会融资规模增量累计为23.91万亿元\n前八个月人民币贷款增加10.44万亿元。\n"
    text += "三、广义货币增长7.5%\n"
    text += f"{month}月末，广义货币（M2）余额356.81万亿元，同比增长7.5%。狭义货币（M1）余额115.77万亿元，同比增长4.1%。\n"
    text += "四、前八个月人民币存款增加18.99万亿元\n"
    if m1_note:
        text += "注5：" + finance.M1_NOTE
    return {"url": "https://www.pbc.gov.cn/diaochatongjisi/20260914/index.html", "text": text,
            "text_sha256": sha256(text.encode()).hexdigest(), "published_at": "2026-09-14",
            "publication_date_basis": "publisher_url_date", "fetch_provider": "direct-public-publisher",
            "receipt_id": "synthetic-fixture", "tables": [], "truncated": False}


def change_text(body, old, new):
    body = copy.deepcopy(body)
    body["text"] = body["text"].replace(old, new)
    body["text_sha256"] = sha256(body["text"].encode()).hexdigest()
    return body


class PbcFinanceTests(unittest.TestCase):
    def candidate(self, rid="s26-shape11::M1:同比", body=None):
        req = next(item for item in actual_requests() if item["id"] == rid)
        body = body or report()
        return req, next(c for c in finance.reviewed_finance_candidates(body, [req])), body

    def test_four_real_contract_requests_and_literal_semantic_replay(self):
        qs = actual_requests(); self.assertEqual(len(qs), 4)
        body = report(); by_id = {q["id"]: q for q in qs}
        candidates = finance.reviewed_finance_candidates(body, qs)
        self.assertEqual(len(candidates), 4)
        for c in candidates:
            verified = finance.verify_finance_candidate(c, by_id[c["request_id"]], body, CUTOFF, "2026-09")
            self.assertTrue(verified["reviewed_period_and_definition"])
            self.assertEqual(verified["observation_kind"], "actual")
            self.assertNotIn("table", verified)
            self.assertNotIn("derived_value_verified", verified)
            for piece in verified["semantic_text"].splitlines():
                self.assertIn(finance.compact(piece), finance.compact(body["text"]))
        self.assertEqual({c["value"] for c in candidates}, {4.1, 7.5, 7.2})

    def test_unsupported_or_invalid_pages_are_no_match_not_errors(self):
        cases = ({}, {"text": ""}, {**report(), "url": "https://unreviewed.test/a"},
                 {**report(), "text_sha256": "invented"}, {**report(), "truncated": True},
                 {**report(), "published_at": "2026-02-31"})
        for body in cases:
            self.assertEqual(finance.reviewed_finance_candidates(body, actual_requests()), [])
        body = change_text(report(), "金融统计数据报告", "金融机构人民币信贷收支表")
        self.assertEqual(finance.reviewed_finance_candidates(body, actual_requests()), [])

    def test_m1_legacy_or_unproved_revision_not_merged(self):
        for body in (report(year=2024), report(m1_note=False)):
            self.assertNotIn("s26-shape11::M1:同比", {c["request_id"] for c in finance.reviewed_finance_candidates(body, actual_requests())})

    def test_m1_definition_requires_new_components_and_retains_original_spacing(self):
        altered = change_text(report(), "个人活期存款", "历史旧口径")
        self.assertNotIn("s26-shape11::M1:同比", {c["request_id"] for c in finance.reviewed_finance_candidates(altered, actual_requests())})
        body = change_text(report(), "个人活期存款", "个人 活期存款")
        req, c, _ = self.candidate(body=body)
        self.assertIn("个人 活期存款", c["pbc_finance_proof"]["m1_definition_quote"])
        finance.verify_finance_candidate(c, req, body, CUTOFF, "2026-09")

    def test_half_year_title_and_local_month_marker_must_agree(self):
        self.assertEqual(len(finance.reviewed_finance_candidates(report(month=6, title="2026年上半年金融统计数据报告"), actual_requests())), 4)
        body = report(month=8, title="2026年上半年金融统计数据报告")
        self.assertEqual(finance.reviewed_finance_candidates(body, actual_requests()), [])

    def test_balance_flow_and_credit_definitions_cannot_substitute(self):
        for definition, unit in (("新增人民币贷款", "亿元"), ("社会融资规模增量", "亿元"),
                                 ("社会融资规模增量结构：贷款", "亿元"), ("社会融资规模存量", "万亿元")):
            req = actual_requests()[-1]; req.update(definition=definition, unit=unit)
            self.assertEqual(finance.reviewed_finance_candidates(report(), [req]), [])

    def test_balance_number_cannot_be_changed_into_growth(self):
        req, c, body = self.candidate("s26-shape11::M2:同比")
        c.update(value=356.81, value_text="356.81")
        with self.assertRaisesRegex(ValueError, "candidate_not_original"):
            finance.verify_finance_candidate(c, req, body, CUTOFF, "2026-09")

    def test_all_fact_fields_and_arbitrary_flags_are_independently_replayed(self):
        req, original, body = self.candidate()
        changes = (("period", "2026-07"), ("unit", "亿元"), ("value", True),
                   ("quote", "invented"), ("definition_quote", "广义货币（M2）"),
                   ("period_quote", "2026年7月"), ("observation_kind", "derived"),
                   ("derived_value_verified", True), ("derivation_proof", {"verified": True}))
        for key, value in changes:
            with self.subTest(field=key):
                c = copy.deepcopy(original); c[key] = value
                with self.assertRaises(ValueError):
                    finance.verify_finance_candidate(c, req, body, CUTOFF, "2026-09")
        for key in original["pbc_finance_proof"]:
            c = copy.deepcopy(original); c["pbc_finance_proof"][key] = "invented"
            with self.assertRaises(ValueError):
                finance.verify_finance_candidate(c, req, body, CUTOFF, "2026-09")

    def test_late_publication_nonoriginal_host_and_receipt_tamper_rejected(self):
        req, c, original = self.candidate()
        for field, value in (("published_at", "2026-10-04"), ("url", "https://regional.pbc.gov.cn/a"),
                             ("text_sha256", "invented"), ("truncated", True)):
            body = copy.deepcopy(original); body[field] = value
            with self.assertRaises(ValueError):
                finance.verify_finance_candidate(c, req, body, CUTOFF, "2026-09")

    def test_core_metadata_whitelist_checks_provenance_not_blindly_strips(self):
        req, c, body = self.candidate()
        metadata = {"series_name": req["series_name"], "source_grade": "primary", "publisher_id": "primary:www.pbc.gov.cn",
                    "receipt_id": body["receipt_id"], "source_url": body["url"], "published_at": body["published_at"]}
        output = {**c, **metadata}
        self.assertEqual(finance.verify_finance_candidate(c, req, body, CUTOFF, "2026-09"),
                         finance.verify_finance_candidate(output, req, body, CUTOFF, "2026-09"))
        for field in metadata:
            changed = copy.deepcopy(output); changed[field] = "invented"
            with self.assertRaisesRegex(ValueError, "output_provenance_changed"):
                finance.verify_finance_candidate(changed, req, body, CUTOFF, "2026-09")
        changed = copy.deepcopy(output); changed["unreviewed_flag"] = True
        with self.assertRaisesRegex(ValueError, "candidate_not_original"):
            finance.verify_finance_candidate(changed, req, body, CUTOFF, "2026-09")

    def test_month_end_actual_cannot_precede_publication_or_target(self):
        req, c, body = self.candidate()
        body["published_at"] = "2026-08-10"
        with self.assertRaisesRegex(ValueError, "period_after_publication"):
            finance.verify_finance_candidate(c, req, body, CUTOFF, "2026-09")
        body["published_at"] = "2026-09-14"
        with self.assertRaisesRegex(ValueError, "period_after_publication_or_target"):
            finance.verify_finance_candidate(c, req, body, CUTOFF, "2026-07")

    def test_duplicate_and_forecast_sentences_not_accepted_as_actual(self):
        for body in (change_text(report(), "广义货币（M2）余额356.81万亿元，同比增长7.5%。",
                                 "预计广义货币（M2）余额356.81万亿元，同比增长7.5%。"),
                     change_text(report(), "广义货币（M2）余额356.81万亿元，同比增长7.5%。",
                                 "广义货币（M2）余额356.81万亿元，同比增长7.5%。广义货币（M2）余额356.81万亿元，同比增长7.6%。")):
            self.assertNotIn("s26-shape11::M2:同比", {c["request_id"] for c in finance.reviewed_finance_candidates(body, actual_requests())})

    def test_decline_direction_preserves_source_number_and_signed_value(self):
        body = change_text(report(), "狭义货币（M1）余额115.77万亿元，同比增长4.1%", "狭义货币（M1）余额115.77万亿元，同比下降1.2%")
        req, c, _ = self.candidate(body=body)
        self.assertEqual(c["value_text"], "1.2%")
        self.assertEqual(c["value"], -1.2)
        finance.verify_finance_candidate(c, req, body, CUTOFF, "2026-09")


class PbcFinanceCoreTests(unittest.TestCase):
    """Run once root attaches the independent helper branch to macro_sources."""
    def test_official_blank_article_source_is_not_a_reprint_but_named_external_source_is(self):
        req = next(q for q in actual_requests() if q["id"] == "s26-shape11::M2:同比")
        for blank in ("文章来源： \n | \n", "文章来源：\n", "文章来源： | \n"):
            body = change_text(report(), "一、社会融资", blank + "一、社会融资")
            c = finance.reviewed_finance_candidates(body, [req])[0]
            output = source.validate_observation(c, req, body, CUTOFF, "2026-09")
            self.assertEqual(output["source_grade"], "primary")
            self.assertEqual(output["publisher_id"], "primary:www.pbc.gov.cn")
        body = change_text(report(), "一、社会融资", "文章来源：国金证券\n一、社会融资")
        c = finance.reviewed_finance_candidates(body, [req])[0]
        with self.assertRaisesRegex(ValueError, "primary_domain_republished_source"):
            source.validate_observation(c, req, body, CUTOFF, "2026-09")

    def test_real_contract_candidates_core_acceptance_and_output_replay(self):
        qs = actual_requests(); by_id = {q["id"]: q for q in qs}; body = report()
        candidates = finance.reviewed_finance_candidates(body, qs)
        self.assertEqual(len(candidates), 4)
        for c in candidates:
            output = source.validate_observation(c, by_id[c["request_id"]], body, CUTOFF, "2026-09")
            replayed = source.validate_observation(output, by_id[c["request_id"]], body, CUTOFF, "2026-09")
            self.assertEqual(output, replayed)
            self.assertEqual(output["observation_kind"], "actual")
            self.assertEqual(output["pbc_finance_proof"], c["pbc_finance_proof"])
            self.assertEqual(output["source_grade"], "primary")

    def test_core_cannot_be_switched_to_another_balance_or_fake_proof(self):
        req = next(q for q in actual_requests() if q["id"] == "s26-shape11::M2:同比")
        body = report(); c = finance.reviewed_finance_candidates(body, [req])[0]
        output = source.validate_observation(c, req, body, CUTOFF, "2026-09")
        for value, token in ((356.81, "356.81"), (8.5, "7.5%")):
            changed = copy.deepcopy(output); changed.update(value=value, value_text=token)
            with self.assertRaises(ValueError):
                source.validate_observation(changed, req, body, CUTOFF, "2026-09")
        changed = copy.deepcopy(output); changed["pbc_finance_proof"]["request_profile"] = "money-m1"
        with self.assertRaises(ValueError):
            source.validate_observation(changed, req, body, CUTOFF, "2026-09")


if __name__ == "__main__":
    unittest.main()
