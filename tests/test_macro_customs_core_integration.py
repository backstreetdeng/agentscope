"""Production collector + real package helpers, offline reviewed HTML fixtures.

Customs HTTP retrieval is mocked and unrelated discovery is stubbed empty.
Customs discovery, exact table readers, core validation, query persistence,
source restrictions and independent replay remain production.
These tests do not represent a live whole-report/PPT acceptance.
"""
import copy
from datetime import date
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1] / "skills/macro-monthly-report/scripts"
SPEC = importlib.util.spec_from_file_location("customs_core_integration_sources", ROOT / "macro_sources.py")
source = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(source)
discovery = source._load_package_helper("macro_customs_discovery")
ordinary = source._load_package_helper("macro_official_discovery")

BALANCE_NAME = "贸易差额(亿美元)"
EXPORT_NAME = "出口金额:当月同比(%,右轴)"
IMPORT_NAME = "进口金额:当月同比(%,右轴)"
QUERY = "美元计价进出口 最新发布 原始历史数据 (site:customs.gov.cn)"
BALANCE_ID = "s19-shape13::" + BALANCE_NAME


def article_url(number):
    return f"http://english.customs.gov.cn/Statics/{number:08d}-1111-2222-3333-444444444444.html"


def requests():
    return [{"id": "s19-shape13::" + name, "chart_id": "s19-shape13", "series_name": name,
             "definition": "美元计价进出口：" + name, "definition_aliases": [alias],
             "context_groups": [["美元", "US dollar", "USD"]] + ([] if name == BALANCE_NAME else [["同比", "year-on-year"]]),
             "unit": "亿美元" if name == BALANCE_NAME else "%", "frequency": "monthly",
             "source_domains": ["customs.gov.cn"], "original_publisher_domains": ["customs.gov.cn"],
             "history_count": 3, "template_latest_period": "2026-07", "query": QUERY}
            for name, alias in [(BALANCE_NAME, "Balance"), (EXPORT_NAME, "Export"), (IMPORT_NAME, "Import")]]


def directory(family, links):
    return (f'<select id="{discovery.SELECTORS[family]}"><option value="2026">2026</option></select>'
            f'<table><tr><td>{discovery.DIRECTORY_TITLES[family]}</td><td>'
            + "".join(f'<a href="{article_url(number)}">{label}.</a>' for label, number in links)
            + '</td></tr></table>')


def balance_table(periods=("2026-06", "2026-07", "2026-08"), old=False):
    caption = "1.Summary of Imports and Exports (In USD) B：Monthly"
    values = {"2026-06": "125,623" if old else "125,467",
              "2026-07": "112,337" if old else "112,500",
              "2026-08": "119,076" if old else "119,085"}
    rows = "".join('<tr><td>' + period.replace("-", ".") + '</td>'
                   + '<td>700,000</td><td>400,000</td><td>300,000</td><td>' + values[period] + '</td>'
                   + '<td>5,000,000</td><td>3,000,000</td><td>2,000,000</td><td>1,000,000</td></tr>' for period in periods)
    return (f'<table><tr><td colspan="9">{caption}</td></tr><tr><td colspan="9">Unit:US$ million</td></tr>'
            '<tr><td rowspan="2">Year&amp;Month</td><td rowspan="2">Total</td><td rowspan="2">Export</td>'
            '<td rowspan="2">Import</td><td rowspan="2">Balance</td><td colspan="4">1to8</td></tr>'
            '<tr><td>Total</td><td>Export</td><td>Import</td><td>Balance</td></tr>' + rows + '</table>')


def wrap_article(caption, day, content):
    return (f'<div class="atcl"><div class="atcl-main"><div class="atcl-ttl">{caption}</div></div>'
            f'<div class="atcl-layout"><div class="atcl-main"><div class="atcl-date">{day}</div>'
            f'<div class="atcl-cnt">{content}</div></div></div></div>')


def balance_article(day="2026/09/18", periods=("2026-06", "2026-07", "2026-08"), old=False):
    return wrap_article("1.Summary of Imports and Exports (In USD) B：Monthly", day, balance_table(periods, old))


