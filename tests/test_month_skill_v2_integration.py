"""Exercise the installed host route without calling a model or web search."""
import asyncio
import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from pptx import Presentation
import app
from skills.market_analysis_skill.runtime import (
    ANALYSIS_TYPE, MarketAnalysisSkill, SheetSnapshot, infer_report_period,
    is_page_block_layout, validate_input_dataset,
)

PROJECT = Path(__file__).resolve().parents[1]
ASSETS = PROJECT / "skills/market_analysis_skill/profiles/passenger_vehicle_monthly/assets"
DATA = ASSETS / "demo_monthly_data.xlsx"


class MonthSkillV2IntegrationTest(unittest.TestCase):
    def config(self):
        config = copy.deepcopy(app.load_json_config())
        config["skills"]["market_analysis"]["external_evidence"]["enabled"] = False
        return config

    def test_host_default_selects_v2_and_excludes_top20_from_driver_records(self):
        skill = MarketAnalysisSkill(self.config())
        context = skill.prepare("生成当前月份月报", ANALYSIS_TYPE)
        self.assertEqual(skill.status()["version"], "2.0.0")
        self.assertEqual(context.dataset_path, DATA)
        self.assertEqual(context.selected_sheet, "6月")
        self.assertEqual(len(context.top_model_records), 45)
        self.assertEqual({r.segment for r in context.top_model_records}, {"轿车", "SUV", "MPV"})
        self.assertEqual(infer_report_period(context.snapshots[0], ""), "2026年6月")
        for term in ("P3", "P21", "库存", "企业竞争", "新能源", "23页"):
            self.assertIn(term, context.prompt_context)

    def test_invalid_file_month_and_year_do_not_fall_back(self):
        skill = MarketAnalysisSkill(self.config())
        for kwargs in ({"dataset_path": PROJECT / "missing.xlsx"},
                       {"question": "生成2026年8月月报"},
                       {"question": "生成2027年6月月报"}):
            options = {"question": "生成月报", "analysis_type": ANALYSIS_TYPE, **kwargs}
            self.assertEqual(skill.prepare(**options).input_gate(), "阻断")

    def test_incomplete_v2_is_blocked_instead_of_using_legacy(self):
        context = MarketAnalysisSkill(self.config()).prepare("生成月报", ANALYSIS_TYPE)
        sheet = context.snapshots[0]
        cut = next(i for i, row in enumerate(sheet.rows) if row and row[0].startswith("P21"))
        incomplete = SheetSnapshot(name="6月", rows=sheet.rows[:cut])
        self.assertTrue(is_page_block_layout(incomplete))
        checks = validate_input_dataset([incomplete], DATA)
        self.assertEqual(next(c.status for c in checks if c.check_id == "page_blocks"), "阻断")

    def test_old_sheet_keeps_old_prompt_and_five_page_template(self):
        from utils.monthly_report_pptx import build_monthly_report_pptx
        old = ASSETS / "demo_monthly_data_v1.xlsx"
        context = MarketAnalysisSkill().prepare("生成月报", ANALYSIS_TYPE, old, "5月")
        self.assertIn("### 2.4 SUV级别分析", context.prompt_context)
        with tempfile.TemporaryDirectory() as directory:
            result = build_monthly_report_pptx("", Path(directory) / "old.pptx", old, sheet_name="5月")
            self.assertEqual(result["slides_count"], 5)

    def test_chat_dispatches_v2_context_and_ppt_exports_installed_template(self):
        report = "# 2026年6月中国乘用车市场月报\n\n## 数据来源与数据缺口\n中汽数据验数；待补充。"
        fake = SimpleNamespace(reply=AsyncMock(return_value=SimpleNamespace(get_text_content=lambda: report)))
        config = self.config()
        with patch.object(app, "load_json_config", return_value=config), \
             patch.object(app, "load_dotenv"), \
             patch.object(app, "build_market_strategy_agent", return_value=fake) as builder:
            response = asyncio.run(app.run_agent_once("market_strategy", "生成2026年6月月报", ANALYSIS_TYPE, DATA, "6月"))
        self.assertEqual(response["skill"]["version"], "2.0.0")
        self.assertTrue(builder.call_args.kwargs["monthly_report"])
        self.assertIn("P21", builder.call_args.kwargs["skill_instruction"])
        with tempfile.TemporaryDirectory(dir=PROJECT / ".work") as directory, \
             patch.object(app, "PPT_OUTPUT_DIR", Path(directory)), \
             patch.object(app, "load_json_config", return_value=config):
            result = app.generate_ppt_from_markdown(report, "integration-smoke", ANALYSIS_TYPE, DATA, "6月")
            deck = Presentation(result["pptx_path"])
            self.assertEqual((len(deck.slides), result["charts_count"], result["tables_count"]), (23, 47, 37))
            self.assertTrue(result["template"].startswith(str(ASSETS)))
            self.assertEqual(result["delivery_status"], "待复核草稿")
            self.assertTrue(result["warnings"])

    def test_blocked_chat_does_not_invoke_model(self):
        with patch.object(app, "load_json_config", return_value=self.config()), \
             patch.object(app, "load_dotenv"), \
             patch.object(app, "build_market_strategy_agent") as builder:
            with self.assertRaisesRegex(RuntimeError, "输入门禁"):
                asyncio.run(app.run_agent_once("market_strategy", "生成2026年8月月报", ANALYSIS_TYPE))
            builder.assert_not_called()


if __name__ == "__main__":
    unittest.main()
