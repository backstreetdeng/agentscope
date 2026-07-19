"""市场月报 Skill 的离线回归测试，不依赖 MiniMax API。"""

from __future__ import annotations

import unittest
from pathlib import Path

from skills.market_analysis_skill.runtime import (
    ANALYSIS_TYPE,
    MarketAnalysisSkill,
    normalize_top15_summary_wording,
)
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

    def test_recognizes_top_model_tables_without_top_header_text(self) -> None:
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
        checks = {item.check_id: item for item in context.input_checks}

        self.assertEqual(checks["model_rank_data"].status, "通过")
        self.assertEqual(checks["brand_concentration"].status, "待补充")
        self.assertIn("星愿", context.prompt_context)

    def test_report_gate_rejects_unsupported_causal_attribution(self) -> None:
        skill = MarketAnalysisSkill()
        context = skill.prepare("请生成中国乘用车月度市场分析报告。", ANALYSIS_TYPE)
        checks = skill.validate_report(
            "## 核心数据速览\nSUV增长由新能源替代燃油车驱动。",
            context,
        )

        evidence_boundary = next(item for item in checks if item.check_id == "evidence_boundary")
        self.assertEqual(evidence_boundary.status, "风险")
        self.assertIn("新能源", evidence_boundary.evidence)

    def test_report_gate_rejects_scope_that_drops_cross_category(self) -> None:
        skill = MarketAnalysisSkill()
        context = skill.prepare("请生成中国乘用车月度市场分析报告。", ANALYSIS_TYPE)
        checks = skill.validate_report("## 核心数据速览\n狭义乘用车销量下降。", context)

        scope_check = next(item for item in checks if item.check_id == "scope_consistency")
        self.assertEqual(scope_check.status, "风险")

    def test_report_gate_rejects_unverified_statistical_caliber(self) -> None:
        skill = MarketAnalysisSkill()
        context = skill.prepare("请生成中国乘用车月度市场分析报告。", ANALYSIS_TYPE)
        checks = skill.validate_report("## 核心数据速览\n本报告统计乘用车批发销量。", context)

        evidence_boundary = next(item for item in checks if item.check_id == "evidence_boundary")
        self.assertEqual(evidence_boundary.status, "风险")
        self.assertIn("批发", evidence_boundary.evidence)

    def test_report_gate_rejects_false_top15_data_gap_claim(self) -> None:
        skill = MarketAnalysisSkill()
        context = skill.prepare("请基于2026年4月数据生成中国乘用车月度市场分析报告。", ANALYSIS_TYPE)
        checks = skill.validate_report(
            "## 核心数据速览\nTOP15摘要仅列前三，TOP4-15排名未注入。",
            context,
        )

        fidelity_check = next(item for item in checks if item.check_id == "top15_source_fidelity")
        self.assertEqual(fidelity_check.status, "风险")

    def test_top15_summary_wording_is_normalized_without_changing_data(self) -> None:
        skill = MarketAnalysisSkill()
        context = skill.prepare("请基于2026年4月数据生成中国乘用车月度市场分析报告。", ANALYSIS_TYPE)
        report, events = normalize_top15_summary_wording(
            "TOP15摘要仅列前三，TOP4-15排名未注入，不生成虚构结论。",
            context,
        )

        self.assertIn("完整 TOP15 可回溯至原始表", report)
        self.assertNotIn("未注入", report)
        self.assertTrue(events)

    def test_report_gate_rejects_unverified_new_model_claim(self) -> None:
        skill = MarketAnalysisSkill()
        context = skill.prepare("请生成中国乘用车月度市场分析报告。", ANALYSIS_TYPE)
        checks = skill.validate_report("## 核心数据速览\n新车型上市带动SUV表现。", context)

        evidence_boundary = next(item for item in checks if item.check_id == "evidence_boundary")
        self.assertEqual(evidence_boundary.status, "风险")
        self.assertIn("新车型", evidence_boundary.evidence)

    def test_report_gate_rejects_unmeasured_demand_causality(self) -> None:
        skill = MarketAnalysisSkill()
        context = skill.prepare("请生成中国乘用车月度市场分析报告。", ANALYSIS_TYPE)
        checks = skill.validate_report("## 核心数据速览\n销量下滑反映终端总需求处于主动收缩。", context)

        evidence_boundary = next(item for item in checks if item.check_id == "evidence_boundary")
        self.assertEqual(evidence_boundary.status, "风险")
        self.assertIn("终端总需求", evidence_boundary.evidence)


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
