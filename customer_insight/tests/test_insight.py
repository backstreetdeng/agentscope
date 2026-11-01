"""洞察服务（InsightService）集成测试：满意度痛点 / 再购意愿 / 需求配置矩阵 / 竞品对比。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from customer_insight.insight_service import InsightService  # noqa: E402
from customer_insight.joint_service import JointInsightService  # noqa: E402


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


class TestRepurchaseIntent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = InsightService()

    def test_repurchase_by_model(self):
        result = self.service.repurchase_intent("purchase_model", "唐L")
        self.assertEqual(result["group_value"], "唐L")
        self.assertEqual(len(result["items"]), 4)
        labels = {x["label"] for x in result["items"]}
        self.assertIn("再购时间", labels)
        self.assertIn("再购技术类型", labels)
        self.assertIn("再购意向品牌", labels)
        self.assertIn("品牌忠诚（是否同品牌）", labels)
        for it in result["items"]:
            self.assertGreaterEqual(it["sample_count"], 0)
            self.assertIsInstance(it["dist"], list)

    def test_repurchase_invalid_field(self):
        with self.assertRaises(ValueError):
            self.service.repurchase_intent("bad_field", "x")


class TestDemandConfigMatrix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = InsightService()

    def test_matrix_by_model(self):
        result = self.service.demand_config_matrix("purchase_model", "唐L")
        self.assertEqual(result["group_value"], "唐L")
        self.assertEqual(len(result["items"]), 16)
        quadrants = {x["quadrant"] for x in result["items"]}
        self.assertTrue(quadrants.issubset({"优先改进", "核心优势", "潜在不满", "保持"}))
        for it in result["items"]:
            self.assertIn("attention_rate", it)
            self.assertIn("low_rate", it)
            self.assertIn("mean_score", it)
            self.assertGreaterEqual(it["attention_rate"], 0.0)
            self.assertLessEqual(it["attention_rate"], 1.0)

    def test_matrix_invalid_field(self):
        with self.assertRaises(ValueError):
            self.service.demand_config_matrix("bad_field", "x")


class TestCompetitorCompare(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = InsightService()

    def test_compare_attention(self):
        result = self.service.competitor_compare("attention", min_samples=20, top_models=8, top_dims=5)
        self.assertEqual(result["focus"], "attention")
        self.assertGreaterEqual(len(result["rows"]), 1)
        self.assertEqual(len(result["dims"]), 16)
        self.assertLessEqual(len(result["top_diff_dims"]), 5)
        for row in result["rows"]:
            self.assertEqual(len(row["values"]), 16)
            for v in row["values"].values():
                self.assertGreaterEqual(v, 0.0)
                self.assertLessEqual(v, 1.0)

    def test_compare_satisfaction(self):
        result = self.service.competitor_compare("satisfaction", min_samples=20, top_models=6)
        self.assertEqual(result["focus"], "satisfaction")
        self.assertGreaterEqual(len(result["rows"]), 1)


class TestCrossValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = JointInsightService()

    def test_cross_by_model(self):
        result = self.service.cross_validation("purchase_model", "唐L", top_k=4)
        self.assertEqual(result["group_value"], "唐L")
        self.assertEqual(len(result["attention"]), 16)
        self.assertGreaterEqual(len(result["satisfaction"]["items"]), 1)
        self.assertIn("evidence", result["qualitative"])

    def test_cross_quant_only_field(self):
        # age_band 在访谈库无过滤字段 → 定性为空，定量仍有效
        result = self.service.cross_validation("age_band", "36-40岁", top_k=4)
        self.assertEqual(result["qualitative"]["evidence"], [])
        self.assertGreater(len(result["attention"]), 0)

    def test_cross_invalid_field(self):
        with self.assertRaises(ValueError):
            self.service.cross_validation("bad_field", "x")


if __name__ == "__main__":
    unittest.main()
