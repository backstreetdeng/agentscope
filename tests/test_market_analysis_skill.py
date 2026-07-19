"""市场月报 Skill 的离线回归测试，不依赖 MiniMax API。"""

from __future__ import annotations

import unittest
from pathlib import Path

from skills.market_analysis_skill.runtime import ANALYSIS_TYPE, MarketAnalysisSkill
from utils.text import strip_thinking


class MarketAnalysisSkillTest(unittest.TestCase):
    def test_default_business_dataset_can_be_parsed(self) -> None:
        context = MarketAnalysisSkill().prepare(
            "请生成中国乘用车月度市场分析报告。",
            ANALYSIS_TYPE,
        )

        self.assertTrue(context.active)
        self.assertIsNotNone(context.dataset_path)
        self.assertTrue(context.snapshots)
        self.assertIn(context.input_gate(), {"通过", "待补充"})
        self.assertIn("车型类别", context.prompt_context)
        self.assertIn("TOP15", context.prompt_context)
        self.assertIn("### 2.3 轿车级别分析", context.prompt_context)
        self.assertIn("禁止把 2.3/2.4/2.5 合并", context.prompt_context)

    def test_can_select_specified_month_sheet(self) -> None:
        dataset = (
            Path(__file__).resolve().parents[1]
            / "skills"
            / "market-analysis-skill"
            / "月报skill"
            / "1-5月报 AI验数.xlsx"
        )
        context = MarketAnalysisSkill().prepare(
            "请基于2026年4月数据生成中国乘用车月度市场分析报告。",
            ANALYSIS_TYPE,
            dataset,
            "4月",
        )

        self.assertTrue(context.active)
        self.assertEqual(context.selected_sheet, "4月")
        self.assertEqual([item.name for item in context.snapshots], ["4月"])
        self.assertIn("### 4月", context.prompt_context)


    def test_non_monthly_question_does_not_use_monthly_template(self) -> None:
        context = MarketAnalysisSkill().prepare("请判断15-20万元新能源SUV的进入机会。")

        self.assertFalse(context.active)
        self.assertEqual(context.prompt_context, "")


    def test_report_gate_marks_missing_sections(self) -> None:
        skill = MarketAnalysisSkill()
        context = skill.prepare("请生成中国乘用车月度市场分析报告。", ANALYSIS_TYPE)
        checks = skill.validate_report("## 核心数据速览\n仅有摘要。", context)

        self.assertTrue(
            any(item.check_id == "report_structure" and item.status in {"待补充", "风险"} for item in checks),
        )

    def test_unclosed_thinking_is_not_exposed(self) -> None:
        self.assertEqual(strip_thinking("<think>内部推理尚未结束"), "")
        self.assertEqual(strip_thinking("<think>内部推理</think>\n可展示结论"), "可展示结论")
