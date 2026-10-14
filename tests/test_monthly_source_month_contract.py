from __future__ import annotations
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch
from tools.monthly_report_browser import MonthlyReportBrowserConnector, _page_card_codes


def card_text(code, month="2026-08"):
    return f"{code}：月份核验测试卡片与业务数据\n日期\n{month}\n{month[-2:]}\n2026\n1234567\n同比\n-22.5%\n"


def package(connector, ready=True):
    return {"source_url": connector.source_url, "report_month": "2026-08",
            "generation_ready": ready, "cards_expected": 45, "cards_usable": 45 if ready else 2,
            "cards": [{"code": code, "text": card_text(code)} for code in _page_card_codes()]}


class SourceMonthContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_complete_package_preflight_and_collection_need_no_browser(self):
        c = MonthlyReportBrowserConnector()
        c.ensure_connected = AsyncMock(side_effect=AssertionError("No browser required"))
        c._quick_page_status = AsyncMock(side_effect=AssertionError("No login check required"))
        with TemporaryDirectory() as d:
            path = Path(d)/"data-source-package-saved.json"
            path.write_text(json.dumps(package(c)), encoding="utf-8")
            with patch("tools.monthly_report_browser.SNAPSHOT_DIR", Path(d)):
                preflight = await c.preflight(report_month="2026-08")
                collected = await c.read_all_cards(report_month="2026-08")
        self.assertTrue(preflight["generation_ready"])
        self.assertFalse(preflight["browser_required"])
        self.assertEqual(preflight["auth_session_state"], "not_checked")
        self.assertEqual(collected["cards_collected"], 0)
        c.ensure_connected.assert_not_awaited()
        c._quick_page_status.assert_not_awaited()

    async def test_invalid_or_wrong_month_package_still_requires_source(self):
        c = MonthlyReportBrowserConnector()
        c.ensure_connected = AsyncMock(side_effect=RuntimeError("Source unavailable"))
        with TemporaryDirectory() as d:
            path = Path(d)/"data-source-package-saved.json"
            path.write_text(json.dumps(package(c, ready=False)), encoding="utf-8")
            with patch("tools.monthly_report_browser.SNAPSHOT_DIR", Path(d)), patch.object(c, "_save_snapshot"):
                result = await c.preflight(report_month="2026-09")
        self.assertFalse(result["generation_ready"])
        c.ensure_connected.assert_awaited_once()

    async def test_mixed_sales_and_inventory_months_continue_with_delayed_inventory(self):
        c = MonthlyReportBrowserConnector()
        c._recapture_cards_with_native_scroll = AsyncMock(return_value=({
            "P1.1-1": "P1.1-1\n2026-08\n1555628\n2026-09\n1668934\n-26.6%\n7.3%",
            "P1.2-1": "P1.2-1\n2026-08\n4119751"}, []))
        r = await c._confirm_page_month({"page_ready": True})
        self.assertTrue(r["page_ready"])
        self.assertEqual(r["report_month"], "2026-09")
        self.assertEqual(r['month_confirmation']['delayed_anchors'], {'P1.2-1': '2026-08'})
        self.assertEqual(c._recapture_cards_with_native_scroll.await_count, 2)

    async def test_explicit_historical_month_allows_dated_backfill_after_sales_advance(self):
        c = MonthlyReportBrowserConnector()
        c._recapture_cards_with_native_scroll = AsyncMock(return_value=({
            "P1.1-1": "P1.1-1\n2026-08\n1555628\n2026-09\n1668934",
            "P1.2-1": "P1.2-1\n2026-08\n4119751"}, []))
        r = await c._confirm_page_month({"page_ready": True}, "2026-08")
        self.assertTrue(r["page_ready"])
        self.assertEqual(r["report_month"], "2026-08")
        self.assertFalse(r["month_confirmation"]["context_period_verified"])
        diag = c._card_diagnostics({"P1.1-3": "P1.1-3：2026年累计销量数据表格校验\n2026\n12345678\n同比\n-22.5%"}, "2026-08", context_verified=False)
        self.assertEqual(diag["P1.1-3"]["reason"], "ambiguous_period")

    async def test_explicit_august_uses_complete_package_without_card_probe(self):
        c = MonthlyReportBrowserConnector()
        c.ensure_connected = AsyncMock()
        c._quick_page_status = AsyncMock(return_value={"page_ready": True, "report_month": "2026-09"})
        c._recapture_cards_with_native_scroll = AsyncMock(side_effect=AssertionError("Do not reread cards"))
        with TemporaryDirectory() as d:
            path = Path(d)/"data-source-package-saved.json"
            path.write_text(json.dumps(package(c)), encoding="utf-8")
            with patch.dict("os.environ", {"MONTHLY_REPORT_REUSE_SNAPSHOT": "0", "MONTHLY_REPORT_SNAPSHOT_MAX_AGE": "1"}), patch("tools.monthly_report_browser.SNAPSHOT_DIR", Path(d)), patch.object(c, "_record_verified_session"), patch.object(c, "_load_session_metadata", return_value={}):
                r = await c.preflight(open_page=False, report_month="2026-08")
        self.assertTrue(r["generation_ready"])
        self.assertEqual(r["report_month"], "2026-08")
        self.assertEqual(r["collection_mode"], "reuse")
        self.assertEqual((r["cards_reused"], r["cards_collected"]), (45, 0))
        c._recapture_cards_with_native_scroll.assert_not_awaited()

    async def test_explicit_refresh_cannot_reuse_complete_package(self):
        c = MonthlyReportBrowserConnector()
        c.ensure_connected = AsyncMock()
        c._quick_page_status = AsyncMock(return_value={"page_ready": True})
        c._confirm_page_month = AsyncMock(return_value={"page_ready": True, "report_month": "2026-08"})
        with patch.object(c, "_load_recent_ready_package", side_effect=AssertionError("Cache disabled")), patch.object(c, "_record_verified_session"), patch.object(c, "_load_session_metadata", return_value={}), patch.object(c, "_save_snapshot"):
            r = await c.preflight(open_page=False, report_month="2026-08", force_refresh=True)
        self.assertFalse(r["generation_ready"])
        self.assertEqual(r["collection_mode"], "force_refresh")

    async def test_partial_package_never_reuses_year_only_cumulative_card(self):
        c = MonthlyReportBrowserConnector()
        data = package(c, False)
        data["cards"] = [{"code": "P1.1-1", "text": card_text("P1.1-1")},
                         {"code": "P1.1-3", "text": "P1.1-3：2026年累计销量数据表格校验\n2026\n12345678\n同比\n-22.5%"}]
        with TemporaryDirectory() as d:
            (Path(d)/"data-source-package-partial.json").write_text(json.dumps(data), encoding="utf-8")
            with patch("tools.monthly_report_browser.SNAPSHOT_DIR", Path(d)):
                reused = c._partial_package_cards("2026-08")
        self.assertEqual(set(reused), {"P1.1-1"})

    async def test_only_missing_card_is_read_and_later_month_cannot_change_target(self):
        c = MonthlyReportBrowserConnector()
        codes = _page_card_codes()
        pending = "P1.1-1"
        reused = {code: card_text(code) for code in codes if code != pending}
        c._quick_page_status = AsyncMock(return_value={"page_ready": True})
        c._confirm_page_month = AsyncMock(return_value={"page_ready": True, "report_month": "2026-08"})
        c._call = AsyncMock(return_value=json.dumps({"cards": [{"code": pending, "text": card_text(pending)+"2026-09\n1668934"}]}))
        with patch.object(c, "_load_recent_ready_package", return_value=None), patch.object(c, "_partial_package_cards", return_value=reused), patch.object(c, "_save_data_package"):
            r = await c.read_all_cards(report_month="2026-08")
        self.assertEqual(r["report_month"], "2026-08")
        self.assertTrue(r["generation_ready"])
        self.assertEqual((r["cards_reused"], r["cards_collected"]), (44, 1))
        self.assertIn('const wanted = new Set(["P1.1-1"])', c._call.call_args.kwargs["function"])

    async def test_inventory_present_but_no_september_has_precise_diagnostic(self):
        c = MonthlyReportBrowserConnector()
        r = c._card_diagnostics({"P1.2-1": card_text("P1.2-1")}, "2026-09")
        self.assertEqual(r["P1.2-1"]["reason"], "delayed_allowed")
        self.assertEqual(r["P1.2-1"]["latest_period"], "2026-08")
        self.assertEqual(r["P1.2-2A"]["reason"], "missing_card")

    async def test_explicit_september_allows_august_inventory(self):
        c = MonthlyReportBrowserConnector()
        c._recapture_cards_with_native_scroll = AsyncMock(return_value=({
            'P1.1-1': card_text('P1.1-1', '2026-09'),
            'P1.2-1': card_text('P1.2-1')}, []))
        r = await c._confirm_page_month({'page_ready': True}, '2026-09')
        self.assertTrue(r['page_ready'])
        self.assertEqual(r['report_month'], '2026-09')

    async def test_target_not_published_by_any_anchor_still_blocks(self):
        c = MonthlyReportBrowserConnector()
        c._recapture_cards_with_native_scroll = AsyncMock(return_value=({
            code: card_text(code) for code in ('P1.1-1', 'P1.2-1')}, []))
        r = await c._confirm_page_month({'page_ready': True}, '2026-09')
        self.assertFalse(r['page_ready'])

    async def test_future_unknown_and_incomplete_cards_are_not_delay_exceptions(self):
        c = MonthlyReportBrowserConnector()
        for value in (card_text('P1.2-1', '2026-10'), 'P1.2-1\n2026-08\n',
                      card_text('P1.2-1').replace('2026-08', '未确认')):
            self.assertNotEqual(c._card_diagnostics({'P1.2-1': value}, '2026-09')['P1.2-1']['status'], 'delayed_allowed')

    async def test_delayed_package_is_reusable_only_for_locked_month(self):
        c = MonthlyReportBrowserConnector()
        data = package(c)
        data['report_month'] = '2026-09'
        for card in data['cards']:
            if card['code'] != 'P1.2-1':
                card['text'] = card_text(card['code'], '2026-09')
        self.assertTrue(c.ready_package_for_month(data, '2026-09'))
        self.assertFalse(c.ready_package_for_month(data, '2026-08'))

if __name__ == "__main__":
    unittest.main()
