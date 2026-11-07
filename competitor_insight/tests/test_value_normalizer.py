"""BCI-004 · D7c 枚举取值归一测试。

覆盖：标准值直通、口语/修饰写法归一、多值互斥、无数据表述、真正无法判断落 invalid_enum。
不连数据库。
"""

from __future__ import annotations

import unittest

from competitor_insight.server.evidence_gate import EvidenceGateError
from competitor_insight.server.value_normalizer import (
    resolve_enum,
    resolve_enum_or_raise,
)

OPTIONS = ["首购", "增购", "换购"]


class ResolveEnumTest(unittest.TestCase):
    def test_standard_value_passes_through(self):
        for raw in ("首购", "增购", "换购", "增购。", " 换购 "):
            with self.subTest(raw=raw):
                resolved = resolve_enum(raw, OPTIONS)
                self.assertEqual(resolved.status, "exact")
                self.assertIn(resolved.value, OPTIONS)
                self.assertEqual(resolved.as_source_ref(), {})

    def test_modifier_wording_is_normalized(self):
        cases = {
            "实际增购。": "增购",
            "确有增购": "增购",
            "是增购": "增购",
            "属于换购。": "换购",
            "增购（第二辆）": "增购",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                resolved = resolve_enum(raw, OPTIONS)
                self.assertEqual(resolved.status, "normalized")
                self.assertEqual(resolved.value, expected)
                self.assertEqual(resolved.as_source_ref()["normalized_from"], raw)

    def test_same_option_repeated_is_still_single_value(self):
        resolved = resolve_enum("增购；增购。", OPTIONS)
        self.assertEqual(resolved.status, "normalized")
        self.assertEqual(resolved.value, "增购")

    def test_multiple_distinct_options_are_ambiguous(self):
        resolved = resolve_enum("换购；增购。", OPTIONS)
        self.assertEqual(resolved.status, "ambiguous")
        self.assertIsNone(resolved.value)
        self.assertEqual(resolved.candidates, ["换购", "增购"])
        self.assertIn("多个互斥取值", resolved.reason)

    def test_no_value_markers(self):
        for raw in ("", "  ", "未提及。", "不适用", "不适用。"):
            with self.subTest(raw=raw):
                resolved = resolve_enum(raw, OPTIONS)
                self.assertEqual(resolved.status, "no_value")
                self.assertIsNone(resolved.value)

    def test_unrecognizable_value_is_unknown_not_guessed(self):
        for raw in ("四个字乱码", "abc", "不是增购", "介于增购和换购之间"):
            with self.subTest(raw=raw):
                resolved = resolve_enum(raw, OPTIONS)
                self.assertEqual(resolved.status, "unknown")
                self.assertIsNone(resolved.value)

    def test_mixed_parts_with_unrecognized_fragment_is_unknown(self):
        resolved = resolve_enum("增购；随便写的", OPTIONS)
        self.assertEqual(resolved.status, "unknown")
        self.assertIn("随便写的", resolved.reason)

    def test_unknown_raises_invalid_enum(self):
        with self.assertRaises(EvidenceGateError) as ctx:
            resolve_enum_or_raise("purchase_attribute", "四个字乱码", OPTIONS)
        self.assertEqual(ctx.exception.code, "invalid_enum")

    def test_ambiguous_and_no_value_do_not_raise(self):
        self.assertEqual(
            resolve_enum_or_raise("purchase_attribute", "换购；增购", OPTIONS).status,
            "ambiguous",
        )
        self.assertEqual(
            resolve_enum_or_raise("purchase_attribute", "未提及", OPTIONS).status,
            "no_value",
        )


if __name__ == "__main__":
    unittest.main()
