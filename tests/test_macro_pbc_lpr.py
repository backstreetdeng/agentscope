import copy
from datetime import date
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import unittest

PROJECT = Path(__file__).resolve().parents[1]
SCRIPTS = PROJECT / "skills/macro-monthly-report/scripts"


def load(name):
    spec = importlib.util.spec_from_file_location("lpr_tests_" + name, SCRIPTS / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


lpr = load("macro_pbc_lpr")
sources = load("macro_sources")


def requests():
    return [{"id": "s30-shape18::" + name, "chart_id": "s30-shape18", "series_name": name,
             "definition": "贷款市场报价利率LPR：" + name,
             "definition_aliases": sorted(aliases), "unit": "%", "frequency": "announcement_monthly"}
            for name, (aliases, _, _) in lpr.ROLES.items()]


def original(day="2026-09-20", one="3.0", five="3.5", percent="%"):
    year, month, date = [int(v) for v in day.split("-")]
    chinese = f"{year}年{month}月{date}日"
    title = chinese + "全国银行间同业拆借中心受权公布贷款市场报价利率（LPR）公告"
    statement = (f"中国人民银行授权全国银行间同业拆借中心公布，{chinese}贷款市场报价利率（LPR）为："
                 f"1年期LPR为{one}{percent}，5年期以上LPR为{five}{percent}。以上LPR在下一次发布LPR之前有效。")
    html = (f'<html><meta name="PublishDate" content="{day}"><title>{title}</title>'
            f'<h1>{title}</h1><p>文章来源：</p><p>{day} 09:00:00</p><p>{statement}</p></html>')
    url = "https://www.pbc.gov.cn/zhengcehuobisi/125207/125213/125440/3876551/" + day.replace("-", "") + "084942122562/index.html"
    page = sources.parse_page(html, url)
    page["text_sha256"] = sha256(page["text"].encode()).hexdigest()
    page["receipt_id"] = "synthetic-lpr-fixture"
    return page


def changed_text(page, old, new):
    page = copy.deepcopy(page)
    page["text"] = page["text"].replace(old, new)
    page["text_sha256"] = sha256(page["text"].encode()).hexdigest()
    return page


class PbcLprTests(unittest.TestCase):
    def test_two_tenors_explicit_percent_and_original_publication_timestamp(self):
        page = original()
        candidates = lpr.reviewed_lpr_candidates(page, requests(), "2026-10-03", "2026-09")
        self.assertEqual([c["value"] for c in candidates], [3.0, 3.5])
        for candidate, request in zip(candidates, requests()):
            self.assertEqual(candidate["period"], "2026-09-20")
            self.assertEqual(candidate["unit"], "%")
            proof = candidate["pbc_lpr_proof"]
            self.assertEqual(proof["publication_quote"], "2026-09-20 09:00:00")
            self.assertEqual(page["text"][proof["value_start"]:proof["value_end"]], candidate["value_text"])
            self.assertEqual(page["text"][proof["unit_start"]:proof["unit_end"]], "%")
            verified = lpr.verify_lpr_candidate(candidate, request, page, "2026-10-03", "2026-09")
            self.assertEqual(verified["observation_kind"], "actual")
            self.assertTrue(verified["reviewed_period_and_definition"])
            self.assertIn(candidate["quote"], verified["semantic_text"])

    def test_actual_announcement_day_not_forced_to_twentieth_and_not_year_fixed(self):
        page = original("2027-06-22")
        candidates = lpr.reviewed_lpr_candidates(page, requests(), "2027-10-03", "2027-09")
        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0]["period"], "2027-06-22")
        lpr.verify_lpr_candidate(candidates[0], requests()[0], page)
        forged = copy.deepcopy(candidates[0])
        forged["period"] = "2027-06-20"
        with self.assertRaises(ValueError):
            lpr.verify_lpr_candidate(forged, requests()[0], page)

    def test_fullwidth_percent_is_literal_unit_variant(self):
        page = original(percent="％")
        candidate = lpr.reviewed_lpr_candidates(page, requests())[0]
        self.assertEqual(candidate["pbc_lpr_proof"]["unit_quote"], "％")
        self.assertEqual(candidate["unit"], "%")
        lpr.verify_lpr_candidate(candidate, requests()[0], page)

    def test_request_whitelist_rejects_frequency_unit_and_five_year_without_above(self):
        request = requests()[1]
        for change in [{"frequency":"monthly"}, {"unit":"基点"}, {"chart_id":"s26-shape11"},
                       {"definition_aliases":["5年期LPR", "5年期"]}, {"definition":"SHIBOR：5年"},
                       {"series_name":"政策利率:5年"}]:
            altered = dict(request, **change)
            self.assertEqual(lpr.reviewed_lpr_candidates(original(), [altered]), [])

    def test_bps_shibor_policy_rate_and_missing_tenor_not_substituted(self):
        page = original()
        for before, after in [("3.0%", "300基点"), ("LPR", "SHIBOR"),
                              ("贷款市场报价利率", "政策利率"), ("5年期以上LPR", "5年期LPR"),
                              ("5年期以上LPR为3.5%", "5年期以上LPR暂无报价")]:
            self.assertEqual(lpr.reviewed_lpr_candidates(changed_text(page, before, after), requests()), [])

    def test_different_heading_publication_day_and_authorized_body_day_rejected(self):
        page = original()
        bad_heading = changed_text(page, "2026年9月20日全国", "2026年8月20日全国")
        bad_body = changed_text(page, "公布，2026年9月20日", "公布，2026年9月21日")
        bad_publication = changed_text(page, "2026-09-20 09:00:00", "2026-09-19 09:00:00")
        for altered in [bad_heading, bad_body, bad_publication, dict(page, published_at="2026-09-19")]:
            self.assertEqual(lpr.reviewed_lpr_candidates(altered, requests()), [])

    def test_missing_or_multiple_original_body_or_publication_dates_are_not_guessed(self):
        page = original()
        candidate = lpr.reviewed_lpr_candidates(page, requests())[0]
        for old, new in [(candidate["quote"], candidate["quote"] * 2),
                         ("2026-09-20 09:00:00", ""),
                         ("2026-09-20 09:00:00", "2026-09-20 09:00:00 2026-09-20 10:00:00")]:
            self.assertEqual(lpr.reviewed_lpr_candidates(changed_text(page, old, new), requests()), [])

    def test_integrity_publisher_and_cutoff_guards(self):
        page = original()
        for change in [{"url":"https://evil.test/lpr.html"}, {"url":"http://www.pbc.gov.cn/lpr.html"},
                       {"url":"https://www.pbc.gov.cn/zhengcehuobisi/index.html"}, {"text_sha256":"fake"},
                       {"truncated":True}, {"text":page["text"] + "changed"}]:
            self.assertEqual(lpr.reviewed_lpr_candidates(dict(page, **change), requests()), [])
        self.assertEqual(lpr.reviewed_lpr_candidates(page, requests(), cutoff_date="2026-09-19"), [])
        self.assertEqual(lpr.reviewed_lpr_candidates(page, requests(), report_month="2026-08"), [])

    def test_arbitrary_candidates_offsets_and_swapped_tenor_rejected(self):
        page, request = original(), requests()[0]
        candidate = lpr.reviewed_lpr_candidates(page, [request])[0]
        for change in [{"value":3.5}, {"value":True}, {"value":float("inf")}, {"value_text":"3"},
                       {"period":"2026-09"}, {"unit":"基点"}, {"request_id":"other"},
                       {"published_at":"2026-09-21"}, {"definition_quote":"5年期以上LPR为3.5%"}]:
            forged = copy.deepcopy(candidate)
            forged.update(change)
            with self.assertRaises(ValueError):
                lpr.verify_lpr_candidate(forged, request, page)
        for change in [{"value_start":True}, {"value_start":-1}, {"value_end":99}, {"tenor":"5年期以上"},
                       {"unit_quote":"基点"}, {"publication_quote":"2026-09-20"}, {"profile":"unreviewed"}]:
            forged = copy.deepcopy(candidate)
            forged["pbc_lpr_proof"].update(change)
            with self.assertRaises(ValueError):
                lpr.verify_lpr_candidate(forged, request, page)

    def test_announcement_not_inferred_from_url_or_directory_dates(self):
        page = original()
        page["url"] = page["url"].replace("202609200849", "202609170849")
        candidate = lpr.reviewed_lpr_candidates(page, requests())[0]
        self.assertEqual(candidate["period"], "2026-09-20")
        lpr.verify_lpr_candidate(candidate, requests()[0], page)

    def test_real_july_august_september_original_receipts_and_contract(self):
        cache = PROJECT / ".work/macro-public-run/codex-run-v3/working/macro-sources/pages"
        contract = PROJECT / "runtime/skill-runs/macro-20261004-005541-c8ad8701/working/template-contract.json"
        if not cache.exists() or not contract.exists():
            self.skipTest("Saved official LPR receipts and real contract required for local replay")
        real_requests = [r for r in json.loads(contract.read_text(encoding="utf-8"))["source_requests"]
                         if r["chart_id"] == "s30-shape18"]
        self.assertEqual(len(real_requests), 2)
        files = ["f42cde4ed98648fc00ff0b59b1599e720ef244e53632f82ae2f4866d669094e4",
                 "a0971952d6b25d3256e30a81fa8ab4067f5f807a5bd1f0caf9c762243bc1a1ec",
                 "1df225a6472cea027405e45926bb49ab8309748c0f1015a1875750b582c3f6d0"]
        verified = set()
        for stem in files:
            page = json.loads((cache / (stem + ".json")).read_text(encoding="utf-8"))
            candidates = lpr.reviewed_lpr_candidates(page, real_requests, "2026-10-03", "2026-09")
            self.assertEqual(len(candidates), 2)
            self.assertEqual([c["value"] for c in candidates], [3.0, 3.5])
            for candidate, request in zip(candidates, real_requests):
                result = lpr.verify_lpr_candidate(candidate, request, page, "2026-10-03", "2026-09")
                self.assertEqual(candidate["period"], page["published_at"])
                self.assertEqual(candidate["pbc_lpr_proof"]["publication_quote"], page["published_at"] + " 09:00:00")
                self.assertTrue(result["reviewed_period_and_definition"])
                verified.add((candidate["request_id"], candidate["period"]))
        self.assertEqual(len(verified), 6)
        self.assertEqual({period for _,period in verified}, {"2026-07-20","2026-08-20","2026-09-20"})


