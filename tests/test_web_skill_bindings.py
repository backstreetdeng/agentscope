"""Web Skill 工具链的轻量回归检查。

前端页面目前以内嵌 JavaScript 的方式由 ``app.py`` 提供。此测试不启动浏览器，
但可阻止模板字符串被错误转义为 ``\\``` 后造成整段脚本无法解析的问题。
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

import app
from app import (
    HTML,
    build_final_answer_retry_config,
    generate_passenger_monthly_pptx,
    load_macro_monthly_skill_prompt,
    resolve_analysis_type,
    resolve_mcp_plugin_ids,
    run_agent_once,
)


PROJECT = Path(__file__).resolve().parents[1]
HOME_JS = (PROJECT / "assets" / "home.js").read_text(encoding="utf-8")
STRATEGY_ANALYSIS_JS = (PROJECT / "assets" / "strategy-analysis.js").read_text(encoding="utf-8")


class WebSkillBindingsTest(unittest.TestCase):
    def test_minimax_final_answer_retry_disables_thinking_without_mutating_source(self) -> None:
        config = {
            "active_provider": "minimax",
            "providers": {
                "minimax": {
                    "type": "openai_compatible",
                    "model": "MiniMax-M3",
                    "extra_body": {"reasoning_split": True},
                },
            },
        }

        retry = build_final_answer_retry_config(config)

        self.assertEqual(config["providers"]["minimax"]["extra_body"], {"reasoning_split": True})
        self.assertEqual(retry["providers"]["minimax"]["extra_body"]["reasoning_split"], True)
        self.assertEqual(retry["providers"]["minimax"]["extra_body"]["thinking"], {"type": "disabled"})

    def test_non_minimax_retry_keeps_provider_parameters(self) -> None:
        config = {
            "active_provider": "cloud",
            "providers": {"cloud": {"model": "gpt-4.1-mini", "extra_body": {"x": 1}}},
        }

        self.assertEqual(build_final_answer_retry_config(config), config)

    def test_skill_click_script_has_no_escaped_template_delimiter(self) -> None:
        self.assertNotIn(r"\`", HTML)
        self.assertNotIn(r"\${", HTML)

    def test_monthly_skill_mapping_and_click_binding_exist(self) -> None:
        self.assertIn('passenger_car_monthly_report', HTML)
        self.assertNotIn('skill_market_monthly_report', HTML)
        self.assertIn("closest('.btn-call-agent')", HOME_JS)
        self.assertIn('data-skill', HTML)

    def test_plugin_connection_status_does_not_auto_select_plugins(self) -> None:
        self.assertIn("card.classList.toggle('is-connected', plugin.status === 'ready')", HOME_JS)
        self.assertNotIn("cards.forEach((card) => card.classList.add('is-active'))", HOME_JS)

    def test_ppt_download_link_does_not_nest_a_template_expression(self) -> None:
        self.assertIn("const url = data.pptx_url || data.html_url;", STRATEGY_ANALYSIS_JS)
        self.assertIn("const pptLinkAttribute", STRATEGY_ANALYSIS_JS)
        self.assertIn('href="${escapeHtml(url)}"', STRATEGY_ANALYSIS_JS)
        self.assertNotIn('${data.pptx_url ? "download"', STRATEGY_ANALYSIS_JS)

    def test_four_market_data_plugins_are_selected_by_default(self) -> None:
        for plugin_id in ("policy", "rights", "newcar", "reputation"):
            self.assertRegex(
                STRATEGY_ANALYSIS_JS,
                rf'\["{plugin_id}",\s*"[^"]+",\s*"[^"]+",\s*true\]',
            )
        self.assertIn("requested.has(id) || checked", STRATEGY_ANALYSIS_JS)

    def test_macro_monthly_ui_runs_by_month_without_uploaded_ledger(self) -> None:
        strategy_html = (PROJECT / "strategy-analysis.html").read_text(encoding="utf-8")
        home_html = (PROJECT / "home.html").read_text(encoding="utf-8")
        self.assertIn('id="macroReportMonth"', strategy_html)
        self.assertIn("无需上传数据台账", strategy_html)
        self.assertIn('analysisType = macroEnabled ? "macro_monthly_report"', STRATEGY_ANALYSIS_JS)
        self.assertIn("逐页数据台账由智能体在执行过程中自动建立", STRATEGY_ANALYSIS_JS)
        self.assertNotIn('id="macroLedgerInput"', strategy_html)
        self.assertIn("data-skill='macro_monthly_report'", home_html)
        self.assertIn("href='/strategy-analysis.html?skills=macro_monthly_report&amp;model_provider=bailian_token_plan'", home_html)
        self.assertIn("<span class='skill-catalog-card__status'>已安装</span>", home_html)
        self.assertIn("skills: 'macro_monthly_report'", HOME_JS)
        self.assertIn("model_provider: 'bailian_token_plan'", HOME_JS)
        self.assertNotIn("month=2026-08", HOME_JS)


class PassengerMonthlyRoutingTest(unittest.IsolatedAsyncioTestCase):
    def test_monthly_route_requires_explicit_capability(self) -> None:
        with self.assertRaisesRegex(ValueError, "未选择"):
            resolve_analysis_type("passenger_car_monthly_report", [])
        self.assertEqual(
            resolve_analysis_type("", ["passenger_car_monthly_report"]),
            "passenger_car_monthly_report",
        )
        self.assertEqual(resolve_analysis_type("", ["policy"]), "")

    def test_macro_monthly_route_is_explicit_and_exclusive(self) -> None:
        self.assertEqual(
            resolve_analysis_type("", ["macro_monthly_report", "policy"]),
            "macro_monthly_report",
        )
        with self.assertRaisesRegex(ValueError, "不能在同一任务中同时执行"):
            resolve_analysis_type(
                "",
                ["passenger_car_monthly_report", "macro_monthly_report"],
            )

    def test_macro_skill_defines_ledger_as_internal_work_product(self) -> None:
        prompt = load_macro_monthly_skill_prompt()
        self.assertIn("Do not ask the user to create, select, or upload a data ledger", prompt)
        self.assertIn("Build the working ledger internally", prompt)

    def test_mcp_plugins_are_derived_from_selected_capabilities(self) -> None:
        self.assertEqual(
            resolve_mcp_plugin_ids(["policy", "newcar", "aippt"]),
            ["policy", "new-car"],
        )
        with self.assertRaisesRegex(ValueError, "不一致"):
            resolve_mcp_plugin_ids(["policy"], ["policy", "reputation"])

    async def test_new_monthly_route_never_calls_legacy_market_skill(self) -> None:
        package = {
            "code": "data_package_incomplete",
            "message": "test gate",
            "generation_ready": False,
            "cards_expected": 45,
            "cards_captured": 44,
            "cards_usable": 44,
            "missing_cards": ["P2-14.2"],
            "unusable_cards": [],
            "stale_cards": [],
        }
        with (
            patch("app.MONTHLY_REPORT_BROWSER.read_all_cards", new=AsyncMock(return_value=package)),
            patch("app.MarketAnalysisSkill", side_effect=AssertionError("legacy skill must not run")),
        ):
            result = await run_agent_once(
                "market_strategy",
                "生成本月乘用车月报",
                "passenger_car_monthly_report",
                model_provider="minimax",
            )

        self.assertEqual(result["skill"]["name"], "passenger-car-monthly-report")
        self.assertTrue(result["skill"]["legacy_excel_disabled"])
        self.assertIn("不会读取旧版月报 Excel", result["answer"])
        self.assertEqual(result["tool_events"][0]["name"], "monthly_report_read_all_cards")

    async def test_ready_data_only_route_waits_for_narrative_before_ppt_export(self) -> None:
        package = {
            "code": "data_package_ready",
            "generation_ready": True,
            "report_month": "2026-08",
            "cards_expected": 45,
            "cards_captured": 45,
            "cards_usable": 45,
            "snapshot_path": "E:/snapshot.json",
        }
        with (
            patch("app.MONTHLY_REPORT_BROWSER.read_all_cards", new=AsyncMock(return_value=package)),
            patch("app.MarketAnalysisSkill", side_effect=AssertionError("legacy skill must not run")),
        ):
            result = await run_agent_once(
                "market_strategy",
                "生成本月乘用车月报",
                "passenger_car_monthly_report",
                model_provider="minimax",
            )

        self.assertEqual(result["skill"]["output_gate"], "等待主旨句门禁")
        self.assertIn("45/45", result["answer"])
        self.assertIn("主旨句", result["answer"])


class PassengerMonthlyPptExportTest(unittest.TestCase):
    def test_export_releases_verified_compatible_template(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package_dir = root / "monthly-report-data"
            output_dir = root / "ppt"
            package_dir.mkdir()
            template = root / "template.pptx"
            template.write_bytes(b"PK-compatible-pptx")
            package = package_dir / "package.json"
            package.write_text(
                json.dumps({
                    "generation_ready": True,
                    "report_month": "2026-08",
                    "cards_expected": 45,
                    "cards_usable": 45,
                    "cards": [{"code": code, "text": f"{code}\n2026-08\n08\n2026\n123"}
                              for code in app._page_card_codes()],
                }, ensure_ascii=False),
                encoding="utf-8",
            )
            run_id = 'month-test-release'
            narrative = package_dir / 'narrative.json'
            narrative.write_text(json.dumps({'run_id':run_id,'report_month':'2026-08','slides':[]}),encoding='utf-8')
            job = {'status':'completed','checkpoints':{'data_collect':{'snapshot_path':str(package)},
                                                      'narrative':{'path':str(narrative)}}}
            def mock_writer(source, destination, _narrative):
                destination.write_bytes(source.read_bytes())
                return {'slides_written':[3], 'headline_count':1}
            with (
                patch.object(app, "PROJECT_DIR", root),
                patch.object(app, "PASSENGER_MONTHLY_PACKAGE_DIR", package_dir.resolve()),
                patch.object(app, "PASSENGER_MONTHLY_TEMPLATE_PATH", template),
                patch.object(app, "PPT_OUTPUT_DIR", output_dir),
                patch.object(app.MONTHLY_REPORT_JOBS, 'get', return_value=job),
                patch.object(app.MONTHLY_REPORT_JOBS, 'save_output_checkpoint') as checkpoint,
                patch.object(app, '_sha256_file', return_value='test-sha256'),
                patch.object(app, 'validate_narrative_package') as validate,
                patch.object(app, 'apply_narratives_to_ppt', side_effect=mock_writer) as writer,
            ):
                result = generate_passenger_monthly_pptx(run_id, "月报")
                self.assertEqual(validate.call_args.kwargs['run_id'], run_id)
                self.assertEqual(writer.call_args.args[2]['run_id'],run_id)
                self.assertEqual(checkpoint.call_args.args[:2],(run_id,'ppt_update'))

            output = output_dir / Path(result["pptx_url"]).name
            self.assertTrue(output.is_file())
            self.assertEqual(output.read_bytes(), template.read_bytes())
            self.assertTrue(output.with_suffix(".manifest.json").is_file())
            self.assertEqual(result["cards_usable"], 45)
            self.assertEqual(result['run_id'],run_id)
