"""BCI-006 · 即时分析服务单测（不连数据库）。"""

from __future__ import annotations

import unittest

from competitor_insight.server.analysis_service import (
    AnalysisService,
    CONFIG_PATH,
    display_purchase_type,
    load_config,
    normalize_competitor,
    parse_recommendation,
    ratio_payload,
    sample_flag,
    tag_dimensions,
)


class FakeReader:
    """按方法名返回固定结构，验证口径拼装而不是 SQL。"""

    def source_counts(self, model):
        return {"quant": 41, "interview": 4, "reputation": 392, "miit": 6}

    def quant_answered_full(self, model):
        return {"n": 41, "Q3_13": 41, "Q3_23": 41, "Q3_24_1": 41, "Q5_2": 41, "Q5_1": 41, "Q5_5": 41}

    def distribution(self, model, field, kind):
        if field == "purchase_type":
            return [
                {"label": "首购", "count": 20},
                {"label": "换购（卖掉旧车）", "count": 12},
                {"label": "增购", "count": 9},
            ]
        return [{"label": "样例A", "count": 21}, {"label": "样例B", "count": 20}]

    def budget_values(self, model):
        return [10, 12, 15, 20, 30]

    def interview_quotes(self, model, question_id):
        return [
            {"interview_id": f"R00{i}", "respondent_code": f"R00{i}", "city": "杭州",
             "purchase_type": "首购", "question_text": "车意味着什么", "answer_text": f"原话{i}"}
            for i in range(1, 5)
        ]

    def multi_counts(self, model, prefix):
        row = {"answered": 41}
        for index in range(1, 17):
            row[f"c{index}"] = 12 if index <= 3 else 1
        return row

    def score_stats(self, model):
        row = {}
        for index in range(1, 17):
            row[f"a{index}"] = 41
            row[f"m{index}"] = 9 - index / 10
            row[f"l{index}"] = index
        return row

    def overall_score(self, model):
        return {"mean": 8.52, "answered": 41}

    def recommendation_values(self, model):
        return ["9十分推荐", "8比较推荐", "7比较推荐", "5说不好"]

    def competitor_texts(self, model):
        return [
            {"value": "比亚迪宋PlUS", "count": 3},
            {"value": "比亚迪宋PLUS", "count": 2},
            {"value": "海狮05EV", "count": 1},
        ]

    def reputation(self, model):
        return [
            {"direction": "positive", "primary_label": "配置智能", "mention_count": 120},
            {"direction": "negative", "primary_label": "油耗能耗", "mention_count": 39},
        ]

    def interview_reason_answers(self, model, question_ids):
        if 29 in question_ids:
            return [
                {"interview_id": "R001", "respondent_code": "R001", "question_id": 29,
                 "question_text": "为什么选", "answer_text": "外观好看，空间大"},
                {"interview_id": "R002", "respondent_code": "R002", "question_id": 29,
                 "question_text": "为什么选", "answer_text": "服务不错"},
                {"interview_id": "R003", "respondent_code": "R003", "question_id": 29,
                 "question_text": "为什么选", "answer_text": "就是喜欢"},
            ]
        return [
            {"interview_id": "R001", "respondent_code": "R001", "question_id": 27,
             "question_text": "为什么放弃", "answer_text": "内饰太差"},
            {"interview_id": "R002", "respondent_code": "R002", "question_id": 28,
             "question_text": "为什么放弃", "answer_text": "价格贵"},
        ]

    def close(self):
        pass


def service() -> AnalysisService:
    return AnalysisService(reader_factory=FakeReader, config_path=CONFIG_PATH)


class ConfigTest(unittest.TestCase):
    def test_config_has_five_models_and_unique_keys(self):
        config = load_config()
        self.assertEqual(len(config["models"]), 5)
        keys = [item["key"] for item in config["models"]]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(config["default_model"], "leapmotor-b10")

    def test_icar_aliases_cover_all_four_sources(self):
        config = load_config()
        icar = next(item for item in config["models"] if item["key"] == "chery-icar-v23")
        for field in ("quant_models", "interview_models", "reputation_models", "miit_models"):
            self.assertTrue(icar[field], field)
        self.assertIn("iCAR 超级V23", icar["reputation_models"])
        self.assertIn("奇瑞iCAR V23", icar["quant_models"])


class RatioTest(unittest.TestCase):
    def test_sample_flag_thresholds(self):
        self.assertEqual(sample_flag(9), "insufficient")
        self.assertEqual(sample_flag(10), "small")
        self.assertEqual(sample_flag(29), "small")
        self.assertEqual(sample_flag(30), "ok")

    def test_ratio_hidden_below_ten_sample(self):
        payload = ratio_payload(3, 9)
        self.assertIsNone(payload["ratio"])
        self.assertIn("低于 10 人", payload["ratio_hidden_reason"])

    def test_ratio_hidden_when_answered_below_ten(self):
        payload = ratio_payload(2, 41, 6)
        self.assertIsNone(payload["ratio"])
        self.assertIn("仅 6 人作答", payload["ratio_hidden_reason"])

    def test_ratio_kept_with_both_denominators(self):
        payload = ratio_payload(12, 41, 41)
        self.assertEqual(payload["ratio"], 29.3)
        self.assertEqual(payload["count"], 12)
        self.assertEqual(payload["n"], 41)
        self.assertEqual(payload["answered"], 41)


