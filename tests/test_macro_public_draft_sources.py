"""Draft collection policy tests; offline fixtures, not live PPT acceptance."""
from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch


SCRIPTS = Path(__file__).resolve().parents[1] / "skills/macro-monthly-report/scripts"
SPEC = importlib.util.spec_from_file_location("public_draft_policy_sources", SCRIPTS / "macro_sources.py")
source = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(source)


def prose_request():
    return {"id": "pmi", "series_name": "制造业采购经理指数", "definition": "中国制造业采购经理指数",
            "definition_aliases": ["制造业采购经理指数"], "unit": "指数", "frequency": "monthly",
            "source_domains": ["stats.gov.cn"], "query": "site:stats.gov.cn 2026年8月 制造业采购经理指数",
            "template_latest_period": "2026-03", "release_lag_days": 30}


def prose_page():
    text = "发布时间：2026-08-31。2026年8月份制造业采购经理指数为49.4，比上月上升0.1个百分点。"
    return {"url": "https://www.stats.gov.cn/sj/zxfb/202608/t20260831_1.html",
            "text": text, "published_at": "2026-08-31", "publication_date_basis": "page_publication_label",
            "receipt_id": "unit-original", "text_sha256": source.hashlib.sha256(text.encode()).hexdigest(),
            "tables": [], "truncated": False}


def prose_observation():
    return {"request_id": "pmi", "period": "2026-08", "value": 49.4, "unit": "指数",
            "definition": "中国制造业采购经理指数", "quote": "2026年8月份制造业采购经理指数为49.4",
            "period_quote": "2026年8月份", "definition_quote": "制造业采购经理指数", "value_text": "49.4"}


def cpi_request(identifier="s21-shape12::同比::category0", metric="同比"):
    return {"id": identifier, "chart_id": "s21-shape12", "series_name": metric,
            "definition": f"CPI分类同比环比：食品：{metric}", "definition_aliases": ["食品价格"],
            "context_groups": [["居民消费价格", "CPI"], [metric]], "unit": "%", "frequency": "monthly",
            "source_domains": ["stats.gov.cn"], "original_publisher_domains": ["stats.gov.cn"],
            "query": "CPI分类同比环比 最新发布 原始历史数据 (site:stats.gov.cn)",
            "template_latest_period": "2026-07", "history_count": 13, "category_index": 0}


def cpi_page(month):
    raw = f'''<html><meta name="PublishDate" content="2026-{month + 1:02d}-09">
    <p>2026年{month}月份，全国居民消费价格同比上涨0.8%。</p>
    <p>2026年{month}月份居民消费价格主要数据</p><table>
    <tr><th></th><th>环比涨跌幅（%）</th><th>同比涨跌幅（%）</th><th>1—{month}月 同比涨跌幅（%）</th></tr>
    <tr><td>其中：食品</td><td>0.4</td><td>-1.4</td><td>-0.8</td></tr>
    <tr><td>一、食品烟酒及在外餐饮</td><td>0.3</td><td>-0.7</td><td>-0.3</td></tr></table></html>'''
    page = source.parse_page(raw, f"https://www.stats.gov.cn/sj/zxfbhjd/2026{month + 1:02d}/t2026{month + 1:02d}09_1965263.html")
    return {**page, "receipt_id": f"unit-cpi-{month}",
            "text_sha256": source.hashlib.sha256(page["text"].encode()).hexdigest(), "fetch_provider": "offline-unit-fixture"}


