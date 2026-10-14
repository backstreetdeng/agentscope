from __future__ import annotations

import asyncio
from datetime import date
import hashlib
import importlib.util
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

SCRIPT = Path(__file__).resolve().parents[1] / "skills/macro-monthly-report/scripts/macro_sources.py"
SPEC = importlib.util.spec_from_file_location("macro_public_sources_under_test", SCRIPT)
source = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(source)


def request():
    publishers = [
        {"publisher_id": "broker-a", "names": ["Broker Alpha"]},
        {"publisher_id": "broker-b", "names": ["Broker Beta"]},
    ]
    return {"id": "test-pmi", "series_name": "Manufacturing PMI", "definition": "Manufacturing PMI",
            "definition_aliases": ["Manufacturing PMI"], "context_groups": [], "unit": "指数", "frequency": "monthly",
            "source_domains": ["producer.test"], "original_publisher_domains": ["producer.test"],
            "secondary_source_domains": ["broker-a.test", "broker-b.test", "mirror-one.test", "mirror-two.test"],
            "secondary_publishers": {"broker-a.test": publishers[:1], "broker-b.test": publishers[1:],
                                     "mirror-one.test": publishers, "mirror-two.test": publishers},
            "origin_attribution_aliases": ["Wind"], "query": "Manufacturing PMI", "history_count": 3,
            "template_latest_period": "2026-07", "release_lag_days": 30}


def observation(period="2026-08", value=49.4):
    month = {"2026-06": "June", "2026-07": "July", "2026-08": "August", "2026-09": "September"}[period]
    quote = f"{month} 2026 Manufacturing PMI {value} index"
    return {"request_id": "test-pmi", "period": period, "value": value, "unit": "指数", "definition": "Manufacturing PMI",
            "quote": quote, "period_quote": f"{month} 2026", "definition_quote": "Manufacturing PMI", "value_text": str(value)}


def page(host="broker-a.test", broker="Broker Alpha", period="2026-08", value=49.4, suffix="release"):
    candidate = observation(period, value)
    text = f"Published: 2026-09-25\nReport by: {broker}\nData source: Wind\n{candidate['quote']}"
    return {"url": f"https://{host}/{suffix}.html", "text": text, "published_at": "2026-09-25",
            "publication_date_basis": "page_publication_label", "receipt_id": f"source-{host}-{suffix}",
            "fetched_at": "2026-10-03T00:00:00Z", "fetch_provider": "direct-public-publisher",
            "text_sha256": hashlib.sha256(text.encode()).hexdigest(), "truncated": False, "tables": []}


def verified(body, candidate=None, req=None):
    return source.validate_observation(candidate or observation(), req or request(), body, date(2026, 10, 3), "2026-09")


def package_replay(pages, candidates):
    evidence = [verified(body, candidate) for body, candidate in zip(pages, candidates)]
    package = {"report_month": "2026-09", "cutoff_date": "2026-10-03", "evidence_observations": evidence}
    return source.verify_source_corroboration(package, {"source_requests": [request()]}, {body["receipt_id"]: body for body in pages})


