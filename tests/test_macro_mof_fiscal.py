import copy
from datetime import date
from hashlib import sha256
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / "skills/macro-monthly-report/scripts"


def load(name):
    spec = importlib.util.spec_from_file_location("fiscal_test_" + name, ROOT / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fiscal = load("macro_mof_fiscal")
source = load("macro_sources")
contract = load("macro_contract")
CUTOFF = date(2026, 10, 3)


def actual_requests():
    chart = {"id": "s30-shape13", "categories": ["2026-06", "2026-07", "2026-08"],
             "series": [{"name": rid.split("::")[1], "values": [None] * 3} for rid in fiscal.ROLES]}
    return contract.request_contract(chart)


def report(month=8, year=2026):
    marker = "上半年" if month == 6 else f"1-{month}月"
    text = (f"{year}年{marker}财政收支情况\n国库司\n2017年11月21日 星期二\n"
            f"{year}年{month+1}月18日 来源：国库司\n一、全国一般公共预算收支情况\n"
            "（一）一般公共预算收入情况。\n"
            f"{marker}，全国一般公共预算收入156633亿元，同比增长5.7%。其中，税收收入129104亿元。\n"
            "（二）一般公共预算支出情况。\n"
            f"{marker}，全国一般公共预算支出181451亿元，同比增长1.2%。\n"
            "二、全国政府性基金预算收支情况\n"
            f"{marker}，全国政府性基金预算收入31992亿元，同比增长5.1%。")
    return {"url": "https://gks.mof.gov.cn/tongjishuju/202609/t20260918_3997709.htm",
            "text": text, "text_sha256": sha256(text.encode()).hexdigest(),
            "published_at": f"{year}-{month+1:02d}-18", "receipt_id": "synthetic-fixture",
            "tables": [], "truncated": False, "fetch_provider": "direct-public-publisher"}


def change_text(body, old, new):
    body = copy.deepcopy(body)
    body["text"] = body["text"].replace(old, new)
    body["text_sha256"] = sha256(body["text"].encode()).hexdigest()
    return body


class FiscalTests(unittest.TestCase):
    def candidate(self, body=None):
        body = body or report(); request = actual_requests()[0]
        return request, fiscal.reviewed_fiscal_candidates(body, [request])[0], body

    def test_four_exact_contract_roles_and_original_sentence_replay(self):
        requests = actual_requests(); by_id = {q["id"]: q for q in requests}; body = report()
        candidates = fiscal.reviewed_fiscal_candidates(body, requests)
        self.assertEqual(len(candidates), 4)
        self.assertEqual([c["value"] for c in candidates], [156633, 181451, 5.7, 1.2])
        for c in candidates:
            output = source.validate_observation(c, by_id[c["request_id"]], body, CUTOFF, "2026-09")
            self.assertEqual(output, source.validate_observation(output, by_id[c["request_id"]], body, CUTOFF, "2026-09"))
            self.assertEqual(output["source_grade"], "primary")
            self.assertEqual(output["observation_kind"], "actual")
            self.assertEqual(output["unit"], "亿元" if "万亿" in c["request_id"] else "%")

    def test_half_year_cumulative_is_not_monthly_flow(self):
        body = report(month=6)
        candidates = fiscal.reviewed_fiscal_candidates(body, actual_requests())
        self.assertEqual(len(candidates), 4)
        for request, c in zip(actual_requests(), candidates):
            self.assertEqual(source.validate_observation(c, request, body, CUTOFF, "2026-09")["period"], "2026-06")
        for bad in (change_text(body, "上半年，全国", "6月，全国"),
                    change_text(body, "上半年财政", "6月财政")):
            self.assertEqual(fiscal.reviewed_fiscal_candidates(bad, actual_requests()), [])

    def test_foreign_or_local_budget_and_fund_cannot_replace_national_general_budget(self):
        for old, new in (("全国一般公共预算", "地方一般公共预算"),
                         ("全国一般公共预算", "全国政府性基金预算"),
                         ("一般公共预算收入情况", "政府性基金预算收入情况")):
            body = change_text(report(), old, new)
            self.assertNotIn(actual_requests()[0]["id"], {c["request_id"] for c in fiscal.reviewed_fiscal_candidates(body, actual_requests())})

    def test_duplicate_or_forecast_sentence_rejected(self):
        sentence = "1-8月，全国一般公共预算收入156633亿元，同比增长5.7%。"
        for replacement in (sentence + sentence, "预计" + sentence):
            body = change_text(report(), sentence, replacement)
            self.assertNotIn(actual_requests()[0]["id"], {c["request_id"] for c in fiscal.reviewed_fiscal_candidates(body, actual_requests())})

    def test_unit_alias_definition_host_and_frequency_must_be_exact(self):
        for field, value in (("unit", "万亿元"), ("definition", "全国当月财政收入"),
                             ("frequency", "quarterly"), ("definition_aliases", ["税收收入"])):
            q = actual_requests()[0]; q[field] = value
            self.assertEqual(fiscal.reviewed_fiscal_candidates(report(), [q]), [])

    def test_invalid_or_tampered_receipts_are_not_candidates(self):
        for field, value in (("url", "https://www.mof.gov.cn/a"), ("truncated", True),
                             ("text_sha256", "invented"), ("published_at", "2026-09-19")):
            body = report(); body[field] = value
            self.assertEqual(fiscal.reviewed_fiscal_candidates(body, actual_requests()), [])
        self.assertEqual(fiscal.reviewed_fiscal_candidates({}, actual_requests()), [])

    def test_every_observation_and_proof_field_is_replayed(self):
        q, original, body = self.candidate()
        for field, value in (("value", True), ("value", 15663.3), ("period", "2026-07"),
                             ("observation_kind", "derived"), ("quote", "invented"),
                             ("unreviewed_actual_flag", True)):
            c = copy.deepcopy(original); c[field] = value
            with self.assertRaises(ValueError):
                source.validate_observation(c, q, body, CUTOFF, "2026-09")
        for field in original["mof_fiscal_proof"]:
            c = copy.deepcopy(original); c["mof_fiscal_proof"][field] = "invented"
            with self.assertRaises(ValueError):
                source.validate_observation(c, q, body, CUTOFF, "2026-09")

    def test_metadata_whitelist_does_not_accept_changed_provenance(self):
        q, c, body = self.candidate()
        output = source.validate_observation(c, q, body, CUTOFF, "2026-09")
        for field in fiscal.METADATA:
            changed = copy.deepcopy(output); changed[field] = "invented"
            with self.assertRaises(ValueError):
                source.validate_observation(changed, q, body, CUTOFF, "2026-09")

    def test_publication_cutoff_target_and_month_end_guard(self):
        q, c, body = self.candidate()
        with self.assertRaises(ValueError):
            source.validate_observation(c, q, body, date(2026, 9, 17), "2026-09")
        with self.assertRaises(ValueError):
            source.validate_observation(c, q, body, CUTOFF, "2026-07")
        body = change_text(body, "2026年9月18日", "2026年8月18日"); body["published_at"] = "2026-08-18"
        c = fiscal.reviewed_fiscal_candidates(body, [q])[0]
        with self.assertRaisesRegex(ValueError, "period_after_publication"):
            source.validate_observation(c, q, body, CUTOFF, "2026-09")

    def test_negative_growth_keeps_literal_unsigned_number_with_decline_direction(self):
        body = change_text(report(), "同比增长5.7%", "同比下降5.7%")
        q, c, body = self.candidate(body)
        self.assertEqual(source.validate_observation(c, q, body, CUTOFF, "2026-09")["value"], 156633)
        q = actual_requests()[2]; c = fiscal.reviewed_fiscal_candidates(body, [q])[0]
        self.assertEqual(source.validate_observation(c, q, body, CUTOFF, "2026-09")["value"], -5.7)
        body = change_text(body, "同比下降5.7%", "同比下降-5.7%")
        self.assertNotIn(q["id"], {c["request_id"] for c in fiscal.reviewed_fiscal_candidates(body, actual_requests())})

    def test_treasury_source_allowed_only_on_exact_treasury_host(self):
        q, c, body = self.candidate()
        self.assertEqual(source.validate_observation(c, q, body, CUTOFF, "2026-09")["publisher_id"], "primary:gks.mof.gov.cn")
        external = change_text(body, "来源：国库司", "来源：国金证券")
        with self.assertRaisesRegex(ValueError, "primary_domain_republished_source"):
            source._source_proof(q, external, c["quote"])
        body["url"] = "https://regional.mof.gov.cn/a"
        with self.assertRaisesRegex(ValueError, "primary_domain_republished_source"):
            source._source_proof(q, body, c["quote"])

    def test_release_header_overrides_earlier_url_date_not_site_calendar(self):
        raw = ("<html><title>2026年1-7月财政收支情况</title><body>"
               "<p>2017年11月21日 星期二</p><h1>2026年1-7月财政收支情况</h1>"
               "<p>2026年8月21日 来源：国库司</p></body></html>")
        url = "https://gks.mof.gov.cn/tongjishuju/202608/t20260814_3995497.htm"
        page = source.parse_page(raw, url)
        self.assertEqual(page["published_at"], "2026-08-21")
        self.assertEqual(page["publication_date_basis"], "reviewed_treasury_article_header")
        unrelated = source.parse_page(raw.replace("财政收支情况", "无关网页"), url)
        self.assertNotEqual(unrelated["publication_date_basis"], "reviewed_treasury_article_header")


if __name__ == "__main__":
    unittest.main()
