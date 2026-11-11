"""BCI-007 · 报告 HTML 渲染单测：转义、自包含、结构完整。"""

from __future__ import annotations

import re
import unittest

from competitor_insight.server.report_render_html import RENDERER_VERSION, render_report_html


def content_with(quote: str = "正常原话") -> dict:
    return {
        "title": "2 款车型竞品用户洞察报告",
        "subtitle": "竞品侧用户洞察",
        "scope_note": "本期仅竞品侧",
        "generated_at": "2026-11-11T15:00:00+08:00",
        "outline_version": "report-outline/1.0.0",
        "data_fingerprint": "a" * 64,
        "models": [
            {
                "key": "a",
                "label": "测试车A",
                "sources": {"quant": 41},
                "archive": {"archived": 2, "interview_total": 4},
                "missing_sources": [],
            }
        ],
        "pages": [
            {
                "page": "P01",
                "title": "用户画像",
                "subtitle": "人群结构",
                "blocks": [
                    {
                        "id": "P01.BASIC",
                        "type": "table",
                        "title": "基本特征（定量）",
                        "source": "analysis.profile",
                        "availability": "ok",
                        "kind": "per_model",
                        "models": [
                            {
                                "key": "a",
                                "label": "测试车A",
                                "n": 41,
                                "columns": ["维度", "取值"],
                                "rows": [["年龄段", "26-30岁 12/41（29.3%）"]],
                                "status": "ok",
                                "note": "",
                            }
                        ],
                    },
                    {
                        "id": "P01.LIFESTYLE",
                        "type": "quotes",
                        "title": "生活状态（深访）",
                        "source": "archive.lifestyle",
                        "availability": "ok",
                        "models": [
                            {
                                "key": "a",
                                "label": "测试车A",
                                "people": 2,
                                "archived": 2,
                                "items": [{"code": "R001", "text": quote, "suspect": False}],
                                "status": "ok",
                                "note": "",
                            }
                        ],
                    },
                ],
            },
            {
                "page": "P08",
                "title": "信息渠道",
                "subtitle": "深访口径",
                "blocks": [
                    {
                        "id": "P08.CHANNELS",
                        "type": "table",
                        "title": "渠道提及人数",
                        "source": "archive.info_channels",
                        "availability": "missing",
                        "kind": "matrix",
                        "columns": ["项目", "测试车A（n=0）"],
                        "rows": [],
                        "note": "无可用档案",
                    }
                ],
            },
        ],
        "appendices": [
            {
                "page": "APPENDIX",
                "title": "附录A 数据边界",
                "subtitle": "",
                "blocks": [
                    {
                        "id": "A.BOUNDARY",
                        "type": "table",
                        "title": "样本覆盖",
                        "source": "derived.boundary",
                        "availability": "ok",
                        "kind": "matrix",
                        "columns": ["车型", "定量样本"],
                        "rows": [["测试车A", "41"]],
                        "note": "",
                    }
                ],
            }
        ],
        "excluded_pages": [{"page": "P02", "title": "用户来源", "reason": "单一车型专题"}],
        "gaps": [{"page": "P08", "block": "P08.CHANNELS", "title": "渠道", "reason": "无可用档案"}],
        "sources": [{"name": "analysis.profile", "description": "定量问卷 · 用户画像"}],
    }


class RenderHtmlTest(unittest.TestCase):
    def test_escapes_dynamic_text(self):
        html = render_report_html(content_with('<script>alert("x")</script>'))
        self.assertNotIn("<script", html.lower())
        self.assertIn("&lt;script&gt;", html)

    def test_self_contained(self):
        html = render_report_html(content_with())
        self.assertNotRegex(html, r"https?://")
        self.assertNotIn("<link", html.lower())
        self.assertNotIn("<img", html.lower())

    def test_renders_all_pages_and_renderer_version(self):
        html = render_report_html(content_with())
        self.assertIn("P01 · 用户画像", html)
        self.assertIn("P08 · 信息渠道", html)
        self.assertIn("附录 · 数据边界", html)
        self.assertIn(RENDERER_VERSION, html)
        self.assertIn("未纳入的页面", html)

    def test_missing_block_shows_reason(self):
        html = render_report_html(content_with())
        self.assertIn("缺数据", html)
        self.assertIn("无可用档案", html)

    def test_no_inline_event_handlers(self):
        html = render_report_html(content_with())
        self.assertIsNone(re.search(r"\son\w+=", html, re.IGNORECASE))


if __name__ == "__main__":
    unittest.main()
