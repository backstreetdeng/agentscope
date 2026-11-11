"""BCI-006 · 即时分析服务单测（不连数据库）。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from competitor_insight.server import name_rules, tile_summary
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

    def power_breakdown(self, model):
        return {"纯电": 41, "插混": 0, "增程": 0, "纯燃油": 0, "油电混动": 0, "未标注": 0}

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

    def loss_rows(self, model):
        """靶心=零跑B10：6 人对比过后买铂智3X、5 人买钛3、1 人买了靶心自己（应排除）。"""
        rows = []
        for index in range(6):
            row = {
                "purchase_model": "铂智3X",
                "c0": "零跑B10" if index == 0 else "",
                "c1": "领跑B10" if index else "",
                "c2": "",
                "r1_8": True,
            }
            if index == 0:
                row["r0_11"] = True
            rows.append(row)
        for _ in range(5):
            rows.append({"purchase_model": "钛3", "c0": "零跑B10", "c1": "", "c2": ""})
        rows.append({"purchase_model": "零跑B10", "c0": "零跑B10", "c1": "", "c2": ""})
        return rows

    def reputation(self, model):
        return {
            "points": [
                {"direction": "positive", "primary_label": "外观设计", "tertiary_label": "整体造型", "n": 6},
                {"direction": "positive", "primary_label": "续航与能耗", "tertiary_label": "实际续航", "n": 3},
                {"direction": "positive", "primary_label": "价格与购买价值", "tertiary_label": "整体性价比", "n": 3},
                {"direction": "positive", "primary_label": "动力与操控", "tertiary_label": "起步响应", "n": 3},
                {"direction": "positive", "primary_label": "空间与实用性", "tertiary_label": "第二排空间", "n": 3},
                {"direction": "positive", "primary_label": "外观设计", "tertiary_label": "前脸设计", "n": 3},
                {"direction": "negative", "primary_label": "续航与能耗", "tertiary_label": "实际续航", "n": 11},
                {"direction": "negative", "primary_label": "乘坐舒适性", "tertiary_label": "异常响声", "n": 4},
                {"direction": "negative", "primary_label": "乘坐舒适性", "tertiary_label": "路面滤震", "n": 3},
                {"direction": "negative", "primary_label": "内饰设计与做工", "tertiary_label": "软性材质覆盖", "n": 3},
                {"direction": "negative", "primary_label": "智能座舱", "tertiary_label": "屏幕显示", "n": 3},
                {"direction": "negative", "primary_label": "辅助驾驶与泊车", "tertiary_label": "车道保持", "n": 3},
            ],
            "rollup": [
                {"direction": "positive", "primary_label": "外观设计", "n": 9},
                {"direction": "positive", "primary_label": "续航与能耗", "n": 4},
                {"direction": "negative", "primary_label": "乘坐舒适性", "n": 8},
                {"direction": "negative", "primary_label": "续航与能耗", "n": 11},
            ],
            "batch": "20261111T093000",
            "batch_reviews": 96,
            "denominators": {"positive": 103, "negative": 103, "reviews": 103},
        }

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
        self.assertEqual(normalize_competitor("  海狮05EV ", aliases), "海狮05")
        self.assertEqual(normalize_competitor("海狮 05EV", aliases), "海狮05")
        self.assertEqual(normalize_competitor("深蓝S05", aliases), "深蓝S05")

    def test_normalize_strips_power_suffix_for_series_view(self):
        aliases = load_config()["competitor_aliases"]
        for raw, expect in (
            ("宋PLUS新能源", "宋PLUS"),
            ("海豹05 DM-i", "海豹05"),
            ("领克07 EM-P", "领克07"),
            ("领克08 EM-P", "领克08"),
            ("海狮05 EV", "海狮05"),
            ("元EV", "元"),
            ("宏光MINIEV", "宏光MINIEV"),
        ):
            self.assertEqual(normalize_competitor(raw, aliases), expect, raw)

    def test_normalize_power_form_five_categories(self):
        for raw, expect in (
            ("纯电", "纯电"),
            ("纯电动", "纯电"),
            ("纯电（BEV）", "纯电"),
            ("插混", "插混"),
            ("插电混动", "插混"),
            ("插电式混合动力", "插混"),
            ("PHEV", "插混"),
            ("增程", "增程"),
            ("增程式", "增程"),
            ("纯燃油", "纯燃油"),
            ("油电混动", "油电混动"),
            ("HEV", "油电混动"),
        ):
            self.assertEqual(name_rules.normalize_power_form(raw), expect, raw)
        for blank in ("", None, "混动", "油车", "不知道"):
            self.assertIsNone(name_rules.normalize_power_form(blank), blank)

    def test_config_aliases_merge_known_spellings(self):
        aliases = load_config()["competitor_aliases"]
        for raw, expect in (
            ("领跑B10", "零跑B10"),
            ("博智3X", "铂智3X"),
            ("海狮05EV", "海狮05"),
            ("比亚迪海狮05", "海狮05"),
            ("比亚迪海狮05 EV", "海狮05"),
            ("海狮05 DM-i", "海狮05"),
            ("iCAR V23", "iCAR 超级V23"),
            ("iCAR 超级V23", "iCAR 超级V23"),
            ("奇瑞iCAR V23", "iCAR 超级V23"),
            ("方程豹钛3", "钛3"),
            ("钛三", "钛3"),
            ("小鹏M03", "小鹏MONA M03"),
            ("小鹏 M03", "小鹏MONA M03"),
            ("小鹏MONA M03", "小鹏MONA M03"),
        ):
            self.assertEqual(normalize_competitor(raw, aliases), expect, raw)

    def test_competitor_aliases_resolve_in_one_hop(self):
        """别名必须一步落到终点，避免 A→B→A 的环把同一车系拆成两行。"""
        aliases = load_config()["competitor_aliases"]
        for raw, target in aliases.items():
            self.assertEqual(aliases.get(target, target), target, f"{raw} → {target} 不是终点")

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

    def test_reputation_l3_top5_uses_autohome_denominator(self):
        rep = next(
            item for item in self.data["tiles"]["satisfaction"]["metrics"]
            if item["key"] == "reputation"
        )
        self.assertEqual(rep["denominators"], {"positive": 103, "negative": 103})
        self.assertEqual(rep["batch"], "20261111T093000")
        self.assertEqual(rep["model"], "零跑B10")
        self.assertEqual(
            [item["label"] for item in rep["positive"]],
            ["整体造型", "实际续航", "整体性价比", "起步响应", "第二排空间"],
        )
        self.assertEqual(rep["positive"][0]["l1"], "外观")
        self.assertEqual(rep["positive"][0]["ratio"], 5.8)
        self.assertEqual(rep["negative"][0]["label"], "实际续航")
        self.assertEqual(rep["negative"][0]["ratio"], 10.7)
        self.assertEqual(len(rep["negative"]), 5)
        self.assertEqual(rep["boundary"]["source"], "汽车之家（满意 / 不满意分栏）")
        self.assertEqual(rep["sample_flag"], "ok")
        self.assertEqual([item["label"] for item in rep["rollup"]["positive"]], ["外观", "续航与能耗"])
        self.assertNotIn("n", rep)

    def test_unavailable_metrics_are_empty_with_reason(self):
        attention = self.data["tiles"]["attention"]["metrics"]
        first = next(item for item in attention if item["key"] == "first_ranking")
        self.assertEqual(first["status"], "empty")
        self.assertTrue(first["reason"])

    def test_winloss_titles_follow_prototype(self):
        winloss = self.data["tiles"]["winloss"]
        self.assertEqual(winloss["title"], "战胜战败原因洞察")
        self.assertEqual(self.data["tiles"]["satisfaction"]["title"], "产品满意度评价")

    def test_win_reasons_keep_sixteen_dimensions(self):
        metrics = {item["key"]: item for item in self.data["tiles"]["winloss"]["metrics"]}
        self.assertEqual(metrics["q3_23"]["label"], "选择当前车辆的原因（Q3_23）")
        self.assertEqual(len(metrics["q3_23"]["items"]), 16)
        self.assertNotIn("q3_24_1", metrics)
        self.assertNotIn("opponent_why_win", metrics)

    def test_loss_split_groups_by_actual_purchase_without_threshold(self):
        loss = next(
            item for item in self.data["tiles"]["winloss"]["metrics"]
            if item["key"] == "loss_split"
        )
        self.assertEqual(loss["kind"], "loss_split")
        self.assertEqual(loss["target"], "零跑B10")
        self.assertEqual(loss["n"], 11)
        self.assertIn("Q3_24_1", loss["basis"])
        self.assertEqual([item["label"] for item in loss["items"]], ["铂智3X", "钛3"])
        self.assertEqual([item["count"] for item in loss["items"]], [6, 5])
        self.assertEqual(sum(item["count"] for item in loss["items"]), loss["n"])
        self.assertNotIn("其他", [item["label"] for item in loss["items"]])
        self.assertNotIn("零跑B10", [item["label"] for item in loss["items"]])
        self.assertEqual(loss["items"][0]["ratio"], 54.5)
        self.assertEqual(loss["items"][0]["reasons"][0]["label"], "质量")
        self.assertEqual(loss["items"][0]["reasons"][0]["count"], 5)
        self.assertEqual(loss["items"][1]["reasons"], [])

    def test_loss_split_row_below_five_has_no_ratio(self):
        fake = FakeReader()
        model = {"key": "toyota-bz3x", "label": "铂智3X", "quant_models": ["铂智3X"]}
        rows = [
            {"purchase_model": "零跑B10", "c0": "铂智3X", "c1": "", "c2": ""},
            {"purchase_model": "零跑B10", "c0": "铂智3X", "c1": "", "c2": ""},
        ]
        fake.loss_rows = lambda _model: rows
        metric = AnalysisService()._loss_split(fake, model, load_config())
        self.assertEqual(metric["n"], 2)
        self.assertEqual(metric["items"][0]["count"], 2)
        self.assertIsNone(metric["items"][0]["ratio"])
        self.assertIn("只给人数", metric["items"][0]["ratio_hidden_reason"])

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


class TileSummaryTest(unittest.TestCase):
    """磁贴级 AI 结论：三块各自的提示词、40–70 字、失败报错、按提示词+数据版本缓存。"""

    def setUp(self):
        self.data = service().analyze("leapmotor-b10")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cache_dir = Path(self.tmp.name)

    def _summarize(self, tile_key, llm=None):
        return tile_summary.summarize_tile(
            tile_key,
            self.data["tiles"][tile_key],
            self.data["model"]["label"],
            self.data["model"]["key"],
            llm=llm,
            cache_dir=self.cache_dir,
        )

    def test_each_tile_uses_its_own_prompt_and_only_its_own_numbers(self):
        calls = []

        def fake_llm(system_prompt, message):
            calls.append((system_prompt, message))
            if "下一步重点防御" in system_prompt:
                return "智驾认知是胜出核心，下一步重点防御零跑B10的价格攻势。"
            if "入场券" in system_prompt:
                return "外观是入场券，智驾是必备项，续航才是竞争决胜点。"
            return "以技术理性派为主，属于理性消费的家用代步用户。"

        results = {key: self._summarize(key, fake_llm) for key in ("profile", "attention", "winloss")}
        self.assertEqual(len(calls), 3)
        for payload in results.values():
            self.assertEqual(payload["source"], "llm")
            self.assertTrue(payload["summary"].endswith("。"))
            self.assertLessEqual(len(payload["summary"]), 70)
            self.assertIn("【本块数字】", payload["prompt"])
        by_tile = dict(zip(("profile", "attention", "winloss"), calls))
        prompts = {key: value[0] for key, value in by_tile.items()}
        messages = {key: value[1] for key, value in by_tile.items()}
        self.assertIn("技术理性派", prompts["profile"])
        self.assertIn("入场券", prompts["attention"])
        self.assertIn("下一步重点防御", prompts["winloss"])
        self.assertNotIn("Q3_23", messages["profile"])
        self.assertNotIn("Q5_2", messages["attention"])
        self.assertIn("战败侧·对比过", messages["winloss"])

    def test_winloss_prompt_carries_interview_clues_with_people_count(self):
        messages = []

        def fake_llm(_system_prompt, message):
            messages.append(message)
            return "智驾是胜出核心，下一步重点防御零跑B10的价格攻势。"

        self._summarize("winloss", fake_llm)
        message = messages[0]
        self.assertIn("深访原话（Q29 选择本车原因，3 人，来源：深访", message)
        self.assertIn("深访原话（Q27/Q28 放弃对比车型原因，2 人，来源：深访", message)
        self.assertIn("外观好看，空间大", message)

    def test_summary_is_cached_by_prompt_and_data_version(self):
        calls = []

        def fake_llm(_system_prompt, message):
            calls.append(message)
            return "外观是入场券，智驾是必备项。"

        first = self._summarize("attention", fake_llm)
        second = self._summarize("attention", fake_llm)
        self.assertEqual(first["source"], "llm")
        self.assertEqual(second["source"], "cache")
        self.assertEqual(first["summary"], second["summary"])
        self.assertEqual(len(calls), 1)

        facts = tile_summary.build_facts("attention", self.data["tiles"]["attention"], "零跑B10")
        self.assertNotEqual(
            tile_summary.facts_digest(facts, "旧提示词"),
            tile_summary.facts_digest(facts, "新提示词"),
        )

    def test_llm_failure_reports_error_instead_of_template_sentence(self):
        def broken(_system_prompt, _message):
            raise RuntimeError("model down")

        payload = self._summarize("winloss", broken)
        self.assertEqual(payload["source"], "error")
        self.assertFalse(payload["summary"])
        self.assertIn("model down", payload["error"])

    def test_llm_output_is_normalized(self):
        payload = self._summarize(
            "attention",
            lambda _system_prompt, _message: "AI 结论：外观是入场券，智驾是必备项，续航才是竞争决胜点。",
        )
        self.assertEqual(payload["source"], "llm")
        self.assertFalse(payload["summary"].startswith("AI"))
        self.assertLessEqual(len(payload["summary"]), 70)
        self.assertTrue(payload["summary"].endswith("。"))

    def test_overlong_output_triggers_one_rewrite(self):
        long_text = "外观是入场券，智驾是必备项，" + "续航与底盘操控才是竞争决胜点，" * 4
        replies = [long_text, "外观是入场券，智驾是必备项，续航与操控才是竞争决胜点。"]
        calls = []

        def fake_llm(_system_prompt, message):
            calls.append(message)
            return replies[len(calls) - 1]

        payload = self._summarize("attention", fake_llm)
        self.assertEqual(payload["source"], "llm")
        self.assertEqual(len(calls), 2)
        self.assertIn("超过 70 字上限", calls[1])

    def test_bad_format_triggers_one_rewrite(self):
        replies = [
            "男性21/30（70%）最突出，36-40岁次之。",
            "以技术理性派为主，处在事业上升期，属于理性消费型用户。",
        ]
        calls = []

        def fake_llm(_system_prompt, message):
            calls.append(message)
            return replies[len(calls) - 1]

        payload = self._summarize("profile", fake_llm)
        self.assertEqual(payload["source"], "llm")
        self.assertEqual(len(calls), 2)
        self.assertIn("上一次输出不合格", calls[1])
        self.assertIn("技术理性派", payload["summary"])

    def test_unfixed_bad_format_reports_error(self):
        payload = self._summarize(
            "winloss", lambda _system_prompt, _message: "钛3胜出8人，外观最强。"
        )
        self.assertEqual(payload["source"], "error")
        self.assertIn("格式", payload["error"])
        self.assertFalse(payload["summary"])

    def test_model_output_spacing_is_repaired_to_library_names(self):
        tile = {
            "metrics": [
                {
                    "key": "loss_split",
                    "target": "铂智3X",
                    "n": 17,
                    "items": [
                        {
                            "label": "海狮05 EV",
                            "count": 3,
                            "n": 17,
                            "ratio": 17.6,
                            "reasons": [{"label": "外观", "count": 2, "n": 3, "ratio": 66.7}],
                        }
                    ],
                }
            ]
        }
        payload = tile_summary.summarize_tile(
            "winloss",
            tile,
            "铂智3X",
            "toyota-bz3x",
            llm=lambda _system_prompt, _message: "海狮05EV是胜出核心，下一步重点防御其外观。",
            cache_dir=self.cache_dir,
        )
        self.assertIn("海狮05 EV", payload["summary"])

    def test_summaries_cover_three_tiles_and_report_missing_llm(self):
        data = AnalysisService(reader_factory=FakeReader, config_path=CONFIG_PATH).summaries(
            "leapmotor-b10"
        )
        self.assertEqual(set(data["tiles"]), {"profile", "attention", "winloss"})
        for payload in data["tiles"].values():
            self.assertEqual(payload["source"], "error")
            self.assertIn("未注入模型通道", payload["error"])
            self.assertFalse(payload["summary"])


if __name__ == "__main__":
    unittest.main()