def trade_article(month, include_old_balance=False):
    name = discovery.MONTHS[month - 1]
    day = {6: "2026/07/15", 7: "2026/08/10", 8: "2026/09/09"}[month]
    caption = f"(2) China's Total Export &amp; Import Values by Trade Mode, {name} 2026 (in USD)"
    exp, imp = {6: ("27.0", "36.0"), 7: ("23.9", "27.5"), 8: ("25.0", "28.2")}[month]
    table = (f'<table><tr><td colspan="7">{caption}</td></tr><tr><td colspan="7">Unit: USD1 Million</td></tr>'
             f'<tr><td rowspan="2">Trade Mode</td><td colspan="3">{month}</td><td colspan="3">Year-on-Year (±%)</td></tr>'
             '<tr><td>Export &amp; Import</td><td>Export</td><td>Import</td><td>Export &amp; Import</td><td>Export</td><td>Import</td></tr>'
             f'<tr><td>Total Value</td><td>683,796.7</td><td>401,441.0</td><td>282,355.8</td><td>26.3</td><td>{exp}</td><td>{imp}</td></tr></table>')
    if include_old_balance:
        # Deliberately valid reader input for Balance on a preliminary URL.
        # Only the selected source family may authorize it; format alone is
        # not enough. Plain local caption/date preserve one real atcl header.
        table += ('<p>1.Summary of Imports and Exports (In USD) B：Monthly</p><p>' + day + '</p>' + balance_table(old=True))
    return wrap_article(caption, day, table)


def native_fixture_documents(latest_periods=("2026-06", "2026-07", "2026-08"), attack=False):
    docs = {
        discovery.DIRECTORIES["customs_trade_yoy"]: directory("customs_trade_yoy", [("Jun", 16), ("Jul", 17), ("Aug", 18)]),
        discovery.DIRECTORIES["customs_monthly_balance"]: directory("customs_monthly_balance", [("Jun", 6), ("Jul", 7), ("Aug", 8)]),
        article_url(6): balance_article("2026/07/22", old=True),
        article_url(7): balance_article("2026/08/18", old=True),
        article_url(8): balance_article(periods=latest_periods),
    }
    docs.update({article_url(month + 10): trade_article(month, include_old_balance=attack) for month in (6, 7, 8)})
    return docs


