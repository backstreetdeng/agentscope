"""深度调研确定性引擎单测（utils/deep_research_engine.py）。

覆盖：计划 JSON 解析（正常/坏输出/兜底）、虚构引用清理、来源清单组装。
纯函数测试，不依赖网络。
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.deep_research_engine import (  # noqa: E402
    build_report_markdown,
    parse_plan,
    strip_invalid_cites,
)

SOURCES = [
    {"n": 1, "title": "工信部公告", "url": "https://www.miit.gov.cn/a", "tier": "P0", "as_of": "2026-11-06"},
    {"n": 2, "title": "行业白皮书", "url": "https://media.example.com/b", "tier": "P1", "as_of": "2026-11-06"},
]


class TestParsePlan(unittest.TestCase):
    def test_valid_plan(self):
        plan = parse_plan('{"intent":"comparison","depth":"L2","queries":["唐L 智驾芯片","理想L9 智驾芯片"]}')
        self.assertEqual(plan["intent"], "comparison")
        self.assertEqual(len(plan["queries"]), 2)

    def test_garbage_returns_empty(self):
        self.assertEqual(parse_plan("我觉得应该搜一下"), {})

    def test_empty_queries_returns_empty(self):
        self.assertEqual(parse_plan('{"intent":"report","depth":"L2","queries":[]}'), {})


class TestCitesAndAssembly(unittest.TestCase):
    def test_strip_invalid_cites(self):
        text = "结论A[cite:1]，结论B[cite:9]。"
        self.assertEqual(strip_invalid_cites(text, {1}), "结论A[cite:1]，结论B。")

    def test_build_report_appends_sources(self):
        report = build_report_markdown("## 一、结论摘要\n\n要点[cite:1][cite:2]。", SOURCES)
        self.assertIn("## 参考来源", report)
        self.assertIn("1. 工信部公告 — https://www.miit.gov.cn/a（P0，时点 2026-11-06）", report)
        self.assertIn("[cite:2]", report)

    def test_build_report_removes_fabricated_and_dup_source_section(self):
        body = "要点[cite:1][cite:7]。\n\n## 参考来源\n\n1. 假来源 — https://x.example"
        report = build_report_markdown(body, SOURCES)
        self.assertNotIn("[cite:7]", report)
        self.assertEqual(report.count("## 参考来源"), 1)
        self.assertNotIn("假来源", report)


if __name__ == "__main__":
    unittest.main()
