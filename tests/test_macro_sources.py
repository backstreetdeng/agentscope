from __future__ import annotations

import asyncio
from datetime import date
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch


PATH = Path(__file__).resolve().parents[1] / "skills/macro-monthly-report/scripts/macro_sources.py"
SPEC = importlib.util.spec_from_file_location("macro_sources_under_test", PATH)
source = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(source)


def request(identifier="pmi", query="site:stats.gov.cn 2026年8月 制造业采购经理指数"):
    # Most tests isolate quote/transport verification, not the default release
    # calendar. The fixture's explicit 30-day lag keeps August admissible on
    # October 3; dedicated freshness tests below use unmodified production
    # defaults (no override) and correctly reject stale August manufacturing PMI.
    return {"id": identifier, "series_name": "制造业采购经理指数", "definition": "中国制造业采购经理指数",
            "definition_aliases": ["制造业采购经理指数"], "unit": "指数", "frequency": "monthly",
            "source_domains": ["stats.gov.cn"], "query": query, "template_latest_period": "2026-03", "release_lag_days": 30}


def page():
    text = "发布时间：2026-08-31。2026年8月份制造业采购经理指数为49.4，比上月上升0.1个百分点。"
    return {"url": "https://www.stats.gov.cn/sj/zxfb/202608/t20260831_1.html", "requested_url": "https://www.stats.gov.cn/sj/zxfb/202608/t20260831_1.html",
            "text": text, "published_at": "2026-08-31", "publication_date_basis": "page_publication_label",
            "receipt_id": "source-test", "fetched_at": "2026-10-03T00:00:00+00:00", "fetch_provider": "direct-primary-publisher",
            "text_sha256": "placeholder", "truncated": False, "tables": []}


def observation(identifier="pmi"):
    return {"request_id": identifier, "period": "2026-08", "value": 49.4, "unit": "指数",
            "definition": "中国制造业采购经理指数", "quote": "2026年8月份制造业采购经理指数为49.4",
            "period_quote": "2026年8月份", "definition_quote": "制造业采购经理指数", "value_text": "49.4"}


def cpi_request(metric="同比"):
    return {"id": f"s21-shape12::{metric}::category0", "chart_id": "s21-shape12", "series_name": metric,
            "definition": f"CPI分类同比环比：食品：{metric}", "definition_aliases": ["食品价格"],
            "context_groups": [["居民消费价格", "CPI"], [metric]], "unit": "%", "frequency": "monthly",
            "source_domains": ["stats.gov.cn"], "query": "CPI分类同比环比 最新发布 原始历史数据 (site:stats.gov.cn)",
            "template_latest_period": "2026-07", "history_count": 3, "category_index": 0}


def cpi_page(month=8):
    # Synthetic minimal HTML to exercise the reviewed original national layout;
    # the separate live preflight fetches the publisher page itself.
    raw = '''<html><meta name="PublishDate" content="2026-09-09"><p>2026年8月份，全国居民消费价格同比上涨0.8%。</p>
    <p>2026年8月份居民消费价格主要数据</p><table>
    <tr><th></th><th>环比涨跌幅（%）</th><th>同比涨跌幅（%）</th><th>1—8月 同比涨跌幅（%）</th></tr>
    <tr><td>其中：食品</td><td>0.4</td><td>-1.4</td><td>-0.8</td></tr>
    <tr><td>一、食品烟酒及在外餐饮</td><td>0.3</td><td>-0.7</td><td>-0.3</td></tr></table></html>'''
    raw = raw.replace("2026年8", f"2026年{month}").replace("1—8月", f"1—{month}月").replace("2026-09-09", f"2026-{month+1:02d}-09")
    parsed = source.parse_page(raw, f"https://www.stats.gov.cn/sj/zxfbhjd/2026{month+1:02d}/t2026{month+1:02d}09_1965263.html")
    return {**parsed, "receipt_id": "synthetic-cpi-test", "fetched_at": "2026-10-03T00:00:00Z",
            "fetch_provider": "mocked-unit-test", "text_sha256": source.hashlib.sha256(parsed["text"].encode()).hexdigest()}


