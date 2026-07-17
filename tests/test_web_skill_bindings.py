"""Web Skill 工具链的轻量回归检查。

前端页面目前以内嵌 JavaScript 的方式由 ``app.py`` 提供。此测试不启动浏览器，
但可阻止模板字符串被错误转义为 ``\\``` 后造成整段脚本无法解析的问题。
"""

from __future__ import annotations

import unittest

from app import HTML


class WebSkillBindingsTest(unittest.TestCase):
    def test_skill_click_script_has_no_escaped_template_delimiter(self) -> None:
        self.assertNotIn(r"\`", HTML)
        self.assertNotIn(r"\${", HTML)

    def test_monthly_skill_mapping_and_click_binding_exist(self) -> None:
        self.assertIn('market_monthly_report', HTML)
        self.assertIn('document.querySelectorAll(".skill-chip")', HTML)
        self.assertIn('$("questionInput").value = demo.question', HTML)
