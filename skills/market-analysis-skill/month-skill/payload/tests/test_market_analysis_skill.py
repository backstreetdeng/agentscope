"""Portable offline tests for the monthly market analysis Skill."""

from __future__ import annotations

import unittest
from pathlib import Path

from skills.market_analysis_skill.runtime import (
    ANALYSIS_TYPE,
    MarketAnalysisSkill,
    format_percent,
    normalize_sales_to_wan,
    strip_internal_evidence_markers,
)


PROJECT_DIR = Path(__file__).resolve().parents[1]
PROFILE_DIR = PROJECT_DIR / "skills" / "market_analysis_skill" / "profiles" / "passenger_vehicle_monthly"
DATASET_PATH = PROFILE_DIR / "assets" / "demo_monthly_data.xlsx"


class MarketAnalysisSkillTest(unittest.TestCase):
    def test_default_demo_dataset_can_be_parsed(self) -> None:
        context = MarketAnalysisSkill().prepare(
            "请生成中国乘用车月度市场分析报告。",
            ANALYSIS_TYPE,
        )

        self.assertTrue(context.active)
        self.assertEqual(context.selected_sheet, "6月")
        self.assertTrue(context.snapshots)
        self.assertIn(context.input_gate(), {"通过", "待补充"})
        self.assertIn("### 2.3 轿车级别分析", context.prompt_context)

    def test_can_select_specified_month(self) -> None:
        context = MarketAnalysisSkill().prepare(
            "请基于2026年5月数据生成中国乘用车月度市场分析报告。",
            ANALYSIS_TYPE,
            DATASET_PATH,
            "5月",
        )

        self.assertEqual(context.selected_sheet, "5月")
        self.assertEqual(len(context.top_model_records), 45)
        self.assertTrue(any(item.name == "秦PLUS" for item in context.top_model_records))

    def test_ordinary_strategy_question_does_not_activate(self) -> None:
        context = MarketAnalysisSkill().prepare("判断15-20万元新能源SUV在华中的进入机会。")
        self.assertFalse(context.active)
        self.assertEqual(context.prompt_context, "")

    def test_units_and_positive_sign_are_normalized(self) -> None:
        self.assertAlmostEqual(normalize_sales_to_wan(38373), 3.8373)
        self.assertEqual(format_percent(0.082), "8.2%")
        self.assertEqual(format_percent(-0.082), "-8.2%")

    def test_public_report_hides_internal_evidence_markers(self) -> None:
        cleaned, removed = strip_internal_evidence_markers("SUV增长〔R1〕，轿车承压〔E2〕。")
        self.assertEqual(cleaned, "SUV增长，轿车承压。")
        self.assertEqual(len(removed), 1)
        self.assertIn("服务端", removed[0])


if __name__ == "__main__":
    unittest.main()
