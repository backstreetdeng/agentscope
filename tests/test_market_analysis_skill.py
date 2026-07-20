"""市场月报 Skill 的离线回归测试，不依赖 MiniMax API。"""

from __future__ import annotations

import unittest
from pathlib import Path

from skills.agent_reach.adapter import EvidenceItem
from skills.market_analysis_skill.runtime import (
    ANALYSIS_TYPE,
    ExternalEvidence,
    MarketAnalysisSkill,
    TopModelEvidence,
    normalize_external_evidence_marker_format,
    normalize_sales_to_wan,
    normalize_top15_summary_wording,
    strip_internal_evidence_markers,
)
from utils.text import strip_thinking


class MarketAnalysisSkillTest(unittest.TestCase):
    @staticmethod
    def _research_enabled_config() -> dict:
        """测试使用项目内已批准清单，不触发网络检索或 MiniMax 调用。"""

        return {
            "skills": {
                "market_analysis": {
                    "research_evidence": {
                        "enabled": True,
                        "manifest": "research/2026_china_passenger_vehicle_market_strategy_consulting/evidence_manifest.json",
                        "max_items": 6,
                        "max_chars_per_item": 500,
                    },
                },
            },
        }

    def test_default_business_dataset_can_be_parsed(self) -> None:
        context = MarketAnalysisSkill().prepare(
            "请生成中国乘用车月度市场分析报告。",
            ANALYSIS_TYPE,
        )

        self.assertTrue(context.active)
        self.assertIsNotNone(context.dataset_path)
        self.assertTrue(context.snapshots)
        self.assertEqual(context.selected_sheet, "5月")
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

    def test_full_top15_is_injected_and_sales_are_normalized_to_wan(self) -> None:
        context = MarketAnalysisSkill().prepare(
            "请基于2026年5月数据生成中国乘用车月度市场分析报告。",
            ANALYSIS_TYPE,
        )

        self.assertEqual(context.selected_sheet, "5月")
        self.assertEqual(len(context.top_model_records), 45)
        self.assertTrue(any(item.name == "秦PLUS" and item.rank == 10 for item in context.top_model_records))
        self.assertIn("15.海鸥", context.prompt_context)
        self.assertAlmostEqual(normalize_sales_to_wan(38373), 3.8373)
        self.assertAlmostEqual(normalize_sales_to_wan(3.8373), 3.8373)

    def test_research_evidence_is_loaded_only_for_matching_report_period(self) -> None:
        skill = MarketAnalysisSkill(self._research_enabled_config())

        may_context = skill.prepare(
            "请基于2026年5月数据生成中国乘用车月度市场分析报告。",
            ANALYSIS_TYPE,
        )
        april_context = skill.prepare(
            "请基于2026年4月数据生成中国乘用车月度市场分析报告。",
            ANALYSIS_TYPE,
            sheet_name="4月",
        )

        self.assertEqual(
            [item.evidence_id for item in may_context.research_evidence],
            ["R1", "R2", "R3", "R4", "R5", "R6"],
        )
        self.assertEqual([item.evidence_id for item in april_context.research_evidence], ["R1"])
        self.assertIn("研究证据；主题=2026政策与以旧换新规则", april_context.prompt_context)
        self.assertNotIn("5月TOP15代表车型与事件边界", april_context.prompt_context)
        self.assertTrue(any(item.stage == "research-evidence" and item.status == "success" for item in may_context.events))

    def test_report_gate_accepts_known_research_evidence_id_and_rejects_unknown_id(self) -> None:
        skill = MarketAnalysisSkill(self._research_enabled_config())
        context = skill.prepare(
            "请基于2026年5月数据生成中国乘用车月度市场分析报告。",
            ANALYSIS_TYPE,
        )

        valid_checks = skill.validate_report(
            "## 核心数据速览\n2026年以旧换新和购置税规则已明确，"
            "可作为政策机制的背景说明〔R1〕。",
            context,
        )
        valid_boundary = next(item for item in valid_checks if item.check_id == "evidence_boundary")
        valid_reference = next(item for item in valid_checks if item.check_id == "external_evidence_traceability")
        self.assertEqual(valid_boundary.status, "通过")
        self.assertEqual(valid_reference.status, "通过")

        invalid_checks = skill.validate_report(
            "## 核心数据速览\n政策影响已经验证〔R9〕。",
            context,
        )
        invalid_reference = next(item for item in invalid_checks if item.check_id == "external_evidence_traceability")
        self.assertEqual(invalid_reference.status, "风险")
        self.assertIn("R9", invalid_reference.evidence)

        causal_checks = skill.validate_report(
            "## 核心数据速览\n政策是市场下滑的核心驱动〔R1〕。",
            context,
        )
        causal_boundary = next(item for item in causal_checks if item.check_id == "evidence_boundary")
        self.assertEqual(causal_boundary.status, "风险")
        self.assertIn("研究证据被用于强因果", causal_boundary.evidence)

    def test_driver_signal_uses_top15_change_not_model_name_guess(self) -> None:
        model = TopModelEvidence(
            segment="轿车-级别",
            rank=10,
            name="秦PLUS",
            volume=1.215,
            yoy=-0.574,
            mom=-0.1,
            level="A",
            share=0.02,
            rank_change="-6",
            cumulative_volume=4.0,
        )

        self.assertAlmostEqual(model.yoy_delta or 0, -1.637, places=3)

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

        self.assertIn("完整 TOP15 已注入并可回溯至原始表", report)
        self.assertNotIn("未注入", report)
        self.assertTrue(events)

    def test_report_gate_allows_external_reason_only_with_existing_evidence_id(self) -> None:
        skill = MarketAnalysisSkill()
        context = skill.prepare("请生成中国乘用车月度市场分析报告。", ANALYSIS_TYPE)
        context.external_evidence = [
            ExternalEvidence(
                "E1",
                EvidenceItem(
                    title="行业月度分析",
                    url="https://www.cada.cn/example",
                    highlights="高油价影响传统车表现。",
                    source_tier="A",
                ),
                "行业宏观背景",
            ),
        ]
        checks = skill.validate_report("## 核心数据速览\n高油价下传统车表现承压〔E1〕。", context)
        evidence_boundary = next(item for item in checks if item.check_id == "evidence_boundary")
        evidence_reference = next(item for item in checks if item.check_id == "external_evidence_traceability")

        self.assertEqual(evidence_boundary.status, "通过")
        self.assertEqual(evidence_reference.status, "通过")

    def test_report_gate_rejects_unknown_external_evidence_id(self) -> None:
        skill = MarketAnalysisSkill()
        context = skill.prepare("请生成中国乘用车月度市场分析报告。", ANALYSIS_TYPE)
        context.external_evidence = [
            ExternalEvidence("E1", EvidenceItem(title="行业月度分析", url="https://www.cada.cn/example"), "行业宏观背景"),
        ]
        checks = skill.validate_report("## 核心数据速览\n高油价下传统车表现承压〔E9〕。", context)
        evidence_reference = next(item for item in checks if item.check_id == "external_evidence_traceability")

        self.assertEqual(evidence_reference.status, "风险")
        self.assertIn("E9", evidence_reference.evidence)

    def test_report_gate_rejects_combined_or_annotated_evidence_marker(self) -> None:
        skill = MarketAnalysisSkill()
        context = skill.prepare("请生成中国乘用车月度市场分析报告。", ANALYSIS_TYPE)
        context.external_evidence = [
            ExternalEvidence("E1", EvidenceItem(title="行业月度分析", url="https://www.cada.cn/example"), "行业宏观背景"),
            ExternalEvidence("E2", EvidenceItem(title="车型月度分析", url="https://www.bitauto.com/example"), "SUV代表车型"),
        ]
        checks = skill.validate_report("## 核心数据速览\n高油价影响传统车表现〔E1,E2〕。", context)
        evidence_reference = next(item for item in checks if item.check_id == "external_evidence_traceability")

        self.assertEqual(evidence_reference.status, "风险")
        self.assertIn("〔E1,E2〕", evidence_reference.evidence)

    def test_known_combined_evidence_markers_are_normalized_before_delivery_gate(self) -> None:
        skill = MarketAnalysisSkill()
        context = skill.prepare("请生成中国乘用车月度市场分析报告。", ANALYSIS_TYPE)
        context.external_evidence = [
            ExternalEvidence("E1", EvidenceItem(title="行业月度分析", url="https://www.cada.cn/example"), "行业宏观背景"),
            ExternalEvidence("E2", EvidenceItem(title="车型月度分析", url="https://www.bitauto.com/example"), "SUV代表车型"),
        ]
        normalized, events = normalize_external_evidence_marker_format(
            "高油价影响传统车表现〔E1,E2〕；另一条待核验线索〔E2,C级线索〕。",
            context,
        )

        self.assertEqual(normalized, "高油价影响传统车表现〔E1〕〔E2〕；另一条待核验线索〔E2〕。")
        self.assertEqual(len(events), 2)

    def test_unknown_evidence_marker_is_not_silently_rewritten(self) -> None:
        skill = MarketAnalysisSkill()
        context = skill.prepare("请生成中国乘用车月度市场分析报告。", ANALYSIS_TYPE)
        context.external_evidence = [
            ExternalEvidence("E1", EvidenceItem(title="行业月度分析", url="https://www.cada.cn/example"), "行业宏观背景"),
        ]
        normalized, events = normalize_external_evidence_marker_format("未经核验的来源〔E9,E1〕。", context)

        self.assertEqual(normalized, "未经核验的来源〔E9,E1〕。")
        self.assertFalse(events)

    def test_delivery_strips_internal_evidence_markers_after_audit(self) -> None:
        delivered, events = strip_internal_evidence_markers(
            "高油价下传统车表现承压〔E1〕，新能源渗透率继续提升〔R3〕。",
        )

        self.assertEqual(delivered, "高油价下传统车表现承压，新能源渗透率继续提升。")
        self.assertTrue(events)

    def test_report_gate_requires_ppt_ready_deep_analysis_paragraphs(self) -> None:
        skill = MarketAnalysisSkill()
        context = skill.prepare("请生成中国乘用车月度市场分析报告。", ANALYSIS_TYPE)
        report = "\n".join(
            [
                "### 2.1 车型类别",
                "只罗列数据，缺少可直接落入 PPT 的业务判断。",
                "### 2.2 车型级别",
                "只罗列数据，缺少可直接落入 PPT 的业务判断。",
                "### 2.3 轿车级别分析",
                "只罗列数据，缺少可直接落入 PPT 的业务判断。",
                "### 2.4 SUV级别分析",
                "只罗列数据，缺少可直接落入 PPT 的业务判断。",
                "### 2.5 MPV级别分析",
                "只罗列数据，缺少可直接落入 PPT 的业务判断。",
            ],
        )
        checks = skill.validate_report(report, context)
        deep_analysis = next(item for item in checks if item.check_id == "ppt_deep_analysis")

        self.assertEqual(deep_analysis.status, "风险")
        self.assertIn("2.1 车型类别", deep_analysis.evidence)

    def test_ppt_ready_paragraph_accepts_a_section_title_with_parenthetical_note(self) -> None:
        skill = MarketAnalysisSkill()
        context = skill.prepare("请生成中国乘用车月度市场分析报告。", ANALYSIS_TYPE)
        sections = (
            "2.1 车型类别",
            "2.2 车型级别",
            "2.3 轿车级别分析",
            "2.4 SUV级别分析",
            "2.5 MPV级别分析",
        )
        blocks = []
        for section in sections:
            candidates = [
                item.model.name
                for item in context.driver_signals
                if not section.startswith("2.3") or item.segment.startswith("轿车")
                if not section.startswith("2.4") or item.segment.startswith("SUV")
                if not section.startswith("2.5") or item.segment.startswith("MPV")
            ]
            model = candidates[0] if candidates else context.driver_signals[0].model.name
            summary = (
                f"◼ 5月，相关细分市场同比承压但结构分化延续；{model}的销量变化反映出代表车型"
                "之间的竞争强弱差异；高油价与同期基数等外部机制仍需按来源交叉核验；整体看，"
                "应继续跟踪新品承接、存量产品节奏、终端成交和下一期结构变化，并验证价格与交付因素，避免仅依据单月数据下结论。"
            )
            blocks.append(f"### {section}：结构变化与后续观察\n{summary}")
        report = "\n".join(blocks)

        checks = skill.validate_report(report, context)
        deep_analysis = next(item for item in checks if item.check_id == "ppt_deep_analysis")
        delivery_language = next(item for item in checks if item.check_id == "business_delivery_language")

        self.assertEqual(deep_analysis.status, "通过")
        self.assertEqual(delivery_language.status, "通过")

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
