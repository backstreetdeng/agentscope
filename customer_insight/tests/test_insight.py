"""洞察服务（InsightService）集成测试：满意度痛点 / 再购意愿 / 需求配置矩阵 / 竞品对比。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from customer_insight.insight_service import InsightService  # noqa: E402


class TestSatisfactionPainpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = InsightService()

    def test_painpoints_by_model(self):
        result = self.service.satisfaction_painpoints("purchase_model", "唐L", top=10)
        self.assertEqual(result["group_field"], "purchase_model")
        self.assertEqual(result["group_value"], "唐L")
        self.assertGreaterEqual(len(result["items"]), 1)
        rates = [x["low_rate"] for x in result["items"]]
        self.assertEqual(rates, sorted(rates, reverse=True))
        for it in result["items"]:
            self.assertIn("mean_score", it)
            self.assertGreaterEqual(it["low_rate"], 0.0)
            self.assertLessEqual(it["low_rate"], 1.0)
            self.assertGreater(it["total"], 0)

    def test_painpoints_invalid_field(self):
        with self.assertRaises(ValueError):
            self.service.satisfaction_painpoints("bad_field", "x")


if __name__ == "__main__":
    unittest.main()