class PbcLprCoreTests(unittest.TestCase):
    def test_core_original_tenors_days_and_fullwidth_unit_replay(self):
        for percent in ("%", "％"):
            page = original(percent=percent)
            for q, c in zip(requests(), lpr.reviewed_lpr_candidates(page, requests())):
                q.update(source_domains=["pbc.gov.cn"], original_publisher_domains=["pbc.gov.cn"],
                         context_groups=[["贷款市场报价利率", "LPR"]])
                result = sources.validate_observation(c, q, page, date(2026, 10, 3), "2026-09")
                self.assertEqual(result, sources.validate_observation(result, q, page, date(2026, 10, 3), "2026-09"))
                self.assertEqual(result["period"], "2026-09-20")
                self.assertEqual(result["observation_kind"], "actual")
                self.assertEqual(result["pbc_lpr_proof"], c["pbc_lpr_proof"])

    def test_core_cannot_swap_tenor_bps_date_or_value(self):
        page = original(); q = requests()[0]
        q.update(source_domains=["pbc.gov.cn"], original_publisher_domains=["pbc.gov.cn"])
        c = lpr.reviewed_lpr_candidates(page, [q])[0]
        result = sources.validate_observation(c, q, page, date(2026, 10, 3), "2026-09")
        for change in ({"period": "2026-09-21"}, {"value": 3.5}, {"unit": "基点"}):
            with self.assertRaises(ValueError):
                sources.validate_observation({**result, **change}, q, page, date(2026, 10, 3), "2026-09")


if __name__ == "__main__":
    unittest.main()
