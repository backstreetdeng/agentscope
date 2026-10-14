"""Exercise the production collector's gap recovery, without network or LLMs."""
import importlib.util
import json
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch
from urllib.error import HTTPError

PATH = Path(__file__).resolve().parents[1] / "skills/macro-monthly-report/scripts/macro_sources.py"
SPEC = importlib.util.spec_from_file_location("macro_recovery_test", PATH)
source = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(source)


def request(identifier="pmi", alias="PMI"):
    return {"id": identifier, "series_name": alias, "definition": "中国制造业" + alias,
            "definition_aliases": [alias], "unit": "指数", "frequency": "monthly",
            "source_domains": ["stats.gov.cn"], "original_publisher_domains": ["stats.gov.cn"],
            "query": "制造业PMI 原始统计数据", "template_latest_period": "2026-07", "history_count": 3}


def body(month=9, alias="PMI", suffix="good", value=49.4):
    raw = (f'<meta name="PublishDate" content="2026-{month:02d}-30">'
           '<p>中国制造业PMI统计发布</p><table><tr><th>时期</th><th>' + alias + '</th></tr>'
           f'<tr><td>2026年{month}月</td><td>{value}</td></tr></table>')
    page = source.parse_page(raw, f"https://www.stats.gov.cn/{suffix}.html")
    return {**page, "text_sha256": source.hashlib.sha256(page["text"].encode()).hexdigest()}


BAD = "https://www.stats.gov.cn/bad.html"


class MacroRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def collect(self, root, reqs, directory, fetch, search, month="2026-09", cutoff="2026-10-04"):
        progress = AsyncMock()
        with patch.object(source, "_official_discovery", AsyncMock(return_value=directory)), \
             patch.object(source, "_fetch_page", fetch), patch.object(source, "_search_candidates", search), \
             patch.object(source, "_extract_page_observations", AsyncMock(side_effect=AssertionError("draft must not use LLM"))):
            result = await source.collect_sources(month, cutoff, reqs, root, public_draft=True, progress=progress)
        return result, progress

    def directory(self, reqs, url=BAD, restricted=False):
        return {"by_request": {req["id"]: {"items": [{"url": url}],
            **({"source_restrictions": {"exclusive_reviewed_discovery": True, "allowed_source_urls": [url]}}
               if restricted else {})} for req in reqs}}

    async def test_directory_404_drives_new_search_and_preserves_error_status(self):
        good = body()
        def fetch(url, domains):
            if url == BAD:
                raise HTTPError(url, 404, "not found", {}, None)
            return good
        search = AsyncMock(return_value={"items": [{"url": good["url"], "highlights": "untrusted 999"}]})
        with TemporaryDirectory() as root:
            result, progress = await self.collect(root, [request()], self.directory([request()]), AsyncMock(side_effect=fetch), search)
            self.assertEqual(result["coverage"], {"required": 1, "verified": 1})
            self.assertEqual(search.await_count, 1)
            self.assertEqual(result["observations"][0]["value"], 49.4)
            self.assertTrue(any(item.get("http_status") == 404 for item in result["issues"]))
            self.assertTrue(any("缺项补证" in call.args[0] for call in progress.await_args_list))
            self.assertTrue(list((Path(root) / "working/macro-sources/recovery").glob("*.json")))

    async def test_login_redirect_is_not_misreported_as_publication_failure(self):
        login = {"url": "https://www.stats.gov.cn/SSO/Login.aspx?token=opaque", "text": "请登录",
                 "published_at": "", "tables": []}
        good = body()
        fetch = AsyncMock(side_effect=lambda url, domains: login if url == BAD else good)
        with TemporaryDirectory() as root:
            result, _ = await self.collect(root, [request()], self.directory([request()]), fetch,
                                          AsyncMock(return_value={"items": [{"url": good["url"]}]}))
            self.assertEqual(result["status"], "ready")
            self.assertTrue(any(item["code"] == "source_authentication_required" for item in result["issues"]))
            self.assertFalse(any(item["code"] == "publication_date_unverified" for item in result["issues"]))

    async def test_parser_gap_targets_only_missing_request_and_keeps_verified_value(self):
        first = body()
        second = body(alias="Other PMI", suffix="other", value=51.0)
        reqs = [request(), request("other", "Other PMI")]
        fetch = AsyncMock(side_effect=lambda url, domains: first if url == first["url"] else second)
        with TemporaryDirectory() as root:
            result, _ = await self.collect(root, reqs, self.directory(reqs, first["url"]), fetch,
                AsyncMock(return_value={"items": [{"url": second["url"]}]}))
            self.assertEqual(result["coverage"]["verified"], 2)
            self.assertEqual({item["request_id"]: item["value"] for item in result["observations"]}, {"pmi": 49.4, "other": 51.0})
            self.assertEqual(result["retrieval_trace"][0]["request_ids"], ["other"])
            self.assertEqual(fetch.await_count, 2)

    async def test_empty_search_is_bounded_and_does_not_restart_directory(self):
        fetch = AsyncMock(side_effect=HTTPError(BAD, 404, "not found", {}, None))
        search = AsyncMock(return_value={"items": []})
        with TemporaryDirectory() as root:
            result, _ = await self.collect(root, [request()], self.directory([request()]), fetch, search)
            self.assertEqual(fetch.await_count, 1)
            self.assertEqual(search.await_count, source.MAX_EVIDENCE_RECOVERY_ROUNDS)
            self.assertEqual(len(result["retrieval_trace"]), 3)
            self.assertEqual(result["coverage"]["verified"], 0)
            self.assertTrue(any(item["code"] == "public_retrieval_unresolved" for item in result["issues"]))

    async def test_repeated_bad_urls_do_not_crowd_out_new_candidates(self):
        good = body()
        def fetch(url, domains):
            if url == BAD:
                raise HTTPError(url, 404, "not found", {}, None)
            return good
        fetch = AsyncMock(side_effect=fetch)
        search = AsyncMock(return_value={"items": [{"url": BAD}] * 4 + [{"url": good["url"]}]})
        with TemporaryDirectory() as root:
            result, _ = await self.collect(root, [request()], self.directory([request()]), fetch, search)
            self.assertEqual(result["status"], "ready")
            self.assertEqual([call.args[0] for call in fetch.await_args_list], [BAD, good["url"]])

    async def test_resume_replays_successful_recovery_without_research_or_refetch(self):
        good = body()
        invalid = {**body(suffix="bad"), "tables": [], "text": "发布时间：2026-09-30。目录页面",
                   "published_at": "2026-09-30"}
        fetch = AsyncMock(side_effect=lambda url, domains: invalid if url == BAD else good)
        search = AsyncMock(return_value={"items": [{"url": good["url"]}]})
        with TemporaryDirectory() as root:
            first, _ = await self.collect(root, [request()], self.directory([request()]), fetch, search)
            second, _ = await self.collect(root, [request()], self.directory([request()]), fetch, search)
            self.assertEqual(first["status"], second["status"])
            self.assertEqual(second["status"], "ready")
            self.assertEqual(fetch.await_count, 2)  # one directory, one original report across both runs
            self.assertEqual(search.await_count, 1)
            self.assertTrue(second["retrieval_trace"][0]["discovery_reused"])

    async def test_exclusive_reviewed_vintage_cannot_be_bypassed(self):
        search = AsyncMock(side_effect=AssertionError("generic discovery forbidden"))
        fetch = AsyncMock(side_effect=HTTPError(BAD, 404, "not found", {}, None))
        with TemporaryDirectory() as root:
            result, _ = await self.collect(root, [request()], self.directory([request()], restricted=True), fetch, search)
            self.assertEqual(result["coverage"]["verified"], 0)
            search.assert_not_called()
            self.assertTrue(any(item["code"] == "reviewed_discovery_restricted" for item in result["issues"]))

    async def test_failed_recovery_search_does_not_discard_data_and_resume_retries_it(self):
        good = body()
        invalid = {**body(suffix="bad"), "tables": [], "text": "目录页面", "published_at": "2026-09-30"}
        fetch = AsyncMock(side_effect=lambda url, domains: invalid if url == BAD else good)
        failed = AsyncMock(side_effect=TimeoutError("search timeout"))
        with TemporaryDirectory() as root:
            first, _ = await self.collect(root, [request()], self.directory([request()]), fetch, failed)
            self.assertEqual(first["status"], "blocked")
            self.assertEqual(failed.await_count, 3)
            self.assertTrue(all(item["search_issues"][0]["code"] == "evidence_recovery_search_failed"
                                for item in first["retrieval_trace"]))
            working = AsyncMock(return_value={"items": [{"url": good["url"]}]})
            second, _ = await self.collect(root, [request()], self.directory([request()]), fetch, working)
            self.assertEqual(second["status"], "ready")
            self.assertEqual(working.await_count, 1)
            self.assertEqual(fetch.await_count, 2)

    async def test_single_secondary_issuer_triggers_independent_corroboration_search(self):
        req = {**request(), "secondary_source_domains": ["broker-a.test", "broker-b.test"],
               "secondary_publishers": {
                   "broker-a.test": [{"publisher_id": "broker-a", "names": ["Broker Alpha"]}],
                   "broker-b.test": [{"publisher_id": "broker-b", "names": ["Broker Beta"]}]},
               "origin_attribution_aliases": ["国家统计局"]}
        def report(host, issuer):
            raw = ('<meta name="PublishDate" content="2026-09-30">'
                   f'<p>Report by: {issuer} Data source: 国家统计局</p>'
                   '<table><tr><th>时期</th><th>PMI</th></tr>'
                   '<tr><td>2026年9月</td><td>49.4</td></tr></table>')
            return source.parse_page(raw, f"https://{host}/report.html")
        first = report("broker-a.test", "Broker Alpha")
        second = report("broker-b.test", "Broker Beta")
        search = AsyncMock(side_effect=[{"items": [{"url": first["url"]}]},
                                       {"items": [{"url": first["url"]}]},
                                       {"items": [{"url": second["url"]}]}])
        fetch = AsyncMock(side_effect=lambda url, domains: first if url == first["url"] else second)
        with TemporaryDirectory() as root:
            result, _ = await self.collect(root, [req], self.directory([req], first["url"]), fetch, search)
            self.assertEqual(result["status"], "ready")
            self.assertEqual(result["observations"][0]["corroborating_publishers"], ["broker-a", "broker-b"])
            self.assertEqual(fetch.await_count, 2)
            self.assertEqual(search.await_count, 3)
            self.assertIn("site:broker-b.test", search.await_args.args[0])

    async def test_snippet_or_future_publication_does_not_fill_gap(self):
        future = {**body(), "published_at": "2026-11-01"}
        search = AsyncMock(return_value={"items": [{"url": future["url"], "highlights": "2026年9月PMI 999"}]})
        fetch = AsyncMock(side_effect=lambda url, domains: future)
        with TemporaryDirectory() as root:
            result, _ = await self.collect(root, [request()], self.directory([request()]), fetch, search)
            self.assertEqual(result["observations"], [])
            self.assertTrue(any(item["code"] == "publication_after_cutoff" for item in result["issues"]))

    async def test_new_report_month_uses_new_query_and_does_not_relabel_old_values(self):
        september = body()
        october = {**body(month=10, suffix="october", value=50.7), "published_at": "2026-10-31"}
        fetch = AsyncMock(side_effect=lambda url, domains: october if url == october["url"] else september)
        search = AsyncMock(return_value={"items": [{"url": october["url"]}]})
        with TemporaryDirectory() as root:
            first, _ = await self.collect(root, [request()], self.directory([request()], september["url"]), fetch, search,
                                          cutoff="2026-11-04")
            second, _ = await self.collect(root, [request()], self.directory([request()], september["url"]), fetch, search,
                                           month="2026-10", cutoff="2026-11-04")
            self.assertEqual(first["status"], "ready")
            self.assertEqual(second["status"], "ready")
            self.assertEqual({item["period"]: item["value"] for item in second["observations"]}, {"2026-09": 49.4, "2026-10": 50.7})
            self.assertIn("2026年10月", search.await_args.args[0])

    def test_queries_have_different_strategies_and_run_specific_period(self):
        queries = source._gap_discovery_queries({"requests": [request()]}, "2026-10", date(2026, 11, 4))
        self.assertEqual(len({query for _, query in queries}), 3)
        self.assertTrue(all("2026年10月" in query or "October 2026" in query for _, query in queries))


if __name__ == "__main__":
    unittest.main()
