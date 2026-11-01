"""战胜战败检索服务（battle_search）集成测试。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from customer_insight.retrieval_service import InterviewRetrievalService  # noqa: E402


class TestBattleSearch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = InterviewRetrievalService()

    def test_battle_search_valid(self):
        result = self.service.battle_search("唐L", top_k=6)
        self.assertEqual(result["battle"]["target_model"], "唐L")
        self.assertGreaterEqual(result["battle"]["buyer_count"], 1)
        groups = {d["content_group"] for d in result["battle"]["dimensions"]}
        self.assertIn("对比车型", groups)
        self.assertIn("选购原因", groups)
        self.assertLessEqual(len(result["evidence"]), 6)

    def test_battle_search_no_result(self):
        result = self.service.battle_search("不存在的车型XYZ")
        self.assertEqual(result["battle"]["buyer_count"], 0)
        self.assertEqual(result["evidence"], [])

    def test_battle_search_empty_model(self):
        with self.assertRaises(ValueError):
            self.service.battle_search("   ")


if __name__ == "__main__":
    unittest.main()