def pdf_bytes(lines_by_page):
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    writer = PdfWriter()
    for lines in lines_by_page:
        page = writer.add_blank_page(width=600, height=800)
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                                 NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
        stream = DecodedStreamObject()
        escaped = [line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") for line in lines]
        operations = "BT /F1 12 Tf 30 750 Td 16 TL " + " ".join(f"({line}) Tj T*" for line in escaped) + " ET"
        stream.set_data(operations.encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    # CreationDate is deliberately not accepted as a report publication date.
    writer.add_metadata({"/CreationDate": "D:20260925000000"})
    output = io.BytesIO(); writer.write(output); return output.getvalue()


class PublicSourceProofTests(unittest.TestCase):
    def test_original_publisher_stays_primary(self):
        item = verified(page(host="producer.test", broker="Publisher"))
        self.assertEqual(item["source_grade"], "primary")
        self.assertNotIn("origin_attribution_quote", item)

    def test_secondary_replayed_attribution_not_official_claim(self):
        item = verified(page())
        self.assertEqual(item["source_grade"], "secondary")
        self.assertEqual(item["publisher_id"], "broker-a")
        self.assertIn("Data source: Wind", item["origin_attribution_quote"])
        self.assertIn("Broker Alpha", item["publisher_quote"])

    def test_secondary_missing_explicit_producer_rejected(self):
        body = page(); body["text"] = body["text"].replace("Data source: Wind", "No upstream attribution")
        with self.assertRaisesRegex(ValueError, "secondary_origin_attribution_unproven"):
            verified(body)

    def test_upstream_name_in_unrelated_article_or_navigation_is_not_proof(self):
        body = page(); body["text"] = "Report by: Broker Alpha\nData source: Wind\n" + "x" * 5000 + "\n" + observation()["quote"]
        with self.assertRaisesRegex(ValueError, "secondary_origin_not_linked_to_value"):
            verified(body)

    def test_unreviewed_secondary_domain_stays_rejected(self):
        with self.assertRaisesRegex(ValueError, "source_domain_not_allowed"):
            verified(page(host="unreviewed-news.test"))

    def test_mirror_with_no_original_broker_identity_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "secondary_original_publisher_unproven"):
            verified(page(host="mirror-one.test", broker="Mirror portal"))

    def test_mirror_can_identify_distinct_original_broker(self):
        item = verified(page(host="mirror-one.test", broker="Broker Beta"))
        self.assertEqual(item["publisher_id"], "broker-b")

    def test_ambiguous_multiple_original_brokers_are_not_guessed(self):
        with self.assertRaisesRegex(ValueError, "secondary_original_publisher_ambiguous"):
            verified(page(host="mirror-one.test", broker="Broker Alpha and Broker Beta"))

    def test_latest_same_value_two_distinct_publishers_accepted(self):
        bodies = [page(), page(host="broker-b.test", broker="Broker Beta")]
        replay = package_replay(bodies, [observation(), observation()])
        self.assertEqual(replay["issues"], [])
        self.assertEqual(len(replay["observations"]), 1)
        self.assertEqual(replay["observations"][0]["corroborating_publishers"], ["broker-a", "broker-b"])

    def test_two_storage_domains_mirroring_same_report_are_one_publisher(self):
        bodies = [page(host="mirror-one.test"), page(host="mirror-two.test")]
        replay = package_replay(bodies, [observation(), observation()])
        self.assertEqual(replay["observations"], [])
        self.assertEqual(replay["issues"][0]["code"], "secondary_latest_corroboration_missing")

    def test_history_keeps_single_source_latest_alone_requires_dual(self):
        bodies = [page(period="2026-06", suffix="jun"), page(period="2026-07", suffix="jul"), page(suffix="aug-a"),
                  page(host="broker-b.test", broker="Broker Beta", suffix="aug-b")]
        replay = package_replay(bodies, [observation("2026-06"), observation("2026-07"), observation(), observation()])
        self.assertEqual(replay["issues"], [])
        self.assertEqual(len(replay["observations"]), 3)
        self.assertNotIn("corroborating_publishers", replay["observations"][0])

    def test_conflicting_exact_period_or_value_does_not_become_corroboration(self):
        bodies = [page(), page(host="broker-b.test", broker="Broker Beta", value=50.4)]
        replay = package_replay(bodies, [observation(), observation(value=50.4)])
        self.assertEqual(replay["observations"], [])
        self.assertEqual(replay["issues"][0]["code"], "primary_observation_conflict")

    def test_primary_latest_needs_one_release_not_secondary_dual(self):
        replay = package_replay([page(host="producer.test")], [observation()])
        self.assertEqual(replay["issues"], [])
        self.assertEqual(replay["observations"][0]["source_grade"], "primary")

    def test_model_source_grade_cannot_override_real_domain(self):
        changed = {**observation(), "source_grade": "primary", "publisher_id": "producer"}
        item = verified(page(), changed)
        self.assertEqual(item["source_grade"], "secondary")
        self.assertEqual(item["publisher_id"], "broker-a")

    def test_future_secondary_publication_rejected(self):
        body = page(); body["published_at"] = "2026-10-05"
        with self.assertRaisesRegex(ValueError, "publication_after_cutoff"):
            verified(body)

    def test_body_publication_overrides_metadata_and_url_creation_date(self):
        body = source.parse_page('<meta name="PublishDate" content="2026-08-14"><p>发布时间：2026-08-21</p>',
                                 "https://www.mof.gov.cn/202608/t20260814_123.html")
        self.assertEqual(body["published_at"], "2026-08-21")
        self.assertEqual(body["publication_date_basis"], "page_publication_label")

    def test_pbc_long_timestamp_url_can_locate_publication_day(self):
        body = source.parse_page("<p>release</p>", "https://www.pbc.gov.cn/diaochatongjisi/20260919123456789001/index.html")
        self.assertEqual(body["published_at"], "2026-09-19")

    def test_reviewed_eastern_air_article_header_proves_publication(self):
        raw = '<div class="investment-content width-1280"><div class="left-content"><div class="title">天然橡胶周度策略（第35期）</div><div class="time">2026-09-22</div><div class="content">9月18日实际观测</div></div></div>'
        body = source.parse_page(raw, "https://www.cesfutures.com/investment/detail/report.html")
        self.assertEqual(body["published_at"], "2026-09-22")
        self.assertEqual(body["publication_date_basis"], "reviewed_publisher_article_header")

    def test_eastern_air_unmarked_prose_date_is_not_publication(self):
        body = source.parse_page('<div class="investment-content"><div class="title">周报</div><p>2026-09-22 实际观测</p></div>',
                                 "https://www.cesfutures.com/investment/detail/report.html")
        self.assertEqual(body["published_at"], "")

    def test_unreviewed_site_cannot_reuse_eastern_air_header_rule(self):
        raw = '<div class="investment-content"><div class="title">周报</div><div class="time">2026-09-22</div></div>'
        self.assertEqual(source.parse_page(raw, "https://unreviewed.test/investment/detail/report.html")["published_at"], "")


class PublicPdfProofTests(unittest.TestCase):
    def body(self, lines=None):
        raw = pdf_bytes(lines or [["Report date: 2026-09-25", "Report by: Broker Alpha", "Data source: Wind", observation()["quote"]]])
        parsed = source.parse_pdf(raw, "https://broker-a.test/report.pdf")
        return {**parsed, "receipt_id": "pdf-source", "fetched_at": "2026-10-03T00:00:00Z",
                "fetch_provider": "direct-public-publisher", "text_sha256": hashlib.sha256(parsed["text"].encode()).hexdigest()}

    def test_real_pdf_bytes_replay_includes_page_and_original_hash(self):
        body = self.body(); item = verified(body)
        self.assertEqual(item["source_grade"], "secondary")
        self.assertEqual(item["pdf_proof"]["page_index"], 0)
        self.assertEqual(item["pdf_proof"]["binary_sha256"], body["binary_sha256"])
        self.assertEqual(body["publication_date_basis"], "pdf_explicit_publication_label")

    def test_pdf_creation_metadata_alone_never_proves_publication(self):
        body = self.body([["Report by: Broker Alpha", "Data source: Wind", observation()["quote"]]])
        self.assertEqual(body["published_at"], "")
        with self.assertRaisesRegex(ValueError, "publication_date_unverified"):
            verified(body)

    def test_pdf_standalone_cover_day_is_explicit_not_fetch_time(self):
        body = self.body([["2026-09-25", "Report by: Broker Alpha", "Data source: Wind", observation()["quote"]]])
        self.assertEqual(body["published_at"], "2026-09-25")
        self.assertEqual(body["publication_date_basis"], "pdf_explicit_cover_date")

    def test_pdf_tampered_binary_page_or_text_rejected(self):
        body = self.body()
        for changed, code in (({**body, "binary_sha256": "0" * 64}, "public_pdf_binary_hash_mismatch"),
                              ({**body, "text": body["text"] + "fake"}, "public_pdf_receipt_changed"),
                              ({**body, "pdf_pages": [{**body["pdf_pages"][0], "text": "fake"}]}, "public_pdf_page_receipt_changed")):
            with self.assertRaisesRegex(ValueError, code):
                verified(changed)

    def test_pdf_quote_must_be_on_referenced_original_page(self):
        body = self.body([["Report date: 2026-09-25", "Report by: Broker Alpha"], ["Data source: Wind", observation()["quote"]]])
        item = verified(body)
        self.assertEqual(item["pdf_proof"]["page_index"], 1)
        with self.assertRaisesRegex(ValueError, "public_pdf_quote_wrong_page"):
            verified(body, {**observation(), "pdf_proof": {"page_index": 0}})


class PublicAdversarialScopeTests(unittest.TestCase):
    def check(self, quote, value, label="唐山钢厂高炉开工率", period="2026-09-18", request_changes=None, candidate_changes=None, publication="2026-09-25"):
        req = {**request(), "frequency": "weekly", "unit": "%", "definition": label, "series_name": label,
               "definition_aliases": [label, "高炉开工率"], "context_groups": [["唐山"]], "secondary_source_domains": []}
        req.update(request_changes or {})
        body = page(host="producer.test"); body.update(text="发布时间：" + publication + "\n" + quote, published_at=publication)
        candidate = {"request_id": req["id"], "period": period, "value": value, "unit": req["unit"], "definition": label,
                     "quote": quote, "period_quote": period, "definition_quote": label, "value_text": str(value) + "%"}
        candidate.update(candidate_changes or {})
        return verified(body, candidate, req)

    def test_other_indicator_numeric_in_same_quote_cannot_be_mapped_to_tangshan(self):
        quote = "2026-09-18 唐山钢厂高炉开工率95.0%，全国高炉开工率82.3%"
        self.assertEqual(self.check(quote, 95.0)["value"], 95.0)
        with self.assertRaisesRegex(ValueError, "observation_context_scope_unproven|observation_value_indicator_binding_unproven"):
            self.check(quote, 82.3)

    def test_primary_domain_republished_broker_wind_cannot_bypass_secondary(self):
        body = page(host="www.umetal.com"); body["text"] = body["text"].replace("Data source: Wind", "来源：国金证券；数据来源：Wind")
        req = {**request(), "source_domains": ["umetal.com"], "original_publisher_domains": ["umetal.com"]}
        with self.assertRaisesRegex(ValueError, "primary_domain_republished_source"):
            verified(body, req=req)

    def test_foreign_script_attribution_is_not_an_empty_source_field(self):
        req = {**request(), "source_domains": ["umetal.com"], "original_publisher_domains": ["umetal.com"]}
        for publisher in ("РБК", "ΕΡΤ", "رويترز"):
            with self.subTest(publisher=publisher):
                body = page(host="www.umetal.com")
                body["text"] = body["text"].replace("Data source: Wind", "来源：" + publisher)
                with self.assertRaisesRegex(ValueError, "primary_domain_republished_source"):
                    verified(body, req=req)

    def test_related_broker_and_wordpress_theme_are_not_document_provenance(self):
        body = page(); body["text"] = "Published: 2026-09-25\n" + observation()["quote"] + "\nRelated links: Broker Alpha\nWordPress theme: Wind"
        with self.assertRaisesRegex(ValueError, "secondary_original_publisher_unproven"):
            verified(body)
        body["text"] = "Published: 2026-09-25\nReport by: Broker Alpha\n" + observation()["quote"] + "\nWordPress theme: Wind"
        with self.assertRaisesRegex(ValueError, "secondary_origin_attribution_unproven"):
            verified(body)

    def test_weekly_housing_cannot_take_daily_or_unspecified_aggregation(self):
        label = "30大中城市商品房成交面积"
        changes = {"unit": "万平方米", "definition_aliases": [label], "context_groups": [["30大中城市"]]}
        for qualifier in ("当日", "日均", ""):
            quote = f"2026-09-18 {qualifier}{label}30.8万平方米"
            with self.assertRaisesRegex(ValueError, "weekly_observation_has_daily_scope|weekly_amount_aggregation_unproven"):
                self.check(quote, 30.8, label=label, request_changes=changes, candidate_changes={"value_text": "30.8"})

    def test_explicit_same_week_range_housing_is_not_guessed(self):
        label = "30大中城市商品房成交面积"
        interval = "2026-09-14至2026-09-20"
        quote = interval + " 当周" + label + "153.75万平方米"
        changes = {"unit": "万平方米", "definition_aliases": [label], "context_groups": [["30大中城市"]]}
        proof = {"period_quote": interval, "period_start": "2026-09-14", "period_end": "2026-09-20", "value_text": "153.75"}
        item = self.check(quote, 153.75, label, "2026-09-20", changes, proof)
        self.assertEqual(item["period_end"], "2026-09-20")
        with self.assertRaisesRegex(ValueError, "weekly_period_interval_unproven"):
            self.check(quote, 153.75, label, "2026-09-20", changes, {**proof, "period_start": "2026-09-01"})

    def test_future_day_in_same_month_is_not_actual(self):
        with self.assertRaisesRegex(ValueError, "observation_after_publication_day"):
            self.check("2026-09-30 唐山钢厂高炉开工率95.0%", 95.0, period="2026-09-30")

    def test_prose_forecast_is_not_original_actual(self):
        with self.assertRaisesRegex(ValueError, "forecast_not_actual_observation"):
            self.check("2026-09-18 唐山钢厂高炉开工率预测为95.0%", 95.0)

    def test_regional_sample_is_unproven_until_contract_declares_it(self):
        label = "全钢胎开工率"; quote = "2026-09-18 山东全钢胎开工率59.89%"
        changes = {"definition_aliases": [label], "context_groups": [["全钢胎"]]}
        with self.assertRaisesRegex(ValueError, "observation_sample_scope_unproven"):
            self.check(quote, 59.89, label=label, request_changes=changes)
        item = self.check(quote, 59.89, label=label, request_changes={**changes, "sample_scope": "山东"})
        self.assertEqual(item["value"], 59.89)

    def test_utilization_metric_cannot_replace_operating_rate(self):
        label = "全钢胎开工率"
        with self.assertRaisesRegex(ValueError, "utilization_not_operating_rate"):
            self.check("2026-09-18 全钢胎产能利用率59.89%", 59.89, label=label,
                       request_changes={"definition_aliases": ["全钢胎"], "context_groups": [["全钢胎"]]},
                       candidate_changes={"definition_quote": "全钢胎"})

    def test_percentage_point_change_cannot_become_pmi_level(self):
        body = page(host="producer.test"); body["text"] = "August 2026 Manufacturing PMI rose 0.1 percentage points to 49.4 index"
        candidate = {**observation(value=0.1), "quote": body["text"], "value_text": "0.1"}
        with self.assertRaisesRegex(ValueError, "observation_delta_not_level"):
            verified(body, candidate)

    def test_multiple_positional_values_are_not_bound_by_visual_order(self):
        quote = "2026-09-18 唐山钢厂高炉开工率与全国高炉开工率分别为95.0%、82.3%"
        with self.assertRaisesRegex(ValueError, "observation_positional_prose_unreviewed"):
            self.check(quote, 82.3)


class PublicCollectorTests(unittest.TestCase):
    def test_shared_directory_group_retains_each_series_required_urls(self):
        async def run():
            with TemporaryDirectory() as root:
                req = {**request(), "secondary_source_domains": [], "history_count": 1}
                second = {**req, "id": "second-measure"}
                bodies = [page(host="producer.test", suffix="release" + str(index)) for index in range(5)]
                lookup = {body["url"]: body for body in bodies}
                hints = [{"url": body["url"], "discovery_only": True} for body in bodies]
                directory = {"by_request": {req["id"]: {"items": hints[:4]}, second["id"]: {"items": hints[1:]}}}
                async def extract(body, requests, config):
                    # The second measure's table only exists in its own last URL.
                    return [{**observation(), "request_id": item["id"]} for item in requests
                            if item["id"] == req["id"] or body["url"] == bodies[-1]["url"]]
                fetch = AsyncMock(side_effect=lambda url, domains: lookup[url])
                with patch.object(source, "_official_discovery", AsyncMock(return_value=directory)), patch.object(source, "_search_candidates", AsyncMock(side_effect=RuntimeError("directory_expected"))), patch.object(source, "_fetch_page", fetch), patch.object(source, "_extract_page_observations", extract):
                    result = await source.collect_sources("2026-09", "2026-10-03", [req, second], root)
                self.assertEqual(fetch.await_count, 5)
                self.assertEqual(result["status"], "ready")
                self.assertEqual(result["request_status"][second["id"]]["status"], "verified")
        asyncio.run(run())

    def test_secondary_query_survives_dated_plan_query_bound(self):
        req = {**request(), "chart_id": "s13-shape17", "series_name": "工业增加值", "release_lag_days": 20}
        queries = source._discovery_queries({"requests": [req], "query": "工业增加值 最新原始数据 site:producer.test"}, "2026-09", date(2026, 10, 3))
        self.assertLessEqual(len(queries), 3)
        self.assertTrue(any("site:broker-a.test" in query and "site:producer.test" not in query for query in queries))

    def test_secondary_dual_latest_collects_ready_not_primary_labeled(self):
        async def run():
            with TemporaryDirectory() as root:
                bodies = [page(period="2026-06", suffix="jun"), page(period="2026-07", suffix="jul"), page(suffix="aug-a"),
                          page(host="broker-b.test", broker="Broker Beta", suffix="aug-b")]
                lookup = {body["url"]: body for body in bodies}
                async def extract(body, requests, config):
                    suffix = body["url"].rsplit("/", 1)[-1]
                    return [observation("2026-06" if suffix.startswith("jun") else "2026-07" if suffix.startswith("jul") else "2026-08")]
                search = AsyncMock(side_effect=[{"items": [{"url": body["url"]} for body in bodies[:3]], "issues": []},
                                                {"items": [{"url": bodies[3]["url"]}], "issues": []}])
                with patch.object(source, "_official_discovery", AsyncMock(return_value={"by_request": {}})), patch.object(source, "_search_candidates", search), patch.object(source, "_fetch_page", AsyncMock(side_effect=lambda url, domains: lookup[url])), patch.object(source, "_extract_page_observations", extract):
                    result = await source.collect_sources("2026-09", "2026-10-03", [request()], root)
                self.assertEqual(result["status"], "ready")
                self.assertEqual(result["coverage"], {"required": 1, "verified": 1})
                self.assertTrue(all(item["source_grade"] == "secondary" for item in result["observations"]))
        asyncio.run(run())

    def test_locator_failure_preserves_exact_table_for_another_request(self):
        async def run():
            with TemporaryDirectory() as root:
                req = {**request(), "source_domains": ["producer.test"], "original_publisher_domains": ["producer.test"], "secondary_source_domains": [], "history_count": 1}
                second = {**req, "id": "other", "definition_aliases": ["Other PMI"], "definition": "Other PMI"}
                html = '<meta name="PublishDate" content="2026-09-25"><table><tr><th>Period</th><th>Manufacturing PMI</th></tr><tr><td>August 2026</td><td>49.4</td></tr></table>'
                parsed = source.parse_page(html, "https://producer.test/report.html")
                body = {**parsed, "receipt_id": "table", "fetched_at": "2026-10-03T00:00:00Z", "fetch_provider": "direct-public-publisher", "text_sha256": hashlib.sha256(parsed["text"].encode()).hexdigest()}
                with patch.object(source, "_official_discovery", AsyncMock(return_value={"by_request": {}})), patch.object(source, "_search_candidates", AsyncMock(return_value={"items": [{"url": body["url"]}], "issues": []})), patch.object(source, "_fetch_page", AsyncMock(return_value=body)), patch.object(source, "_extract_page_observations", AsyncMock(side_effect=ValueError("locator_failed"))):
                    result = await source.collect_sources("2026-09", "2026-10-03", [req, second], root)
                self.assertEqual(result["request_status"][req["id"]]["status"], "verified")
                self.assertEqual(result["request_status"][second["id"]]["status"], "missing")
        asyncio.run(run())

    def test_dated_retained_source_plan_precedes_undated_broad_query(self):
        req = {**request(), "chart_id": "s13-shape17", "series_name": "工业增加值", "frequency": "monthly",
               "secondary_source_domains": [], "source_domains": ["stats.gov.cn"], "original_publisher_domains": ["stats.gov.cn"], "release_lag_days": 20}
        queries = source._discovery_queries({"requests": [req], "query": "工业增加值 最新发布 原始历史数据 site:stats.gov.cn"}, "2026-09", date(2026, 10, 3))
        self.assertIn("2026年8月", queries[0])
        self.assertIn("2026年8月", queries[-1])

    def test_quarter_and_month_history_hints_retarget_retained_plan(self):
        req = {**request(), "chart_id": "s10-shape7", "frequency": "quarterly", "secondary_source_domains": []}
        queries = source._discovery_queries({"requests": [req], "query": "GDP 最新原始数据", "history_hint": "2025年4季度"}, "2026-09", date(2026, 10, 3))
        self.assertIn("2025年第4季度", queries[0])
        self.assertIn("2025年", queries[0])
        req["chart_id"] = "s13-shape17"; req["frequency"] = "monthly"
        queries = source._discovery_queries({"requests": [req], "query": "工业增加值", "history_hint": "2026年6月"}, "2026-09", date(2026, 10, 3))
        self.assertIn("2026年6月", queries[0])

    def test_official_directory_urls_precede_search_and_still_fetch_originals(self):
        async def run():
            with TemporaryDirectory() as root:
                req = {**request(), "secondary_source_domains": [], "history_count": 1}
                body = page(host="producer.test")
                directory = {"by_request": {req["id"]: {"items": [{"url": body["url"], "published_at": "2026-01-01", "discovery_only": True}]}}}
                search = AsyncMock(side_effect=RuntimeError("directory_must_take_priority"))
                fetch = AsyncMock(return_value=body)
                with patch.object(source, "_official_discovery", AsyncMock(return_value=directory)), patch.object(source, "_search_candidates", search), patch.object(source, "_fetch_page", fetch), patch.object(source, "_extract_page_observations", AsyncMock(return_value=[observation()])):
                    result = await source.collect_sources("2026-09", "2026-10-03", [req], root)
                self.assertEqual(result["status"], "ready")
                self.assertEqual(search.await_count, 0)
                self.assertEqual(fetch.await_count, 1)
                self.assertEqual(result["observations"][0]["published_at"], body["published_at"])
        asyncio.run(run())

    def test_eight_week_history_is_not_limited_to_two_supplements(self):
        async def run():
            with TemporaryDirectory() as root:
                req = {**request(), "frequency": "weekly", "history_count": 8, "unit": "%", "definition": "唐山高炉开工率", "series_name": "唐山高炉开工率", "definition_aliases": ["唐山高炉开工率"], "secondary_source_domains": [], "template_latest_period": "2026-07-01", "query": "唐山高炉开工率"}
                calls = []
                async def search(query, domains):
                    calls.append(query)
                    match = source.re.search(r"2026-\d{2}-\d{2}", query)
                    period = match.group() if match else "2026-09-25"
                    return {"items": [{"url": "https://producer.test/" + period + ".html"}], "issues": []}
                async def fetch(url, domains):
                    period = url.rsplit("/", 1)[-1].replace(".html", "")
                    text = f"发布时间：2026-09-26；{period} 唐山高炉开工率 94.3%"
                    return {"url": url, "text": text, "published_at": "2026-09-26", "tables": [], "receipt_id": period,
                            "fetched_at": "2026-10-03T00:00:00Z", "fetch_provider": "direct-public-publisher", "text_sha256": hashlib.sha256(text.encode()).hexdigest()}
                async def extract(body, requests, config):
                    period = body["url"].rsplit("/", 1)[-1].replace(".html", "")
                    return [{"request_id": req["id"], "period": period, "value": 94.3, "unit": "%", "definition": req["definition"],
                             "quote": f"{period} 唐山高炉开工率 94.3%", "period_quote": period, "definition_quote": "唐山高炉开工率", "value_text": "94.3%"}]
                with patch.object(source, "_official_discovery", AsyncMock(return_value={"by_request": {}})), patch.object(source, "_search_candidates", search), patch.object(source, "_fetch_page", fetch), patch.object(source, "_extract_page_observations", extract):
                    result = await source.collect_sources("2026-09", "2026-10-03", [req], root)
                self.assertEqual(result["status"], "ready")
                self.assertGreaterEqual(len(result["observations"]), 8)
                self.assertGreater(len(calls), 3)
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