class NormalizeTest(unittest.TestCase):
    def test_parse_recommendation(self):
        self.assertEqual(parse_recommendation("9十分推荐"), (9, "十分推荐"))
        self.assertEqual(parse_recommendation(" 5 说不好 "), (5, "说不好"))
        self.assertIsNone(parse_recommendation("十分推荐"))
        self.assertIsNone(parse_recommendation("11超出范围"))

    def test_normalize_competitor_aliases(self):
        aliases = {"比亚迪宋PlUS": "比亚迪宋PLUS", "海狮05EV": "海狮05 EV"}
        self.assertEqual(normalize_competitor("比亚迪宋PlUS", aliases), "比亚迪宋PLUS")
        self.assertEqual(normalize_competitor("  海狮05EV ", aliases), "海狮05 EV")
        self.assertEqual(normalize_competitor("深蓝S05", aliases), "深蓝S05")

    def test_purchase_type_short_labels(self):
        self.assertEqual(display_purchase_type("首购"), "首购")
        self.assertEqual(display_purchase_type("换购（卖掉旧车换新车）"), "换购（卖掉旧车）")
        self.assertEqual(display_purchase_type("换购（报废旧车）"), "换购（报废旧车）")
        self.assertEqual(display_purchase_type("增购"), "增购")

    def test_tag_dimensions_returns_same_labels_and_unmatched(self):
        self.assertIn("外观", tag_dimensions("外观好看，空间也大"))
        self.assertIn("空间", tag_dimensions("外观好看，空间也大"))
        self.assertEqual(tag_dimensions("就是喜欢"), [])


class AnalyzeTest(unittest.TestCase):
    def setUp(self):
        self.data = service().analyze("leapmotor-b10")

    def test_four_tiles_present(self):
        self.assertEqual(set(self.data["tiles"]), {"profile", "attention", "winloss", "satisfaction"})

    def test_every_ratio_has_both_denominators(self):
        for tile in self.data["tiles"].values():
            for metric in tile["metrics"]:
                for item in metric.get("items", []) + metric.get("top", []):
                    if "count" not in item:
                        continue
                    self.assertIn("n", item)
                    self.assertIn("ratio", item)
                    if item["ratio"] is not None:
                        self.assertGreaterEqual(item["n"], 10)

    def test_unavailable_metrics_are_empty_with_reason(self):
        attention = self.data["tiles"]["attention"]["metrics"]
        first = next(item for item in attention if item["key"] == "first_ranking")
        self.assertEqual(first["status"], "empty")
        self.assertTrue(first["reason"])
        winloss = self.data["tiles"]["winloss"]["metrics"]
        opponent = next(item for item in winloss if item["key"] == "opponent_why_win")
        self.assertEqual(opponent["status"], "empty")
        self.assertTrue(opponent["reason"])

    def test_winloss_uses_confirmed_caliber_and_same_dimensions(self):
        winloss = self.data["tiles"]["winloss"]
        self.assertEqual(winloss["title"], "选择与放弃")
        metrics = {item["key"]: item for item in winloss["metrics"]}
        self.assertEqual(metrics["q3_23"]["label"], "选择当前车辆的原因（Q3_23）")
        self.assertEqual(metrics["q3_24_1"]["label"], "放弃核心对比车型的原因（Q3_24_1）")
        self.assertEqual(len(metrics["q3_23"]["items"]), 16)
        self.assertEqual(len(metrics["q3_24_1"]["items"]), 16)
        self.assertEqual(
            [item["label"] for item in metrics["q3_23"]["items"]],
            [item["label"] for item in metrics["q3_24_1"]["items"]],
        )

    def test_qualitative_layer_counts_people_and_lists_unmatched(self):
        winloss = self.data["tiles"]["winloss"]
        win_quotes = next(item for item in winloss["metrics"] if item["key"] == "win_quotes")
        self.assertEqual(win_quotes["people"], 3)
        self.assertEqual(win_quotes["answered"], 3)
        self.assertEqual(len(win_quotes["unmatched"]), 1)
        self.assertIn("外观", [tag for item in win_quotes["items"] for tag in item["dimensions"]])
        abandon_quotes = next(item for item in winloss["metrics"] if item["key"] == "abandon_quotes")
        self.assertEqual(abandon_quotes["question_ids"], ["Q27", "Q28"])
        self.assertEqual(abandon_quotes["people"], 2)

    def test_recommendation_is_computed_from_q5_5_text(self):
        rec = next(
            item for item in self.data["tiles"]["satisfaction"]["metrics"]
            if item["key"] == "recommendation"
        )
        self.assertEqual(rec["status"], "ok")
        self.assertEqual(rec["answered"], 4)
        self.assertEqual(rec["mean"], 7.25)

    def test_summary_contains_numbers_and_sample_size(self):
        summary = self.data["summary"]
        self.assertTrue(any("定量样本 41" in line for line in summary))
        self.assertTrue(any("41" in line for line in summary[1:]))

    def test_models_endpoint_returns_sources(self):
        data = service().models()
        self.assertEqual(len(data["models"]), 5)
        for item in data["models"]:
            self.assertEqual(item["sources"], {"quant": 41, "interview": 4, "reputation": 392, "miit": 6})
            self.assertFalse(item["missing_sources"])


if __name__ == "__main__":
    unittest.main()
