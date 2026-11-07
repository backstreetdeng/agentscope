"""BCI-004 · 信息渠道呈现层归并测试。

不连数据库：直接校验归并表覆盖率，以及未知写法落「未归类」而非丢弃。
"""

from __future__ import annotations

import json
import unittest

from competitor_insight.server.channel_normalizer import (
    ALIAS_PATH,
    UNCATEGORIZED,
    load_alias_map,
    normalize_channel,
    normalize_channels,
)


class AliasTableTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = json.loads(ALIAS_PATH.read_text(encoding="utf-8"))

    def test_snapshot_covers_every_distinct_writing(self):
        entries = self.payload["entries"]
        raws = [entry["raw"] for entry in entries]
        self.assertEqual(len(raws), 64)
        self.assertEqual(len(set(raws)), 64)
        self.assertEqual(self.payload["coverage"]["mapped"], 64)
        self.assertEqual(self.payload["coverage"]["distinct_raw"], 64)
        for entry in entries:
            with self.subTest(raw=entry["raw"]):
                self.assertIn(entry["target"], self.payload["targets"] + [UNCATEGORIZED])
                self.assertGreaterEqual(entry["count"], 1)
                self.assertTrue(entry["basis"])

    def test_every_snapshot_writing_maps_to_declared_target(self):
        for entry in self.payload["entries"]:
            with self.subTest(raw=entry["raw"]):
                self.assertEqual(normalize_channel(entry["raw"]), entry["target"])

    def test_synonyms_merge_to_standard_channel(self):
        aliases = load_alias_map()
        self.assertEqual(aliases["哔哩哔哩"], "B站")
        self.assertEqual(aliases["朋友介绍"], "朋友推荐")
        self.assertEqual(aliases["线下门店"], "到店咨询")
        self.assertEqual(aliases["车展活动"], "车展")
        self.assertEqual(aliases["抖音精选"], "抖音")

    def test_unknown_writing_is_uncategorized_not_dropped(self):
        self.assertEqual(normalize_channel("从未见过的渠道"), UNCATEGORIZED)
        self.assertEqual(normalize_channel(""), UNCATEGORIZED)
        self.assertEqual(normalize_channel("   "), UNCATEGORIZED)

    def test_uncategorized_entries_are_listed_explicitly(self):
        uncategorized = [
            entry["raw"] for entry in self.payload["entries"]
            if entry["target"] == UNCATEGORIZED
        ]
        self.assertIn("未提及", uncategorized)
        self.assertIn("王者荣耀", uncategorized)
        self.assertNotIn("其他", [entry["raw"] for entry in self.payload["entries"]])

    def test_normalize_channels_dedupes_and_keeps_order(self):
        self.assertEqual(normalize_channels(["哔哩哔哩", "B站"]), ["B站"])
        self.assertEqual(normalize_channels(["抖音", "视频号", "哔哩哔哩"]), ["抖音", "其他", "B站"])
        self.assertEqual(normalize_channels(["未提及", "从未见过的渠道"]), [UNCATEGORIZED])


if __name__ == "__main__":
    unittest.main()
