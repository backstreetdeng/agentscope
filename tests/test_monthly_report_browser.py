from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from tools.monthly_report_browser import (
    MONTHLY_REPORT_BROWSER,
    PLAYWRIGHT_MCP_CLI,
    MonthlyReportBrowserConnector,
    MonthlyReportBrowserReconnectionRequired,
    MonthlyReportSessionOwnerMismatch,
    _card_has_current_period,
    _mapping_card_codes,
    _page_card_codes,
)


class MonthlyReportBrowserConnectorTests(unittest.TestCase):
    def test_saved_package_contains_same_path_returned_to_caller(self) -> None:
        with TemporaryDirectory() as directory:
            result = {"cards": [], "report_month": "2026-08"}
            with patch("tools.monthly_report_browser.SNAPSHOT_DIR", Path(directory)):
                MONTHLY_REPORT_BROWSER._save_data_package(result, "saved-view")
            path = Path(result["snapshot_path"])
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["snapshot_path"], str(path.resolve()))
            self.assertEqual(saved["snapshot_path"], result["snapshot_path"])

    def test_playwright_mcp_is_installed(self) -> None:
        self.assertTrue(PLAYWRIGHT_MCP_CLI.is_file())

    def test_mapping_cards_are_discovered(self) -> None:
        codes = _mapping_card_codes()
        self.assertGreaterEqual(len(codes), 30)
        self.assertIn("P1.1-1", codes)
        self.assertIn("P2-14.2", codes)

    def test_page_inventory_includes_all_45_dashboard_cards(self) -> None:
        codes = _page_card_codes()
        self.assertEqual(len(codes), 45)
        self.assertIn("P1.2-3A", codes)
        self.assertIn("P1.2-3B", codes)

    def test_ready_snapshot_passes_connector_and_generation_gate(self) -> None:
        snapshot = "日期组合 整体市场销量 " + " ".join(_page_card_codes())
        result = MONTHLY_REPORT_BROWSER._assess_snapshot(snapshot)
        self.assertTrue(result["page_ready"])
        self.assertTrue(result["connector_ready"])
        self.assertTrue(result["generation_ready"])
        self.assertEqual(result["mapping_coverage_pct"], 100.0)

    def test_partial_long_page_snapshot_is_warning_not_blocker(self) -> None:
        snapshot = "日期组合 整体市场销量 P1.1-1 P1.1-2"
        result = MONTHLY_REPORT_BROWSER._assess_snapshot(snapshot)
        self.assertTrue(result["page_ready"])
        self.assertTrue(result["connector_ready"])
        self.assertTrue(result["generation_ready"])
        self.assertEqual(result["mapping_cards_expected"], 45)
        self.assertEqual(result["code"], "data_source_connector_ready_with_snapshot_warning")

    def test_legacy_source_punctuation_maps_to_canonical_card_ids(self) -> None:
        snapshot = "日期组合 整体市场销量 P1.1-1 P2.8-1 P2.10-2 P2.12-1"
        result = MONTHLY_REPORT_BROWSER._assess_snapshot(snapshot)
        self.assertIn("P2-8.1", result["matched_cards"])
        self.assertIn("P2-10.2", result["matched_cards"])
        self.assertIn("P2-12.1", result["matched_cards"])

    def test_login_snapshot_is_blocked(self) -> None:
        result = MONTHLY_REPORT_BROWSER._assess_snapshot("请输入用户名和密码登录")
        self.assertFalse(result["page_ready"])
        self.assertFalse(result["generation_ready"])
        self.assertEqual(result["code"], "data_source_login_required")

    def test_loaded_shell_is_not_misreported_as_login_failure(self) -> None:
        result = MONTHLY_REPORT_BROWSER._assess_snapshot("数据部 数据分析 数据应用 数据准备")
        self.assertFalse(result["page_ready"])
        self.assertFalse(result["generation_ready"])
        self.assertEqual(result["code"], "data_source_page_not_ready")

    def test_evaluate_result_parser_ignores_playwright_audit_suffix(self) -> None:
        raw = '### Result\n{"cards":[{"code":"P1.1-1","text":"销量 123"}]}\n### Ran Playwright code\n```js\n() => ({x: 1})\n```'
        result = MONTHLY_REPORT_BROWSER._parse_evaluate_payload(raw)
        self.assertEqual(result["cards"][0]["code"], "P1.1-1")

    def test_region_cards_inherit_dashboard_month_but_require_current_year(self) -> None:
        text = "P2.8-1：乘用车月报-区域-省份\n2025\n2026\n广东\n208930\n166038"
        self.assertTrue(_card_has_current_period("P2-8.1", text, "2026-08"))
        self.assertFalse(_card_has_current_period("P2-8.1", text, "2027-08"))

    def test_point_in_time_cards_inherit_dashboard_period(self) -> None:
        text = "P1.2-3A：库存-TOP20企业\n企业简称\n总计\n长安汽车\n464764"
        self.assertTrue(_card_has_current_period("P1.2-3A", text, "2026-08"))

    def test_monthly_card_must_contain_current_period(self) -> None:
        stale = "P2-6.1：车型系别-单月销量\n2025-05\n1189772"
        fresh = stale + "\n2026-08\n1083713"
        self.assertFalse(_card_has_current_period("P2-6.1", stale, "2026-08"))
        self.assertTrue(_card_has_current_period("P2-6.1", fresh, "2026-08"))

    def test_month_indexed_new_car_cards_inherit_dashboard_year(self) -> None:
        stale = "P1.2-2B：新车-新能源类型\n07\n921791\n589360"
        fresh = stale + "\n08\n860014\n703958"
        self.assertFalse(_card_has_current_period("P1.2-2B", stale, "2026-08"))
        self.assertTrue(_card_has_current_period("P1.2-2B", fresh, "2026-08"))
        self.assertTrue(_card_has_current_period("P1.2-2D", fresh, "2026-08"))