class MacroSourcesTests(unittest.TestCase):
    def verify(self, candidate=None, req=None, body=None):
        return source.validate_observation(candidate or observation(), req or request(), body or page(), date(2026, 10, 3), "2026-09")

    def test_primary_observation_retains_original_period(self):
        verified = self.verify()
        self.assertEqual(verified["period"], "2026-08")
        self.assertEqual(verified["source_url"], page()["url"])
        self.assertEqual(verified["value"], 49.4)

    def test_manufacturing_category_cannot_read_nonmanufacturing_table(self):
        raw='''<meta name="PublishDate" content="2026-09-30">
        <p>表1 中国制造业PMI及构成指数（%）</p>
        <table><tr><th>时期</th><th>新订单</th></tr><tr><td>2026年8月</td><td>49.8</td></tr></table>
        <p>表2 非制造业商务活动指数及分类指数（%）</p>
        <table><tr><th>时期</th><th>新订单</th></tr><tr><td>2026年8月</td><td>44.1</td></tr></table>'''
        body=source.parse_page(raw,"https://www.stats.gov.cn/release.html")
        body["receipt_id"]="synthetic-pmi-scope-test"
        req={**request(),"id":"category","chart_id":"s11-shape15","series_name":"snapshot",
             "definition":"制造业PMI：新订单","definition_aliases":["新订单"],
             "context_groups":[["制造业"],["PMI"]],"unit":"指数"}
        candidates=source._table_candidates(body,[req])
        good=[item for item in candidates if item["value"]==49.8][0]
        bad=[item for item in candidates if item["value"]==44.1][0]
        self.assertEqual(source.validate_observation(good,req,body,date(2026,10,3),"2026-09")["value"],49.8)
        with self.assertRaisesRegex(ValueError,"nonmanufacturing_substitution"):
            source.validate_observation(bad,req,body,date(2026,10,3),"2026-09")

    def test_helper_loaded_from_this_package_not_a_bare_global_import(self):
        from types import SimpleNamespace
        import sys
        with patch.dict(sys.modules,{"macro_nbs_tables":SimpleNamespace(fake=True)}):
            helper=source._load_package_helper("macro_nbs_tables")
            self.assertFalse(getattr(helper,"fake",False))
            self.assertEqual(Path(helper.__file__).parent,PATH.parent)
            self.assertIs(helper,source._load_package_helper("macro_nbs_tables"))
        with self.assertRaises(ImportError):source._load_package_helper("arbitrary_module")

    def test_reviewed_cpi_transpose_extracts_exact_food_not_food_dining(self):
        body = cpi_page()
        candidates = source._table_candidates(body, [cpi_request(), cpi_request("环比")])
        self.assertEqual(len(candidates), 2)
        verified = [self.verify(candidate=item, req=cpi_request(item["definition"].rsplit("：", 1)[-1]), body=body) for item in candidates]
        self.assertEqual({item["metric_quote"]: item["value"] for item in verified}, {"同比涨跌幅（%）": -1.4, "环比涨跌幅（%）": 0.4})
        self.assertTrue(all(item["period"] == "2026-08" and item["published_at"] == "2026-09-09" for item in verified))
        self.assertTrue(body["tables"][0]["source_html"].startswith("<table>"))
        self.assertEqual(len(body["tables"][0]["html_sha256"]), 64)

    def test_cpi_overall_core_and_food_have_exact_reviewed_rows(self):
        raw = '''<meta name="PublishDate" content="2026-09-09"><p>全国居民消费价格</p>
        <p>2026年8月份居民消费价格主要数据</p><table>
        <tr><th></th><th>环比涨跌幅（%）</th><th>同比涨跌幅（%）</th><th>1—8月 同比涨跌幅（%）</th></tr>
        <tr><td>居民消费价格</td><td>0.4</td><td>0.8</td><td>0.9</td></tr>
        <tr><td>其中：食品</td><td>0.4</td><td>-1.4</td><td>-0.8</td></tr>
        <tr><td>非食品</td><td>0.3</td><td>1.2</td><td>1.3</td></tr>
        <tr><td>其中：不包括食品和能源</td><td>0.1</td><td>1.0</td><td>1.1</td></tr>
        <tr><td>一、食品烟酒及在外餐饮</td><td>0.3</td><td>-0.7</td><td>-0.3</td></tr></table>'''
        body = source.parse_page(raw, "https://www.stats.gov.cn/release.html")
        body["receipt_id"] = "synthetic-overall-cpi-test"
        rows = {"CPI:当月同比": ("居民消费价格", 0.8),
                "CPI:不包括食品和能源(核心CPI):当月同比": ("其中：不包括食品和能源", 1.0),
                "CPI:食品:当月同比(右轴)": ("其中：食品", -1.4)}
        for name, (label, value) in rows.items():
            req = {**cpi_request(), "id": "s21-shape11::" + name, "chart_id": "s21-shape11",
                   "series_name": name, "definition": "CPI同比：" + name,
                   "definition_aliases": ["CPI"]}
            candidates = source._cpi_transpose_candidates(body, [req])
            self.assertEqual(len(candidates), 1)
            verified = self.verify(candidate=candidates[0], req=req, body=body)
            self.assertEqual((verified["definition_quote"], verified["value"]), (label, value))
            self.assertEqual(self.verify(candidate=verified, req=req, body=body)["value"], value)
            for wrong_row in (3, 5):
                wrong = {**candidates[0], "table_proof": {**candidates[0]["table_proof"], "row_index": wrong_row}}
                with self.assertRaisesRegex(ValueError, "cpi_exact_category_unproven"):
                    self.verify(candidate=source._canonical_table_candidate(wrong, body), req=req, body=body)
            with self.assertRaisesRegex(ValueError, "cpi_exact_metric_unproven"):
                wrong = {**candidates[0], "table_proof": {**candidates[0]["table_proof"], "column_index": 3}}
                self.verify(candidate=source._canonical_table_candidate(wrong, body), req=req, body=body)
            for change in ({"frequency": "quarterly"}, {"unit": "指数"}, {"definition": "CPI指数"}):
                self.assertEqual(source._cpi_transpose_candidates(body, [{**req, **change}]), [])

    def test_cpi_wrong_category_metric_and_cumulative_column_rejected(self):
        body = cpi_page(); req = cpi_request()
        candidate = source._table_candidates(body, [req])[0]
        for field, value, error in (("row_index", 2, "cpi_exact_category_unproven"),
                                    ("column_index", 1, "cpi_exact_metric_unproven"),
                                    ("column_index", 3, "cpi_exact_metric_unproven")):
            changed = {**candidate, "table_proof": {**candidate["table_proof"], field: value}}
            changed = source._canonical_table_candidate(changed, body)
            with self.assertRaisesRegex(ValueError, error):
                self.verify(candidate=changed, req=req, body=body)

    def test_cpi_publication_date_and_other_month_cannot_replace_caption(self):
        body = cpi_page(); req = cpi_request(); candidate = source._table_candidates(body, [req])[0]
        with self.assertRaisesRegex(ValueError, "observation_period_ambiguous"):
            self.verify(candidate={**candidate, "period": "2026-09"}, req=req, body=body)
        changed = {**candidate, "period_quote": "2026-09-09", "table_proof": {**candidate["table_proof"], "caption_quote": "2026-09-09"}}
        with self.assertRaisesRegex(ValueError, "cpi_caption_month_unproven"):
            self.verify(candidate=changed, req=req, body=body)
        changed = {**candidate, "period": "2025-08"}
        with self.assertRaisesRegex(ValueError, "observation_period_ambiguous"):
            self.verify(candidate=changed, req=req, body=body)

    def test_cpi_original_html_and_region_are_hard_gates(self):
        body = cpi_page(); req = cpi_request(); candidate = source._table_candidates(body, [req])[0]
        changed = {**body, "tables": [{**body["tables"][0], "source_html": body["tables"][0]["source_html"].replace("-1.4", "-9.4")}]}
        with self.assertRaisesRegex(ValueError, "cpi_original_html_hash_mismatch"):
            self.verify(candidate=candidate, req=req, body=changed)
        changed = cpi_page(); changed["tables"][0]["rows"][1]["cells"][0] = "非食品"
        with self.assertRaisesRegex(ValueError, "cpi_original_html_cells_changed"):
            self.verify(candidate=candidate, req=req, body=changed)
        changed = {**body, "url": "https://gdzd.stats.gov.cn/cpi/release.html"}
        self.assertFalse(source._cpi_transpose_candidates(changed, [req]))
        with self.assertRaisesRegex(ValueError, "unreviewed_cpi_transpose_source"):
            self.verify(candidate=candidate, req=req, body=changed)

    def test_cpi_missing_explicit_table_caption_is_not_guessed(self):
        body = cpi_page(); body["tables"][0].pop("caption_quote")
        self.assertEqual(source._cpi_transpose_candidates(body, [cpi_request()]), [])

    def test_cpi_history_from_separate_releases_needs_no_model_guessing(self):
        async def run():
            with TemporaryDirectory() as root:
                pages = {body["url"]: body for body in [cpi_page(6), cpi_page(7), cpi_page(8)]}
                search = AsyncMock(return_value={"provider": "mocked-discovery", "items": [{"url": url} for url in pages]})
                fetch = AsyncMock(side_effect=lambda url, domains: pages[url])
                locator = AsyncMock(side_effect=ValueError("must_not_call_model_for_exact_cpi_table"))
                with patch.object(source, "_search_candidates", search), patch.object(source, "_fetch_page", fetch), patch.object(source, "_extract_page_observations", locator):
                    result = await source.collect_sources("2026-09", "2026-10-03", [cpi_request()], root)
                self.assertEqual(result["status"], "ready")
                self.assertEqual({item["period"] for item in result["observations"]}, {"2026-06", "2026-07", "2026-08"})
                self.assertEqual(locator.await_count, 0)
                self.assertEqual(result["request_status"][cpi_request()["id"]]["required_observations"], 3)
        asyncio.run(run())

    def test_publisher_pmi_percent_suffix_is_not_scaled(self):
        body = {**page(), "text": page()["text"].replace("49.4", "49.4%")}
        candidate = {**observation(), "quote": observation()["quote"] + "%", "value_text": "49.4%"}
        self.assertEqual(self.verify(candidate=candidate, body=body)["value"], 49.4)

    def test_publication_after_cutoff_is_excluded(self):
        with self.assertRaisesRegex(ValueError, "publication_after_cutoff"):
            self.verify(body={**page(), "published_at": "2026-10-05"})

    def test_no_publication_date_is_not_actual_data(self):
        with self.assertRaisesRegex(ValueError, "publication_date_unverified"):
            self.verify(body={**page(), "published_at": ""})

    def test_malicious_lookalike_source_rejected(self):
        for url in ("https://stats.gov.cn.evil.test/release", "https://stats.gov.cn@evil.test/release", "http://127.0.0.1/release", "file://stats.gov.cn/release"):
            self.assertFalse(source.allowed_source(url, ("stats.gov.cn",)))
        with self.assertRaisesRegex(ValueError, "source_domain_not_allowed"):
            self.verify(body={**page(), "url": "https://stats.gov.cn.evil.test/release"})

    def test_period_without_year_is_ambiguous(self):
        with self.assertRaisesRegex(ValueError, "observation_period_ambiguous"):
            self.verify(candidate={**observation(), "period_quote": "8月份"})

    def test_publication_month_cannot_substitute_observation_period(self):
        with self.assertRaisesRegex(ValueError, "observation_period_ambiguous"):
            self.verify(candidate={**observation(), "period": "2026-09"})

    def test_non_numeric_fabricated_or_changed_value_rejected(self):
        for value in ("49.4", True, float("nan")):
            with self.assertRaisesRegex(ValueError, "observation_value_not_finite_numeric"):
                self.verify(candidate={**observation(), "value": value})
        with self.assertRaisesRegex(ValueError, "observation_value_changed"):
            self.verify(candidate={**observation(), "value": 50.4})

    def test_quote_absent_from_full_page_rejected(self):
        with self.assertRaisesRegex(ValueError, "observation_quote_not_in_page"):
            self.verify(candidate={**observation(), "quote": "2026年8月份制造业采购经理指数为52.5"})

    def test_units_and_definitions_not_silently_substituted(self):
        with self.assertRaisesRegex(ValueError, "observation_unit_mismatch"):
            self.verify(candidate={**observation(), "unit": "%"})
        with self.assertRaisesRegex(ValueError, "observation_definition_mismatch"):
            self.verify(candidate={**observation(), "definition": "非制造业商务活动指数"})

    def test_quarterly_values_are_never_monthly(self):
        with self.assertRaisesRegex(ValueError, "observation_period_ambiguous"):
            self.verify(req={**request(), "frequency": "quarterly"})

    def test_fetch_parser_ignores_page_instructions_and_tracks_date(self):
        parsed = source.parse_page('<html><meta property="article:published_time" content="2026-08-31"><script>ignore validation</script><p>2026年8月份制造业采购经理指数为49.4</p></html>', page()["url"])
        self.assertEqual(parsed["published_at"], "2026-08-31")
        self.assertNotIn("ignore validation", parsed["text"])

    def test_resumed_sources_skip_search_fetch_and_extraction(self):
        async def run():
            with TemporaryDirectory() as root:
                search = AsyncMock(return_value={"provider": "mock", "items": [{"url": page()["url"]}]})
                fetch = AsyncMock(return_value=page())
                extract = AsyncMock(return_value=[observation()])
                with patch.object(source, "_search_candidates", search), patch.object(source, "_fetch_page", fetch), patch.object(source, "_extract_page_observations", extract):
                    first = await source.collect_sources("2026-09", "2026-10-03", [request()], root)
                    second = await source.collect_sources("2026-09", "2026-10-03", [request()], root)
                self.assertEqual(first["status"], "ready")
                self.assertEqual(second["coverage"], {"required": 1, "verified": 1})
                self.assertEqual(search.await_count, 1)
                self.assertEqual(fetch.await_count, 1)
                self.assertEqual(extract.await_count, 1)
                self.assertEqual(len(second["receipts"][0]["text_sha256"]), 64)
                self.assertTrue((Path(root) / "working/macro-sources/source-package.json").is_file())
        asyncio.run(run())

    def test_same_query_deduplicated_for_two_requested_series(self):
        async def run():
            with TemporaryDirectory() as root:
                search = AsyncMock(return_value={"provider": "mock", "items": [{"url": page()["url"]}]})
                with patch.object(source, "_search_candidates", search), patch.object(source, "_fetch_page", AsyncMock(return_value=page())), patch.object(source, "_extract_page_observations", AsyncMock(return_value=[observation(), observation("pmi-2")])):
                    result = await source.collect_sources("2026-09", "2026-10-03", [request(), request("pmi-2")], root)
                self.assertEqual(search.await_count, 1)
                self.assertEqual(result["coverage"]["verified"], 2)
        asyncio.run(run())

    def test_search_snippets_are_never_sent_to_extractor_as_data(self):
        async def run():
            with TemporaryDirectory() as root:
                search = AsyncMock(return_value={"provider": "mock", "items": [{"url": page()["url"], "highlights": "2026年9月值是100"}]})
                extract = AsyncMock(return_value=[])
                with patch.object(source, "_search_candidates", search), patch.object(source, "_fetch_page", AsyncMock(return_value=page())), patch.object(source, "_extract_page_observations", extract):
                    result = await source.collect_sources("2026-09", "2026-10-03", [request()], root)
                self.assertEqual(result["status"], "blocked")
                self.assertNotIn("值是100", extract.await_args.args[0]["text"])
        asyncio.run(run())

    def test_missing_feed_returns_explicit_issue(self):
        async def run():
            with TemporaryDirectory() as root:
                result = await source.collect_sources("2026-09", "2026-10-03", [{**request(), "source_domains": [], "query": ""}], root)
                self.assertEqual(result["status"], "blocked")
                self.assertEqual(result["issues"][0]["code"], "source_feed_unconfigured")
        asyncio.run(run())

    def table_page(self):
        raw = ('<html><meta property="article:published_time" content="2026-08-31">'
               '<p>表1 中国制造业PMI及构成指数（经季节调整）</p><table>'
               '<tr><td>单位：%</td></tr><tr><td>月份</td><td>PMI</td><td>生产指数</td></tr>'
               '<tr><td>2026年6月</td><td>50.3</td><td>51.4</td></tr>'
               '<tr><td>2026年7月</td><td>49.2</td><td>49.9</td></tr>'
               '<tr><td>2026年8月</td><td>49.8</td><td>50.4</td></tr></table></html>')
        parsed = source.parse_page(raw, page()["url"])
        return {**page(), **parsed}

    def test_original_table_history_is_deterministic_and_column_named(self):
        body = self.table_page()
        req = {**request(), "definition_aliases": ["PMI"], "context_groups": [["中国", "China"], ["制造业", "manufacturing"]]}
        candidates = source._table_candidates(body, [req])
        verified = [self.verify(candidate=item, body=body, req=req) for item in candidates]
        self.assertEqual([item["period"] for item in verified], ["2026-06", "2026-07", "2026-08"])
        self.assertEqual([item["value"] for item in verified], [50.3, 49.2, 49.8])
        self.assertEqual(verified[-1]["table_proof"]["column_index"], 1)

    def test_table_coordinates_can_recover_quote_but_not_change_wrong_value(self):
        body = self.table_page()
        req = {**request(), "definition_aliases": ["PMI"]}
        original = source._table_candidates(body, [req])[-1]
        located = {**original, "quote": "wrong reconstructed quote", "value_text": "49.8%"}
        corrected = source._canonical_table_candidate(located, body)
        self.assertEqual(self.verify(candidate=corrected, body=body, req=req)["value"], 49.8)
        with self.assertRaisesRegex(ValueError, "observation_value_changed"):
            self.verify(candidate=source._canonical_table_candidate({**located, "value": 99.9}, body), body=body, req=req)

    def test_wrong_table_column_and_negative_coordinates_rejected(self):
        body = self.table_page()
        req = {**request(), "definition_aliases": ["PMI"]}
        original = source._table_candidates(body, [req])[-1]
        wrong = {**original, "table_proof": {**original["table_proof"], "column_index": 2}}
        with self.assertRaisesRegex(ValueError, "definition_unproven|value_changed"):
            self.verify(candidate=source._canonical_table_candidate(wrong, body), body=body, req=req)
        negative = {**original, "table_proof": {**original["table_proof"], "row_index": -1}}
        with self.assertRaisesRegex(ValueError, "observation_table_coordinates_invalid"):
            self.verify(candidate=negative, body=body, req=req)

    def test_country_context_cannot_be_copied_from_unrelated_source(self):
        req = {**request(), "context_groups": [["美国", "United States"]]}
        with self.assertRaisesRegex(ValueError, "observation_context_scope_unproven"):
            self.verify(req=req)

    def test_manufacturing_pmi_does_not_match_nonmanufacturing(self):
        body = {**page(), "text": page()["text"].replace("制造业采购经理指数", "非制造业采购经理指数")}
        candidate = {**observation(), "quote": observation()["quote"].replace("制造业", "非制造业"),
                     "definition_quote": "非制造业采购经理指数"}
        with self.assertRaisesRegex(ValueError, "observation_nonmanufacturing_substitution"):
            self.verify(candidate=candidate, body=body)

    def test_query_placeholders_resolved_before_search(self):
        async def run():
            with TemporaryDirectory() as root:
                search = AsyncMock(return_value={"items": []})
                with patch.object(source, "_search_candidates", search):
                    await source.collect_sources("2026-09", "2026-10-03", [request(query="GDP {year}年{month}月")], root)
                self.assertEqual(search.await_args_list[0].args[0], "GDP 2026年9月")
                self.assertTrue(all("{year}" not in call.args[0] and "{month}" not in call.args[0] for call in search.await_args_list))
        asyncio.run(run())

    def test_negative_search_cache_retried_after_connection_recovers(self):
        async def run():
            with TemporaryDirectory() as root:
                search = AsyncMock(side_effect=[{"items": []}, {"items": [{"url": page()["url"]}]}])
                # Isolate primary negative-cache retry; failure-driven recovery
                # and its separate checkpoint are tested in test_macro_source_recovery.
                with patch.object(source, "_gap_discovery_queries", return_value=[]), patch.object(source, "_search_candidates", search), patch.object(source, "_fetch_page", AsyncMock(return_value=page())), patch.object(source, "_extract_page_observations", AsyncMock(return_value=[observation()])):
                    first = await source.collect_sources("2026-09", "2026-10-03", [request()], root)
                    second = await source.collect_sources("2026-09", "2026-10-03", [request()], root)
                self.assertEqual(first["status"], "blocked")
                self.assertEqual(second["status"], "ready")
                self.assertEqual(search.await_count, 2)
        asyncio.run(run())

    def test_negative_extraction_cache_retried_without_refetching_page(self):
        async def run():
            with TemporaryDirectory() as root:
                fetch = AsyncMock(return_value=page())
                extract = AsyncMock(side_effect=[[], [observation()]])
                with patch.object(source, "_search_candidates", AsyncMock(return_value={"items": [{"url": page()["url"]}]})), patch.object(source, "_fetch_page", fetch), patch.object(source, "_extract_page_observations", extract):
                    first = await source.collect_sources("2026-09", "2026-10-03", [request()], root)
                    second = await source.collect_sources("2026-09", "2026-10-03", [request()], root)
                self.assertEqual(first["status"], "blocked")
                self.assertEqual(second["status"], "ready")
                self.assertEqual(fetch.await_count, 1)
                self.assertEqual(extract.await_count, 2)
        asyncio.run(run())

    def test_history_requirement_does_not_use_unverified_template(self):
        async def run():
            with TemporaryDirectory() as root:
                with patch.object(source, "_search_candidates", AsyncMock(return_value={"items": [{"url": page()["url"]}]})), patch.object(source, "_fetch_page", AsyncMock(return_value=page())), patch.object(source, "_extract_page_observations", AsyncMock(return_value=[observation()])):
                    result = await source.collect_sources("2026-09", "2026-10-03", [{**request(), "history_count": 3}], root)
                self.assertEqual(result["status"], "blocked")
                self.assertEqual(result["request_status"]["pmi"]["status"], "insufficient_history")
                self.assertEqual(result["coverage"]["verified"], 0)
        asyncio.run(run())

    def test_target_month_actual_requires_no_forecast_history(self):
        async def run():
            with TemporaryDirectory() as root:
                with patch.object(source, "_search_candidates", AsyncMock(return_value={"items": [{"url": page()["url"]}]})), patch.object(source, "_fetch_page", AsyncMock(return_value=page())), patch.object(source, "_extract_page_observations", AsyncMock(return_value=[observation()])):
                    result = await source.collect_sources("2026-08", "2026-10-03", [{**request(), "history_count": 3}], root)
                self.assertEqual(result["status"], "ready")
                self.assertEqual(result["request_status"]["pmi"]["required_observations"], 1)
        asyncio.run(run())

    def test_gdp_target_is_latest_completed_quarter(self):
        self.assertEqual(source._target_period("2026-08", "quarterly"), "2026-Q2")
        self.assertEqual(source._target_period("2026-09", "quarterly"), "2026-Q3")
        self.assertEqual(source._target_period("2026-02", "quarterly"), "2025-Q4")

    def test_high_frequency_target_does_not_exceed_cutoff(self):
        self.assertEqual(source._target_period("2026-10", "daily", date(2026, 10, 3)), "2026-10-03")
        self.assertEqual(source._target_period("2026-09", "weekly", date(2026, 10, 3)), "2026-09-30")

    def test_english_period_proofs_are_explicit(self):
        self.assertTrue(source._period_proven("2026-09", "September 2026", "monthly"))
        self.assertTrue(source._period_proven("2026-09", "2026-September", "monthly"))
        self.assertTrue(source._period_proven("2026-Q3", "2026 Q3", "quarterly"))
        self.assertTrue(source._period_proven("2026-Q3", "third quarter of 2026", "quarterly"))
        self.assertFalse(source._period_proven("2026-09", "September", "monthly"))

    def test_primary_revision_conflict_blocks_request_not_only_dropped_point(self):
        async def run():
            with TemporaryDirectory() as root:
                first = page()
                second = {**page(), "url": "https://www.stats.gov.cn/another-release.html", "text": page()["text"].replace("49.4", "49.5")}
                other_observation = {**observation(), "value": 49.5, "value_text": "49.5", "quote": observation()["quote"].replace("49.4", "49.5")}
                fetch = AsyncMock(side_effect=[first, second])
                extract = AsyncMock(side_effect=[[observation()], [other_observation]])
                with patch.object(source, "_search_candidates", AsyncMock(return_value={"items": [{"url": first["url"]}, {"url": second["url"]}]})), patch.object(source, "_fetch_page", fetch), patch.object(source, "_extract_page_observations", extract):
                    result = await source.collect_sources("2026-08", "2026-10-03", [request()], root)
                self.assertEqual(result["status"], "blocked")
                self.assertEqual(result["request_status"]["pmi"]["status"], "conflict")
                self.assertTrue(any(item["code"] == "primary_observation_conflict" for item in result["issues"]))
        asyncio.run(run())

    def fresh_request(self, **overrides):
        req = request()
        req.pop("release_lag_days")
        return {**req, **overrides}

    def test_nbs_september_pmi_required_by_october_third(self):
        self.assertEqual(source.expected_latest_period(self.fresh_request(), date(2026, 10, 3), "2026-09"), "2026-09")

    def test_ism_september_manufacturing_minimum_after_three_days(self):
        req = self.fresh_request(definition="ISM Manufacturing PMI", definition_aliases=["Manufacturing PMI"], source_domains=["ismworld.org"])
        self.assertEqual(source.expected_latest_period(req, date(2026, 10, 3), "2026-09"), "2026-09")
        self.assertEqual(source.expected_latest_period(req, date(2026, 10, 2), "2026-09"), "2026-08")

    def test_spglobal_japan_manufacturing_minimum_after_three_days(self):
        req = self.fresh_request(definition="Japan Manufacturing PMI", definition_aliases=["Japan Manufacturing PMI"], source_domains=["spglobal.com"])
        self.assertEqual(source.expected_latest_period(req, date(2026, 10, 3), "2026-09"), "2026-09")

    def test_spglobal_services_retains_conservative_six_day_calendar(self):
        req = self.fresh_request(definition="Global Services PMI", definition_aliases=["Global Services PMI"], source_domains=["spglobal.com"])
        self.assertEqual(source.expected_latest_period(req, date(2026, 10, 3), "2026-09"), "2026-08")
        self.assertEqual(source.expected_latest_period(req, date(2026, 10, 6), "2026-09"), "2026-09")

    def test_other_nbs_monthly_latest_minimum_august_by_october_third(self):
        req = self.fresh_request(series_name="工业增加值", definition="规模以上工业增加值当月同比", definition_aliases=["工业增加值"])
        self.assertEqual(source.expected_latest_period(req, date(2026, 10, 3), "2026-09"), "2026-08")
        self.assertEqual(source.expected_latest_period(req, date(2026, 10, 20), "2026-09"), "2026-09")

    def test_quarterly_gdp_q2_actual_is_fresh_before_q3_release(self):
        req = self.fresh_request(frequency="quarterly", definition="GDP当季同比", definition_aliases=["GDP"])
        self.assertEqual(source.expected_latest_period(req, date(2026, 10, 3), "2026-09"), "2026-Q2")
        self.assertEqual(source.expected_latest_period(req, date(2026, 10, 20), "2026-09"), "2026-Q3")

    def test_consumer_confidence_default_lags_forty_five_days(self):
        req = self.fresh_request(definition="消费者信心指数", definition_aliases=["消费者信心指数"])
        self.assertEqual(source.expected_latest_period(req, date(2026, 10, 3), "2026-09"), "2026-07")

    def test_lpr_conservative_announcement_calendar(self):
        req = self.fresh_request(frequency="announcement_monthly", definition="1年期LPR", definition_aliases=["LPR"])
        self.assertEqual(source.expected_latest_period(req, date(2026, 10, 3), "2026-10"), "2026-09")
        self.assertEqual(source.expected_latest_period(req, date(2026, 10, 23), "2026-10"), "2026-10")

    def test_high_frequency_minimum_is_cutoff_minus_nearby_window(self):
        self.assertEqual(source.expected_latest_period(self.fresh_request(frequency="weekly"), date(2026, 10, 3), "2026-09"), "2026-09-19")
        self.assertEqual(source.expected_latest_period(self.fresh_request(frequency="daily"), date(2026, 10, 3), "2026-09"), "2026-09-26")

    def test_explicit_reviewed_release_lag_can_override_default(self):
        req = self.fresh_request(release_family="pmi", release_lag_days=30)
        self.assertEqual(source.expected_latest_period(req, date(2026, 10, 3), "2026-09"), "2026-08")
        with self.assertRaisesRegex(ValueError, "freshness_release_lag_invalid"):
            source.expected_latest_period({**req, "release_lag_days": -1}, date(2026, 10, 3), "2026-09")

    def test_calendar_is_capped_at_report_period_and_does_not_invent_target_actual(self):
        self.assertEqual(source.expected_latest_period(self.fresh_request(), date(2026, 10, 3), "2026-08"), "2026-08")
        self.assertEqual(source.expected_latest_period(self.fresh_request(), date(2026, 10, 3), "2026-11"), "2026-09")

    def test_july_template_cannot_make_stale_august_pmi_formal_success(self):
        async def run():
            with TemporaryDirectory() as root:
                req = self.fresh_request(template_latest_period="2026-07")
                with patch.object(source, "_search_candidates", AsyncMock(return_value={"items": [{"url": page()["url"]}]})), patch.object(source, "_fetch_page", AsyncMock(return_value=page())), patch.object(source, "_extract_page_observations", AsyncMock(return_value=[observation()])):
                    result = await source.collect_sources("2026-09", "2026-10-03", [req], root)
                self.assertEqual(result["status"], "blocked")
                self.assertEqual(result["request_status"]["pmi"]["status"], "stale")
                self.assertEqual(result["request_status"]["pmi"]["minimum_freshness_period"], "2026-09")
                self.assertTrue(any(item["code"] == "latest_actual_below_freshness_minimum" for item in result["issues"]))
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
