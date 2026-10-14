"""Offline behavior regression for the workbench's explicit public-draft mode."""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import shutil
import subprocess
import unittest


PROJECT = Path(__file__).resolve().parents[1]


class _Inputs(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.inputs: dict[str, dict[str, str | None]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "input" and attributes.get("id"):
            self.inputs[str(attributes["id"])] = attributes


class MacroPublicDraftUiTest(unittest.TestCase):
    def test_new_analysis_links_are_explicitly_fresh(self) -> None:
        html = (PROJECT / "home.html").read_text(encoding="utf-8")
        self.assertEqual(html.count("aria-label='在新窗口新建一次市场分析'"), 2)
        self.assertEqual(html.count("href='/strategy-analysis.html?new=1'"), 2)

    def test_draft_requires_explicit_unchecked_macro_option(self) -> None:
        html = (PROJECT / "strategy-analysis.html").read_text(encoding="utf-8")
        parser = _Inputs()
        parser.feed(html)
        self.assertEqual(parser.inputs["macroPublicDraft"]["type"], "checkbox")
        self.assertNotIn("checked", parser.inputs["macroPublicDraft"])
        self.assertIn("不属于完整正式报告", html)
        self.assertIn("未勾选时按正式报告完整性要求执行", html)

    def test_actual_workbench_requests_gates_and_resumption_offline(self) -> None:
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is required for the JavaScript behavior regression.")
        result = subprocess.run(
            [node, str(PROJECT / "tests/test_macro_public_draft_ui.js")],
            cwd=PROJECT, capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("archive assertions passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
