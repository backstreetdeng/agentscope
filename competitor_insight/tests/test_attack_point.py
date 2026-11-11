"""BCI-006 · 「本品进攻点」提炼与现状核验单测（不联网、不连库）。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from competitor_insight.server import attack_point


DIRECTIONS = [
    {"direction": "车内气味", "competitor": "钛3", "count": 18, "denominator": 195,
     "ref": "reputation:negative:钛3:车内气味"},
    {"direction": "实际续航", "competitor": "零跑B10", "count": 11, "denominator": 103,
     "ref": "reputation:negative:零跑B10:实际续航"},
    {"direction": "路面滤震", "competitor": "钛3", "count": 10, "denominator": 195,
     "ref": "reputation:negative:钛3:路面滤震"},
]

CLEAN = "内饰气味控制、续航真实性、后排滤震舒适性"


def fake_search(query: str, max_results: int = 5):
    return [{
        "title": query,
        "url": "https://www.autohome.com.cn/koubei/1.html",
        "domain": "autohome.com.cn",
        "snippet": "车主反馈续航虚标，厂家已通过 OTA 优化。",
    }]


class AttackPointTest(unittest.TestCase):
    def test_extract_accepts_clean_output(self) -> None:
        result = attack_point.extract_attack(
            "iCAR 超级V23", "紧凑型纯电 SUV", DIRECTIONS,
            lambda system, message: CLEAN,
        )
        self.assertEqual(result["source"], "llm")
        self.assertEqual(result["texts"], CLEAN.split("、"))

    def test_extract_rewrites_sentence_form_once(self) -> None:
        replies = iter([
            "新车内饰气味偏重，提车初期乘坐不适、标称续航打折明显、细碎路面滤震不足",
            CLEAN,
        ])
        result = attack_point.extract_attack(
            "iCAR 超级V23", "紧凑型纯电 SUV", DIRECTIONS, lambda system, message: next(replies),
        )
        self.assertEqual(result["source"], "llm")
        self.assertEqual(result["texts"], CLEAN.split("、"))

    def test_extract_rejects_label_copy(self) -> None:
        result = attack_point.extract_attack(
            "iCAR 超级V23", "紧凑型纯电 SUV", DIRECTIONS,
            lambda system, message: "车内气味、实际续航、路面滤震",
        )
        self.assertEqual(result["source"], "fallback_labels")
        self.assertIn("复述", result["problem"])

    def test_extract_falls_back_when_numbers_persist(self) -> None:
        result = attack_point.extract_attack(
            "iCAR 超级V23", "紧凑型纯电 SUV", DIRECTIONS,
            lambda system, message: "车内异味 18 条、续航少 30 公里、悬架偏硬",
        )
        self.assertEqual(result["source"], "fallback_labels")
        self.assertEqual(result["texts"], [item["direction"] for item in DIRECTIONS])
        self.assertFalse(any(ch.isdigit() for ch in "、".join(result["texts"])))

    def test_verify_requires_verbatim_quote(self) -> None:
        rows = [[{"title": "t", "domain": "autohome.com.cn", "url": "https://a/1",
                  "snippet": "车主反馈续航虚标"}]]
        bad = lambda system, message: json.dumps(
            [{"index": 1, "verdict": "still_reported", "evidence": 1, "quote": "续航很好"}],
            ensure_ascii=False,
        )
        result = attack_point.verify_directions(DIRECTIONS[:1], rows, bad)
        self.assertEqual(result["items"][0]["text"], "未做现状核验")

    def test_verify_accepts_supported_quote(self) -> None:
        rows = [[{"title": "t", "domain": "autohome.com.cn", "url": "https://a/1",
                  "snippet": "车主反馈续航虚标"}]]
        good = lambda system, message: json.dumps(
            [{"index": 1, "verdict": "still_reported", "evidence": 1, "quote": "车主反馈续航虚标"}],
            ensure_ascii=False,
        )
        result = attack_point.verify_directions(DIRECTIONS[:1], rows, good)
        self.assertEqual(result["items"][0]["verdict"], "still_reported")
        self.assertEqual(result["items"][0]["domain"], "autohome.com.cn")

    def test_cache_key_changes_with_search_results(self) -> None:
        def llm(system: str, message: str) -> str:
            if "JSON 数组" in system:
                return "[]"
            return CLEAN

        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            first = attack_point.build_attack(
                "m", "iCAR 超级V23", "紧凑型纯电 SUV", list(DIRECTIONS),
                llm=llm, search=fake_search, cache_dir=cache,
            )
            second = attack_point.build_attack(
                "m", "iCAR 超级V23", "紧凑型纯电 SUV", list(DIRECTIONS),
                llm=llm, search=fake_search, cache_dir=cache,
            )
            self.assertEqual(first["source"], "llm")
            self.assertEqual(second["source"], "cache")

            changed = attack_point.build_attack(
                "m", "iCAR 超级V23", "紧凑型纯电 SUV", list(DIRECTIONS),
                llm=llm,
                search=lambda query, max_results=5: [{
                    "title": query, "url": "https://b/2", "domain": "b.cn",
                    "snippet": "另一条结果",
                }],
                cache_dir=Path(tmp) / "changed",
            )
            self.assertEqual(changed["source"], "llm")
            self.assertNotEqual(first["search_hash"], changed["search_hash"])

    def test_empty_directions_returns_empty(self) -> None:
        result = attack_point.build_attack("m", "iCAR 超级V23", "", [], llm=None)
        self.assertEqual(result["source"], "empty")


if __name__ == "__main__":
    unittest.main()
