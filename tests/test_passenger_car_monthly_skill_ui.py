"""乘用车月报智能生成 Skill 的产品入口回归检查。"""

from __future__ import annotations

from pathlib import Path
import unittest


PROJECT = Path(__file__).resolve().parents[1]
HOME = (PROJECT / "home.html").read_text(encoding="utf-8")
ANALYSIS_HTML = (PROJECT / "strategy-analysis.html").read_text(encoding="utf-8")
ANALYSIS_JS = (PROJECT / "assets" / "strategy-analysis.js").read_text(encoding="utf-8")
SKILL_ROOT = PROJECT / "skills" / "market-analysis-skill" / "passenger-car-monthly-report"


class PassengerCarMonthlySkillUiTest(unittest.TestCase):
    def test_home_lists_only_the_new_product_skill(self) -> None:
        self.assertIn("市场分析 · skill_passenger_car_monthly_report", HOME)
        self.assertIn("data-skill='passenger_car_monthly_report'", HOME)
        self.assertIn("href='/strategy-analysis.html?skills=passenger_car_monthly_report'", HOME)
        self.assertIn("乘用车月报智能生成", HOME)
        self.assertNotIn("BI", HOME)
        self.assertNotIn("Code: skill_market_monthly_report", HOME)
        self.assertNotIn("行业市场分析（月报）", HOME)

    def test_market_workspace_binds_monthly_route_to_explicit_selection(self) -> None:
        combined = ANALYSIS_HTML + ANALYSIS_JS
        self.assertIn('["passenger_car_monthly_report", "乘用车月报智能生成"', ANALYSIS_JS)
        self.assertIn('selected.includes("passenger_car_monthly_report")', ANALYSIS_JS)
        self.assertIn('analysis_type: analysisType', ANALYSIS_JS)
        self.assertIn('mcp_plugins: mcpPlugins', ANALYSIS_JS)
        self.assertIn('newcar: "new-car"', ANALYSIS_JS)
        self.assertNotIn('["passenger_car_monthly_report", "乘用车月报智能生成", "数据源读取、映射验数、21页PPT与主旨句生成", true]', ANALYSIS_JS)
        self.assertNotIn('analysis_type: "market_monthly_report"', ANALYSIS_JS)
        self.assertIn("乘用车月报数据源", combined)
        self.assertIn("不得沿用上月数据或补造结论", combined)
        self.assertNotIn("请基于当前月报验数数据", combined)
        self.assertNotIn("BI看板", combined)

    def test_monthly_job_polling_survives_temporary_backend_restart(self) -> None:
        self.assertIn("async function fetchMonthlyJobSnapshot(runId)", ANALYSIS_JS)
        self.assertIn("isTransientMonthlyPollError", ANALYSIS_JS)
        self.assertIn("后端连接暂时中断，已保留 run_id=", ANALYSIS_JS)
        self.assertIn("任务检查点仍保留，不会重新创建任务", ANALYSIS_JS)
        self.assertIn("const job = await fetchMonthlyJobSnapshot(runId);", ANALYSIS_JS)

    def test_skill_package_contains_fixed_business_assets(self) -> None:
        self.assertTrue((SKILL_ROOT / "SKILL.md").is_file())
        self.assertTrue((SKILL_ROOT / "agents" / "openai.yaml").is_file())
        self.assertTrue((SKILL_ROOT / "assets" / "乘用车月报-数据源映射指标.xlsx").is_file())
        self.assertTrue((SKILL_ROOT / "assets" / "乘用车月报PPT兼容模板.pptx").is_file())


if __name__ == "__main__":
    unittest.main()