class PublicDraftSourcesTest(unittest.IsolatedAsyncioTestCase):
    async def test_draft_never_calls_external_locator_or_training_supplements(self):
        req = cpi_request()
        page = cpi_page(8)
        with TemporaryDirectory() as root, \
             patch.object(source, "_official_discovery", AsyncMock(return_value={"by_request": {
                 req["id"]: {"items": [{"url": page["url"]}]}}})) as discover, \
             patch.object(source, "_fetch_page", AsyncMock(return_value=page)), \
             patch.object(source, "_extract_page_observations", AsyncMock(side_effect=AssertionError("draft locator forbidden"))) as locator, \
             patch.object(source, "_history_hint", side_effect=AssertionError("draft training history forbidden")) as history, \
             patch.object(source, "_search_candidates", AsyncMock(side_effect=AssertionError("official table already located"))) as search:
            result = await source.collect_sources("2026-09", "2026-10-03", [req], root, public_draft=True,
                model_config={"extract_observations": AsyncMock(side_effect=AssertionError("model callback forbidden"))})
            self.assertEqual(result["status"], "ready")
            self.assertEqual(result["coverage"]["verified"], 1)
            self.assertEqual(result["request_status"][req["id"]]["required_observations"], 1)
            self.assertEqual(discover.await_args.args[0][0]["history_count"], 3)
            self.assertEqual(req["history_count"], 13)  # contract is not mutated
            self.assertEqual(result["delivery_mode"], "public_draft")
            self.assertTrue(result["collection_policy"]["deterministic_only"])
            self.assertFalse(result["collection_policy"]["prediction_history_supplements"])
            locator.assert_not_called()
            history.assert_not_called()
            search.assert_not_called()

    async def test_reviewed_directory_is_bounded_to_three_latest_pages(self):
        req = cpi_request()
        pages = {cpi_page(month)["url"]: cpi_page(month) for month in (8, 7, 6, 5, 4)}
        with TemporaryDirectory() as root, \
             patch.object(source, "_official_discovery", AsyncMock(return_value={"by_request": {
                 req["id"]: {"items": [{"url": url} for url in pages]}}})), \
             patch.object(source, "_fetch_page", AsyncMock(side_effect=lambda url, domains: pages[url])) as fetch, \
             patch.object(source, "_extract_page_observations", AsyncMock(side_effect=AssertionError("no locator"))):
            result = await source.collect_sources("2026-09", "2026-10-03", [req], root, public_draft=True)
            self.assertEqual(fetch.await_count, 3)
            self.assertEqual([call.args[0] for call in fetch.await_args_list], list(pages)[:3])
            self.assertEqual({item["period"] for item in result["observations"]}, {"2026-08", "2026-07", "2026-06"})

    async def test_shared_page_retains_multiple_indicator_requests(self):
        reqs = [cpi_request(), cpi_request("s21-shape12::环比::category0", "环比")]
        page = cpi_page(8)
        official = {"by_request": {req["id"]: {"items": [{"url": page["url"]}]} for req in reqs}}
        with TemporaryDirectory() as root, patch.object(source, "_official_discovery", AsyncMock(return_value=official)), \
             patch.object(source, "_fetch_page", AsyncMock(return_value=page)) as fetch, \
             patch.object(source, "_extract_page_observations", AsyncMock(side_effect=AssertionError("no locator"))):
            result = await source.collect_sources("2026-09", "2026-10-03", reqs, root, public_draft=True)
            self.assertEqual(result["coverage"], {"required": 2, "verified": 2})
            self.assertEqual(fetch.await_count, 1)
            self.assertEqual({item["request_id"] for item in result["observations"]}, {req["id"] for req in reqs})

    async def test_shared_query_cannot_extend_another_requests_three_page_scope(self):
        reqs = [cpi_request(), cpi_request("s21-shape12::环比::category0", "环比")]
        pages = {month: cpi_page(month) for month in (8, 7, 6, 5, 4)}
        scope = {reqs[0]["id"]: (8, 7, 6, 5), reqs[1]["id"]: (8, 6, 5, 4)}
        official = {"by_request": {identifier: {"items": [{"url": pages[month]["url"]} for month in months]}
                                  for identifier, months in scope.items()}}
        by_url = {page["url"]: page for page in pages.values()}
        with TemporaryDirectory() as root, patch.object(source, "_official_discovery", AsyncMock(return_value=official)), \
             patch.object(source, "_fetch_page", AsyncMock(side_effect=lambda url, domains: by_url[url])) as fetch, \
             patch.object(source, "_extract_page_observations", AsyncMock(side_effect=AssertionError("no locator"))):
            result = await source.collect_sources("2026-09", "2026-10-03", reqs, root, public_draft=True)
            self.assertEqual(result["coverage"], {"required": 2, "verified": 2})
            self.assertEqual(fetch.await_count, 4)  # unique union of each request's three pages
            for identifier, months in scope.items():
                self.assertEqual({item["period"] for item in result["observations"] if item["request_id"] == identifier},
                                 {f"2026-{month:02d}" for month in months[:3]})

    async def test_missing_deterministic_value_remains_explicit_gap_with_search(self):
        page = prose_page()
        with TemporaryDirectory() as root, patch.object(source, "_official_discovery", AsyncMock(return_value={"by_request": {}})), \
             patch.object(source, "_search_candidates", AsyncMock(return_value={"items": [{"url": page["url"]}]})) as search, \
             patch.object(source, "_fetch_page", AsyncMock(return_value=page)), \
             patch.object(source, "_extract_page_observations", AsyncMock(side_effect=AssertionError("no locator"))) as locator:
            result = await source.collect_sources("2026-08", "2026-10-03", [prose_request()], root, public_draft=True)
            self.assertEqual(result["coverage"]["verified"], 0)
            self.assertEqual(result["request_status"]["pmi"]["status"], "missing")
            self.assertTrue(any(item["code"] == "public_draft_deterministic_observation_missing" for item in result["issues"]))
            self.assertGreater(search.await_count, 0)
            locator.assert_not_called()

    async def test_formal_default_still_calls_locator_and_draft_cannot_reuse_it(self):
        page = prose_page()
        with TemporaryDirectory() as root, patch.object(source, "_official_discovery", AsyncMock(return_value={"by_request": {}})), \
             patch.object(source, "_search_candidates", AsyncMock(return_value={"items": [{"url": page["url"]}]})) as search, \
             patch.object(source, "_fetch_page", AsyncMock(return_value=page)) as fetch, \
             patch.object(source, "_extract_page_observations", AsyncMock(return_value=[prose_observation()])) as locator:
            formal = await source.collect_sources("2026-08", "2026-10-03", [prose_request()], root)
            draft = await source.collect_sources("2026-08", "2026-10-03", [prose_request()], root, public_draft=True)
            self.assertEqual(formal["status"], "ready")
            self.assertEqual(formal["delivery_mode"], "formal")
            self.assertEqual(draft["coverage"]["verified"], 0)
            self.assertEqual(locator.await_count, 1)
            self.assertEqual(fetch.await_count, 1)  # literal original receipt can be reused
            self.assertEqual(len(list((Path(root) / "working/macro-sources/extractions").glob("*.json"))), 2)
            self.assertGreaterEqual(search.await_count, 2)  # discovery caches are mode-isolated

    async def test_draft_keeps_freshness_and_same_definition_acceptance(self):
        req = cpi_request()
        page = cpi_page(6)
        with TemporaryDirectory() as root, patch.object(source, "_official_discovery", AsyncMock(return_value={"by_request": {
            req["id"]: {"items": [{"url": page["url"]}]}}})), \
             patch.object(source, "_fetch_page", AsyncMock(return_value=page)), \
             patch.object(source, "_search_candidates", AsyncMock(return_value={"items": []})):
            result = await source.collect_sources("2026-09", "2026-10-03", [req], root, public_draft=True)
            self.assertEqual(result["coverage"]["verified"], 0)
            self.assertEqual(result["request_status"][req["id"]]["status"], "stale")
            self.assertTrue(any(item["code"] == "latest_actual_below_freshness_minimum" for item in result["issues"]))

    async def test_nonboolean_mode_is_rejected(self):
        with TemporaryDirectory() as root, self.assertRaisesRegex(ValueError, "boolean"):
            await source.collect_sources("2026-09", "2026-10-03", [], root, public_draft="true")


if __name__ == "__main__":
    unittest.main()
