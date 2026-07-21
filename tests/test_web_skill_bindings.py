"""Web Skill 工具链的轻量回归检查。

前端页面目前以内嵌 JavaScript 的方式由 ``app.py`` 提供。此测试不启动浏览器，
但可阻止模板字符串被错误转义为 ``\\``` 后造成整段脚本无法解析的问题。
"""

from __future__ import annotations

import unittest

from app import HTML, build_final_answer_retry_config


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
        self.assertIn('market_monthly_report', HTML)
        self.assertIn('document.querySelectorAll(".skill-chip")', HTML)
        self.assertIn('$("questionInput").value = demo.question', HTML)

    def test_ppt_download_link_does_not_nest_a_template_expression(self) -> None:
        self.assertIn("const pptLinkAttribute", HTML)
        self.assertIn("${pptLinkAttribute}", HTML)
        self.assertNotIn('${data.pptx_url ? "download"', HTML)
