"""Agent Reach 项目内适配器的离线测试，不访问真实网络。"""

from __future__ import annotations

import json
import subprocess
import unittest
from unittest.mock import patch

from skills.agent_reach.adapter import classify_source_tier, search


class AgentReachAdapterTest(unittest.TestCase):
    def test_search_uses_exa_mcp_route_and_returns_structured_sources(self) -> None:
        payload = {
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Title: 行业月度分析\n"
                        "URL: https://www.cada.cn/report\n"
                        "Published: 2026-06-01\n"
                        "Author: 中国汽车流通协会\n"
                        "Highlights:\n高油价影响传统车表现。"
                    ),
                },
            ],
        }
        completed = subprocess.CompletedProcess([], 0, json.dumps(payload, ensure_ascii=False), "")
        with patch("skills.agent_reach.adapter.shutil.which", return_value="mcporter"), patch(
            "skills.agent_reach.adapter.subprocess.run",
            return_value=completed,
        ) as mocked_run:
            response = search("2026年5月乘用车市场", max_results=3)

        self.assertTrue(response.ok)
        self.assertEqual(response.items[0].source_tier, "A")
        self.assertIn("exa.web_search_exa", mocked_run.call_args.args[0])
        self.assertIn("numResults=3", mocked_run.call_args.args[0])

    def test_source_tier_distinguishes_authoritative_and_industry_domains(self) -> None:
        self.assertEqual(classify_source_tier("https://www.gov.cn/example"), "A")
        self.assertEqual(classify_source_tier("https://auto.gasgoo.com/example"), "B")
        self.assertEqual(classify_source_tier("https://example.com/article"), "C")

    def test_source_tier_recognizes_official_oem_domains(self) -> None:
        self.assertEqual(classify_source_tier("https://www.buick.com.cn/news/432"), "A")
        self.assertEqual(classify_source_tier("https://www.byd.com/cn/detail617"), "A")
        self.assertEqual(classify_source_tier("https://www.marklines.com/cn/report/example"), "B")


if __name__ == "__main__":
    unittest.main()
