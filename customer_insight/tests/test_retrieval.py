"""访谈证据检索服务的集成测试（依赖真实 DB + Ollama + Reranker）。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from customer_insight.retrieval_service import InterviewRetrievalService  # noqa: E402


class TestInterviewRetrievalService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = InterviewRetrievalService()

    def test_validate_filters_whitelist(self):
        clean, warnings = self.service._validate_filters(
            {"city": ["沈阳"], "question_ids": [4], "evil_col": "x"}
        )
        self.assertEqual(clean["city"], ["沈阳"])
        self.assertEqual(clean["question_ids"], [4])
        self.assertTrue(any("evil_col" in w for w in warnings))

    def test_search_no_filter(self):
        result = self.service.search("哪些用户提到后排空间？", top_k=6)
        self.assertIn("evidence", result)
        self.assertLessEqual(len(result["evidence"]), 6)
        for ev in result["evidence"]:
            self.assertTrue(ev["evidence_id"].startswith("E"))
            self.assertTrue(ev["quote"])

    def test_search_city_filter(self):
        result = self.service.search("用户为什么选择这款车", filters={"city": ["沈阳"]}, top_k=6)
        cities = {e["city"] for e in result["evidence"]}
        self.assertTrue(cities <= {"沈阳"})

    def test_search_empty_question(self):
        with self.assertRaises(ValueError):
            self.service.search("   ")


if __name__ == "__main__":
    unittest.main()
