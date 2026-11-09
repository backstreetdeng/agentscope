"""深度调研报告验收规则单测（utils/research_report_validation.py）。

覆盖：正常通过 / 虚构引用 / 缺必需章节 / 空来源与坏引用占位。
纯函数测试，不依赖数据库与网络。
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.research_report_validation import validate_research_report  # noqa: E402


def _report(cites: str = "[cite:1]", sources: str = "1. 工信部公告 — https://www.miit.gov.cn/a（P0，2026-10）") -> str:
    return (
        "# 对比分析报告\n\n"
        "## 结论摘要\n\n"
        f"唐L 续航优于理想 L9{cites}。整体判断为机会，置信度中。\n"
        "唐L 在纯电续航与补能效率两个维度占优；理想 L9 在增程无里程焦虑与空间舒适性上占优。\n"
        "综合判断：家用多场景用户更适配理想 L9，充电条件良好的用户更适配唐L。\n\n"
        "## 对比口径\n\n"
        "对比时点 2026-10，价格均为厂商指导价口径；续航均为 CLTC 工况，不与 WLTC 混算。\n\n"
        "## 分维度对比\n\n"
        "| 维度 | 唐L | 理想 L9 | 来源 | 口径备注 |\n"
        "|---|---|---|---|---|\n"
        "| 纯电续航 | 200km | 180km | [cite:1] | CLTC 申报值 |\n"
        "| 电池能量 | 35.2kWh | 42.8kWh | [cite:1] | 申报值 |\n\n"
        "## 缺口声明\n\n"
        "智驾方案实测数据 [数据不足]；双方交付周期未获取到一致口径来源。\n\n"
        "## 参考来源\n\n"
        f"{sources}\n"
    )


class TestResearchReportValidation(unittest.TestCase):
    def test_valid_report_passes(self):
        self.assertEqual(validate_research_report(_report()), [])

    def test_fabricated_citation_fails(self):
        failures = validate_research_report(_report(cites="[cite:9]"))
        self.assertTrue(any("不存在" in item for item in failures))

    def test_missing_required_sections_fail(self):
        text = _report().replace("## 结论摘要", "").replace("## 参考来源", "## 附录")
        failures = validate_research_report(text)
        self.assertTrue(any("结论摘要" in item for item in failures))
        self.assertTrue(any("参考来源" in item for item in failures))

    def test_empty_sources_and_bad_placeholder_fail(self):
        text = _report(cites="[cite:]", sources="")
        failures = validate_research_report(text)
        self.assertTrue(any("空引用占位" in item for item in failures))
        self.assertTrue(any("参考来源" in item for item in failures))

    def test_source_without_url_fails(self):
        text = _report(sources="1. 工信部公告（P0，2026-10）")
        failures = validate_research_report(text)
        self.assertTrue(any("缺少 URL" in item for item in failures))

    def test_too_short_report_fails(self):
        self.assertTrue(validate_research_report("太短"))


if __name__ == "__main__":
    unittest.main()