class CustomsProductionCollectorTests(unittest.IsolatedAsyncioTestCase):
    async def collect(self, docs=None, stale_query=False, directory_error=False):
        docs = docs or native_fixture_documents()
        reqs = requests()
        with TemporaryDirectory() as run:
            root = Path(run) / "working/macro-sources"
            if stale_query:
                group_key = source._hash({"query": QUERY, "domains": ["customs.gov.cn"], "cutoff": "2026-10-03"})
                source._save(root / "queries" / (group_key + ".json"), {
                    "provider": "old-generic-search", "items": [{"url": article_url(6), "title": "old balance"}],
                    "query": QUERY, "cutoff_date": "2026-10-03"})
            async def direct_fetch(url):
                html = docs[url]
                digest = sha256(html.encode()).hexdigest()
                return {"url": url, "requested_url": url, "raw_html": html, "raw_sha256": digest,
                        "html_sha256": digest, "fetched_at": "2026-10-04T00:00:00Z", "fetch_provider": "offline-test-fixture"}
            async def page_fetch(url, domains):
                page = source.parse_page(docs[url], url)
                return {**page, "fetch_provider": "offline-test-fixture", "fetched_at": "2026-10-04T00:00:00Z"}
            with patch.object(ordinary, "discover_official_sources", new=AsyncMock(return_value={"by_request": {}})), \
                 patch.object(discovery, "_fetch", side_effect=direct_fetch), \
                 patch.object(source, "_fetch_page", side_effect=page_fetch) as fetch_page, \
                 patch.object(source, "_search_candidates", new=AsyncMock(side_effect=AssertionError("generic search forbidden"))) as search, \
                 patch.object(source, "_extract_page_observations", new=AsyncMock(side_effect=AssertionError("LLM locator not required"))) as locator:
                if directory_error:
                    with patch.object(discovery, "discover_customs_sources", new=AsyncMock(side_effect=RuntimeError("official directory offline"))):
                        result = await source.collect_sources("2026-09", "2026-10-03", reqs, run)
                else:
                    result = await source.collect_sources("2026-09", "2026-10-03", reqs, run)
                fetched = [call.args[0] for call in fetch_page.call_args_list]
                search.assert_not_called()
                locator.assert_not_called()
            pages = {page["receipt_id"]: page for page in [json.loads(path.read_text(encoding="utf-8")) for path in (root / "pages").glob("*.json")]}
            actual_queries = [json.loads(path.read_text(encoding="utf-8")) for path in (root / "queries").glob("*.json")]
            original_discovery = json.loads((root / "official-discovery.json").read_text(encoding="utf-8"))
            replay = source.verify_source_corroboration(result, {"source_requests": reqs}, pages)
        return result, pages, fetched, actual_queries, original_discovery, replay

    async def test_all_three_requests_use_production_readers_and_double_replay(self):
        result, pages, fetched, _, official, replay = await self.collect()
        self.assertEqual(result["coverage"], {"required": 3, "verified": 3})
        self.assertEqual(result["status"], "ready")
        self.assertEqual(len(result["observations"]), 9)
        self.assertEqual(replay["observations"], result["observations"])
        self.assertEqual(replay["issues"], [])
        self.assertEqual(set(fetched), {article_url(8), article_url(16), article_url(17), article_url(18)})
        self.assertEqual(official["customs_discovery"]["balance_selection_proof"]["selected_url"], article_url(8))
        balance = [row for row in result["observations"] if row["request_id"] == BALANCE_ID]
        self.assertEqual([(row["period"], row["value"]) for row in balance], [("2026-06", 1254.67), ("2026-07", 1125.0), ("2026-08", 1190.85)])
        self.assertTrue(all(row["source_url"] == article_url(8) and row["observation_kind"] == "derived" for row in balance))
        index = {req["id"]: req for req in requests()}
        for observation in result["observations"]:
            self.assertEqual(observation, source.validate_observation(copy.deepcopy(observation), index[observation["request_id"]], pages[observation["receipt_id"]], date(2026, 10, 3), "2026-09"))

    async def test_shared_query_balance_cannot_eat_preliminary_old_balance(self):
        docs = native_fixture_documents(attack=True)
        attacker = source.parse_page(docs[article_url(18)], article_url(18))
        attacker["text_sha256"] = sha256(attacker["text"].encode()).hexdigest()
        # The old balance table really qualifies for the table helper. This
        # test would be vacuous if the fixture itself were unparsable.
        eligible = source._table_candidates(attacker, [requests()[0]])
        self.assertEqual(len(eligible), 3)
        result, _, _, _, _, _ = await self.collect(docs=docs)
        balance = [row for row in result["observations"] if row["request_id"] == BALANCE_ID]
        self.assertEqual(len(balance), 3)
        self.assertEqual({row["source_url"] for row in balance}, {article_url(8)})
        self.assertNotIn("primary_observation_conflict", [issue["code"] for issue in result["issues"]])

    async def test_stale_generic_query_cache_cannot_change_fresh_selected_urls(self):
        result, _, fetched, caches, _, _ = await self.collect(stale_query=True)
        self.assertEqual(result["coverage"]["verified"], 3)
        self.assertNotIn(article_url(6), fetched)
        self.assertEqual(len(caches), 1)
        self.assertEqual(caches[0]["provider"], "original-publisher-directory")
        self.assertEqual({item["url"] for item in caches[0]["items"]}, {article_url(8), article_url(16), article_url(17), article_url(18)})

    async def test_discovery_exception_is_exclusive_no_generic_or_stale_cache_fallback(self):
        result, _, fetched, _, official, _ = await self.collect(stale_query=True, directory_error=True)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["observations"], [])
        self.assertEqual(fetched, [])
        self.assertTrue(all(row["source_restrictions"]["exclusive_reviewed_discovery"] for row in official["by_request"].values()))
        self.assertTrue(all(row["source_restrictions"]["allowed_source_urls"] == [] for row in official["by_request"].values()))

    async def test_latest_balance_missing_history_does_not_borrow_old_or_preliminary_rows(self):
        docs = native_fixture_documents(latest_periods=("2026-08",), attack=True)
        result, _, fetched, _, official, _ = await self.collect(docs=docs, stale_query=True)
        self.assertEqual(result["coverage"], {"required": 3, "verified": 2})
        self.assertEqual(result["request_status"][BALANCE_ID]["status"], "missing")
        self.assertFalse(any(row["request_id"] == BALANCE_ID for row in result["observations"]))
        self.assertNotIn(article_url(6), fetched)
        self.assertNotIn(article_url(7), fetched)
        self.assertNotIn(article_url(8), fetched)
        self.assertEqual(official["by_request"][BALANCE_ID]["source_restrictions"]["allowed_source_urls"], [])
        self.assertIn("customs_latest_balance_history_incomplete", [issue["code"] for issue in official["customs_discovery"]["issues"]])


if __name__ == "__main__":
    unittest.main()