class MonthlyReportPreflightTests(unittest.IsolatedAsyncioTestCase):
    async def test_pipe_only_dedicated_chrome_refuses_second_launch(self) -> None:
        connector = MonthlyReportBrowserConnector()
        pipe_only_process = {
            "pid": 4101,
            "owner": "same-user",
            "cdp_port": 0,
            "listener_pid": 0,
        }

        with (
            patch.object(connector, "_assert_session_owner"),
            patch.object(connector, "_current_windows_user", return_value="same-user"),
            patch(
                "tools.monthly_report_browser._dedicated_chrome_processes",
                return_value=[pipe_only_process],
            ),
            patch.object(connector, "_launch_detached_chrome") as launch,
            self.assertRaisesRegex(
                MonthlyReportBrowserReconnectionRequired,
                "旧版私有管道",
            ),
        ):
            await connector._ensure_detached_endpoint()

        launch.assert_not_called()

    async def test_existing_cdp_process_with_matching_identity_is_reused(self) -> None:
        connector = MonthlyReportBrowserConnector()
        identity = {
            "pid": 4102,
            "owner": "same-user",
            "owner_sid": "same-sid",
            "executable": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            "cdp_port": connector.cdp_port,
            "listener_pid": 4102,
        }

        with (
            patch.object(connector, "_assert_session_owner"),
            patch.object(connector, "_current_windows_user", return_value="same-user"),
            patch.object(connector, "_current_windows_sid", return_value="same-sid"),
            patch("tools.monthly_report_browser.Path.is_file", return_value=True),
            patch(
                "tools.monthly_report_browser._dedicated_chrome_processes",
                side_effect=[[identity], [identity]],
            ) as inspect_processes,
            patch(
                "tools.monthly_report_browser._port_is_listening",
                return_value=True,
            ) as port_is_listening,
            patch.object(connector, "_launch_detached_chrome") as launch,
            patch.object(connector, "_record_browser_runtime"),
        ):
            result = await connector._ensure_detached_endpoint()

        self.assertEqual(result, identity)
        self.assertEqual(inspect_processes.call_count, 2)
        port_is_listening.assert_called_once_with(connector.cdp_port)
        launch.assert_not_called()

    async def test_cdp_port_listener_identity_mismatch_is_rejected(self) -> None:
        connector = MonthlyReportBrowserConnector()
        existing = {
            "pid": 4103,
            "owner": "same-user",
            "owner_sid": "same-sid",
            "executable": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            "cdp_port": connector.cdp_port,
            "listener_pid": 4103,
        }
        mismatched_listener = {
            **existing,
            "listener_pid": 9999,
        }

        with (
            patch.object(connector, "_assert_session_owner"),
            patch.object(connector, "_current_windows_user", return_value="same-user"),
            patch.object(connector, "_current_windows_sid", return_value="same-sid"),
            patch("tools.monthly_report_browser.Path.is_file", return_value=True),
            patch(
                "tools.monthly_report_browser._dedicated_chrome_processes",
                side_effect=[[existing], [mismatched_listener]],
            ),
            patch("tools.monthly_report_browser._port_is_listening", return_value=True),
            patch.object(connector, "_launch_detached_chrome") as launch,
            self.assertRaisesRegex(RuntimeError, "监听进程.*不一致"),
        ):
            await connector._ensure_detached_endpoint()

        launch.assert_not_called()

    async def test_closed_tracked_tab_reuses_live_bi_instead_of_relaunching(self) -> None:
        connector = MonthlyReportBrowserConnector()
        closed_tab = MagicMock()
        closed_tab.is_closed.return_value = True
        bi_tab = MagicMock(url=connector.source_url)
        bi_tab.is_closed.return_value = False
        login_tab = MagicMock(url="https://dicp.catarc-adc.com:18082/#/login")
        login_tab.is_closed.return_value = False
        connector._direct_page = closed_tab
        connector._direct_context = MagicMock(pages=[closed_tab, bi_tab, login_tab])

        with patch("tools.monthly_report_browser.async_playwright") as launch:
            page = await connector._ensure_direct_connected()

        self.assertIs(page, bi_tab)
        launch.assert_not_called()

    async def test_live_login_tab_does_not_hide_a_live_bi_tab(self) -> None:
        connector = MonthlyReportBrowserConnector()
        bi_tab = MagicMock(url=connector.source_url)
        bi_tab.is_closed.return_value = False
        login_tab = MagicMock(url="https://dicp.catarc-adc.com:18082/#/login")
        login_tab.is_closed.return_value = False
        connector._direct_page = login_tab
        connector._direct_context = MagicMock(pages=[bi_tab, login_tab])

        page = await connector._ensure_direct_connected()

        self.assertIs(page, bi_tab)

    async def test_cdp_rejects_an_unrelated_chrome_profile(self) -> None:
        connector = MonthlyReportBrowserConnector()
        session = MagicMock(
            send=AsyncMock(return_value={"arguments": ["--user-data-dir=unrelated-profile"]}),
            detach=AsyncMock(),
        )
        browser = MagicMock(new_browser_cdp_session=AsyncMock(return_value=session))

        with self.assertRaisesRegex(RuntimeError, "不属于月报专用浏览器"):
            await connector._verify_cdp_profile(browser)

        session.detach.assert_awaited_once()

    async def test_normal_cleanup_keeps_owned_browser_and_driver_alive(self) -> None:
        connector = MonthlyReportBrowserConnector()
        context = MagicMock(close=AsyncMock())
        runtime = MagicMock(stop=AsyncMock())
        connector._direct_context = context
        connector._direct_playwright = runtime

        await connector.close()

        context.close.assert_not_awaited()
        runtime.stop.assert_not_awaited()
        self.assertIs(connector._direct_context, context)

    async def test_cdp_cleanup_detaches_without_closing_live_window(self) -> None:
        connector = MonthlyReportBrowserConnector()
        context = MagicMock(close=AsyncMock())
        runtime = MagicMock(stop=AsyncMock())
        connector._direct_browser = MagicMock()
        connector._direct_context = context
        connector._direct_playwright = runtime

        await connector.close()

        context.close.assert_not_awaited()
        runtime.stop.assert_awaited_once()
        self.assertIsNone(connector._direct_context)

    async def test_quick_status_recognizes_sms_login_url_and_title(self) -> None:
        connector = MonthlyReportBrowserConnector()
        connector._call = AsyncMock(return_value={
            "url": "https://dicp.catarc-adc.com:18082/#/login",
            "title": "登录 - Role-Based Access Control",
            "text": "登录",
            "reportMonths": [],
        })

        result = await connector._quick_page_status()

        self.assertFalse(result["page_ready"])
        self.assertEqual(result["code"], "data_source_login_required")
        self.assertEqual(result["auth_session_state"], "login_required")
        self.assertIn("登录会话未恢复", result["message"])

    async def test_quick_status_recognizes_live_bi_page(self) -> None:
        connector = MonthlyReportBrowserConnector()
        connector._call = AsyncMock(return_value={
            "url": connector.source_url,
            "title": "乘用车月报-BI测试",
            "text": "P1.1-1 整体市场销量 2026-08",
            "reportMonths": ["2026-08"],
        })

        result = await connector._quick_page_status()

        self.assertTrue(result["page_ready"])
        self.assertEqual(result["auth_session_state"], "verified")
        self.assertEqual(result["report_month"], "2026-08")

    async def test_visible_logout_modal_overrides_loaded_card_titles(self) -> None:
        connector = MonthlyReportBrowserConnector()
        connector._call = AsyncMock(return_value={
            "url": connector.source_url, "title": "乘用车月报-BI测试",
            "text": "P1.1-1 整体市场销量 2026-08", "reportMonths": ["2026-08"],
            "dialogText": "状态异常 当前账号尝试在其他设备登录，本设备已自动下线。重新登录",
        })
        result = await connector._quick_page_status()
        self.assertFalse(result["page_ready"])
        self.assertEqual(result["code"], "data_source_login_required")
        self.assertEqual(result["report_month"], "")
        self.assertTrue(result["session_invalidated"])

    async def test_expired_session_preflight_does_not_navigate_or_probe_cards(self) -> None:
        connector = MonthlyReportBrowserConnector()
        connector.ensure_connected = AsyncMock()
        connector._quick_page_status = AsyncMock(return_value={
            "page_ready": False, "session_invalidated": True, "report_month": "",
            "code": "data_source_login_required", "page_text": "P1.1-1 2026-08",
            "auth_session_state": "login_required", "message": "BI登录已失效",
        })
        connector._call = AsyncMock()
        connector._recapture_cards_with_native_scroll = AsyncMock()
        with patch.object(connector, "_load_session_metadata", return_value={}), \
             patch.object(connector, "_save_snapshot"):
            result = await connector.preflight(open_page=True)
        self.assertFalse(result["page_ready"])
        connector._call.assert_not_awaited()
        connector._recapture_cards_with_native_scroll.assert_not_awaited()

    async def test_another_dashboard_on_same_host_is_not_the_monthly_source(self) -> None:
        connector = MonthlyReportBrowserConnector()
        connector._call = AsyncMock(return_value={
            "url": connector.source_url.rsplit("/", 1)[0] + "/another-dashboard",
            "title": "另一份月报",
            "text": "P1.1-1 整体市场销量 2026-08", "reportMonths": ["2026-08"],
        })
        result = await connector._quick_page_status()
        self.assertFalse(result["page_ready"])

    async def test_session_metadata_blocks_another_windows_account(self) -> None:
        connector = MonthlyReportBrowserConnector()
        with TemporaryDirectory() as temp_dir:
            metadata = Path(temp_dir) / "monthly-report-browser-session.json"
            metadata.write_text(
                json.dumps({"windows_user": "11489", "verified_at": "2026-10-07T18:00:00+08:00"}),
                encoding="utf-8",
            )
            with (
                patch("tools.monthly_report_browser.SESSION_METADATA_FILE", metadata),
                patch.object(connector, "_current_windows_user", return_value="another-user"),
            ):
                with self.assertRaises(MonthlyReportSessionOwnerMismatch):
                    connector._assert_session_owner()

    async def test_preflight_maps_reconnection_required_without_closing_driver(self) -> None:
        connector = MonthlyReportBrowserConnector()
        legacy_driver = MagicMock(is_connected=True, close=AsyncMock())
        connector._client = legacy_driver
        reason = (
            "已登录的月报专用 Chrome 仍在运行，但使用旧版私有管道，不能重新连接。"
            "需要经你允许后做一次连接方式迁移。"
        )

        with (
            patch.object(
                connector,
                "ensure_connected",
                new=AsyncMock(
                    side_effect=MonthlyReportBrowserReconnectionRequired(reason),
                ),
            ) as connect,
            patch.object(connector, "close", new=AsyncMock()) as close,
        ):
            result = await connector.preflight(open_page=False)

        self.assertEqual(result["code"], "data_source_browser_reconnect_required")
        self.assertEqual(result["message"], reason)
        self.assertTrue(result["connected"])
        connect.assert_awaited_once_with()
        close.assert_not_awaited()
        legacy_driver.close.assert_not_awaited()

    async def test_preflight_reuses_validated_same_month_package_after_lightweight_check(self) -> None:
        with TemporaryDirectory() as temp_dir:
            snapshot_dir = Path(temp_dir)
            package = snapshot_dir / "data-source-package-20260929-095102.json"
            cards = []
            for code in _page_card_codes():
                if code in {"P1.1-2", "P1.2-2B", "P1.2-2D"}:
                    text = f"{code}：历史月均销量\n08\n168.0"
                elif code in {"P1.2-3A", "P1.2-3B"}:
                    text = f"{code}：当前快照\n企业\n123"
                else:
                    text = f"{code}：累计校验样本\n2026\n123"
                cards.append({"code": code, "text": text})
            package.write_text(
                json.dumps({
                    "generation_ready": True,
                    "report_month": "2026-08",
                    "cards_expected": 45,
                    "cards_captured": 45,
                    "cards_usable": 45,
                    "cards": cards,
                    "captured_at": "2026-09-29T09:51:02+08:00",
                    "source_url": MONTHLY_REPORT_BROWSER.source_url,
                }),
                encoding="utf-8",
            )
            with (
                patch("tools.monthly_report_browser.SNAPSHOT_DIR", snapshot_dir),
                patch("tools.monthly_report_browser.SESSION_METADATA_FILE", snapshot_dir / "test-session.json"),
                patch.object(MONTHLY_REPORT_BROWSER, "ensure_connected", new=AsyncMock()) as connect,
                patch.object(MONTHLY_REPORT_BROWSER, "_call", new=AsyncMock()) as browser_call,
                patch.object(
                    MONTHLY_REPORT_BROWSER, "_recapture_cards_with_native_scroll",
                    new=AsyncMock(return_value=({"P1.1-1": "P1.1-1\n2025-01\n123\n2026-08\n456", "P1.2-1": "P1.2-1\n2026-08\n4119751"}, [])),
                ) as month_probe,
                patch.object(
                    MONTHLY_REPORT_BROWSER,
                    "_quick_page_status",
                    new=AsyncMock(return_value={
                        "page_ready": True,
                        "code": "data_source_page_ready",
                        "message": "数据源页面已连接。",
                        "report_month": "2025-01",
                        "page_text": "日期组合 整体市场销量 P1.1-1 2025-01",
                    }),
                ),
            ):
                result = await MONTHLY_REPORT_BROWSER.preflight(open_page=True)

            self.assertEqual(result["code"], "data_source_package_reused")
            self.assertTrue(result["generation_ready"])
            self.assertEqual(result["mapping_cards_matched"], 45)
            self.assertEqual(result["report_month"], "2026-08")
            self.assertEqual(result["snapshot_path"], str(package))
            self.assertEqual(result["data_package_path"], str(package))
            self.assertTrue(Path(result["preflight_snapshot_path"]).is_file())
            self.assertNotEqual(result["preflight_snapshot_path"], result["data_package_path"])
            browser_call.assert_not_awaited()
            self.assertEqual(month_probe.await_count, 2)
            self.assertEqual([c.args[0] for c in month_probe.await_args_list], [["P1.1-1"], ["P1.2-1"]])
            connect.assert_awaited_once()

    async def test_unconfirmed_anchor_month_cannot_reuse_visible_historical_month(self) -> None:
        connector = MonthlyReportBrowserConnector()
        with patch.object(connector, "_recapture_cards_with_native_scroll", new=AsyncMock(return_value=({}, []))):
            result = await connector._confirm_page_month({"page_ready": True, "report_month": "2025-01"})
        self.assertEqual(result["report_month"], "")
        self.assertEqual(result["month_confirmation"]["status"], "unconfirmed")

    async def test_preflight_does_not_reuse_package_from_another_month(self) -> None:
        with TemporaryDirectory() as temp_dir:
            snapshot_dir = Path(temp_dir)
            package = snapshot_dir / "data-source-package-20260929-095102.json"
            cards = [
                {"code": code, "text": f"{code}\n2026\n08\n123"}
                for code in _page_card_codes()
            ]
            package.write_text(
                json.dumps({
                    "generation_ready": True,
                    "report_month": "2026-08",
                    "cards_expected": 45,
                    "cards_captured": 45,
                    "cards_usable": 45,
                    "cards": cards,
                    "source_url": MONTHLY_REPORT_BROWSER.source_url,
                }),
                encoding="utf-8",
            )
            with patch("tools.monthly_report_browser.SNAPSHOT_DIR", snapshot_dir):
                result = MONTHLY_REPORT_BROWSER._load_recent_ready_package("2026-09")
            self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
