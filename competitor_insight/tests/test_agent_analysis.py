"""智能化分析：工具层与固定骨架的离线单测（不连库、不调模型）。"""

from __future__ import annotations

import json
import unittest

from competitor_insight.server.agent_analysis import AgentAnalysisError, AgentAnalysisService
from competitor_insight.server.agent_tools import Toolbox

TARGET_KEY = "byd-sealion-05-ev"
TARGET_LABEL = "海狮05"
POOL_LABEL = "铂智3X"


class FakeReader:
    """只实现工具层用到的方法；口径与 PostgresReader 返回形状一致。"""

    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True

    @staticmethod
    def _size(model) -> int:
        return 39 if model["label"] == POOL_LABEL else 31

    def source_counts(self, model):
        size = self._size(model)
        return {"quant": size, "interview": 3, "reputation": 400, "miit": 1}

    def quant_answered_full(self, model):
        size = self._size(model)
        return {
            "n": size,
            "Q3_13": size,
            "Q3_23": size - 2,
            "Q3_24_1": size - 3,
            "Q5_2": size - 4,
            "Q5_1": size - 5,
            "Q5_5": size - 6,
        }

    def distribution(self, model, field, kind):
        base = {
            "age_band": [{"label": "25–30岁", "count": 12}, {"label": "31–35岁", "count": 9}],
            "gender": [{"label": "男", "count": 20}, {"label": "女", "count": 11}],
            "city": [{"label": "上海", "count": 8}, {"label": "北京", "count": 6}],
            "price_band": [{"label": "10–15 万", "count": 25}],
            "purchase_type": [{"label": "首购", "count": 18}, {"label": "换购（卖掉旧车）", "count": 9}],
        }
        rows = base[field]
        if model["label"] == POOL_LABEL:
            return [{"label": row["label"], "count": max(1, row["count"] - 4)} for row in rows]
        return rows

    def multi_counts(self, model, prefix):
        counts = [20, 4, 12, 10, 9, 8, 7, 6, 5, 4, 3, 3, 2, 2, 1, 1]
        answered = 31
        if model["label"] == POOL_LABEL:
            counts = [6, 18, 15, 12, 9, 7, 6, 5, 4, 3, 3, 2, 2, 1, 1, 1]
            answered = 39
        return {f"c{index + 1}": value for index, value in enumerate(counts)} | {"answered": answered}

    def score_stats(self, model):
        size = self._size(model)
        base = 8.0 if model["label"] != POOL_LABEL else 7.8
        return (
            {f"a{index}": size - 4 for index in range(1, 17)}
            | {f"m{index}": base - 0.1 * (index - 1) for index in range(1, 17)}
            | {f"l{index}": 2 for index in range(1, 17)}
        )

    def overall_score(self, model):
        return {"mean": 8.1 if model["label"] != POOL_LABEL else 7.9, "answered": 25}

    def recommendation_values(self, model):
        return ["9 十分推荐"] * 5 + ["7 比较推荐"] * 3

    def interview_reason_answers(self, model, question_ids):
        if model["label"] == POOL_LABEL:
            return [
                {"interview_id": "b1", "respondent_code": "BR1", "question_id": 29, "question_text": "", "answer_text": "操控更直接，开起来有信心"},
                {"interview_id": "b2", "respondent_code": "BR2", "question_id": 27, "question_text": "", "answer_text": "对比后觉得铂智3X更好开"},
            ]
        return [
            {"interview_id": "a1", "respondent_code": "AR1", "question_id": 29, "question_text": "", "answer_text": "空间大，后排坐着舒服"},
            {"interview_id": "a2", "respondent_code": "AR2", "question_id": 29, "question_text": "", "answer_text": "价格合适，配置够用"},
        ]

    def reputation(self, model):
        return {
            "points": [
                {"direction": "positive", "primary_label": "空间与实用性", "tertiary_label": "后排空间", "n": 30},
                {"direction": "positive", "primary_label": "外观设计", "tertiary_label": "造型", "n": 22},
                {"direction": "negative", "primary_label": "价格与购买价值", "tertiary_label": "优惠幅度", "n": 25},
                {"direction": "negative", "primary_label": "售后与服务保障", "tertiary_label": "交付等待", "n": 15},
            ],
            "rollup": [],
            "batch": "20261111T113525",
            "batch_reviews": 300,
            "denominators": {"positive": 200, "negative": 180, "reviews": 400},
        }

    def loss_rows(self, model):
        rows = []
        for index in range(8):
            rows.append(
                {
                    "purchase_model": POOL_LABEL,
                    "c0": TARGET_LABEL,
                    "c1": None,
                    "c2": None,
                    "f0": "纯电动",
                    "r0_1": index < 5,
                    "r0_2": index < 2,
                }
            )
        for _ in range(2):
            rows.append({"purchase_model": "宋PLUS新能源", "c0": TARGET_LABEL, "c1": None, "c2": None, "r0_1": True})
        rows.append({"purchase_model": "零跑B10", "c0": TARGET_LABEL, "c1": None, "c2": None, "r0_3": True})
        rows.append({"purchase_model": TARGET_LABEL, "c0": POOL_LABEL, "c1": None, "c2": None})
        return rows


class StubLLM:
    def __init__(self, route, outputs):
        self.route = route
        self.outputs = list(outputs)
        self.compose_calls = 0

    def __call__(self, system_prompt, message):
        if "意图分类器" in system_prompt:
            return json.dumps(self.route, ensure_ascii=False)
        self.compose_calls += 1
        output = self.outputs[min(self.compose_calls - 1, len(self.outputs) - 1)]
        return output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)


W1_OK = {
    "evidence": [{"text": "购车关注首位是空间", "refs": ["T2:attention.Q3_13__5"]}],
    "causes": [{"text": "竞品在安全性上赢走用户", "refs": ["T3:loss.铂智3X.reason[0]"]}],
    "actions": [{"text": "围绕空间与安全性做对比话术", "refs": ["T2:attention.Q3_13__5"]}],
    "sample_note": "深访仅 3 人，只出原话；流通数据尚未接入，本次结论不含规模维度。",
}

W2_OK = {
    "benchmark": {"text": "本次对标海狮05 vs 铂智3X（池内第 1）", "refs": ["T8:pool.0"]},
    "differences": [
        {"text": "购车关注差异集中在安全性与操控性", "refs": ["T10:购车关注.Q3_13__1", "T10:购车关注.Q3_13__2"]}
    ],
    "causes": [{"text": "对比后转向铂智3X的用户更看重操控", "refs": ["T9:a_to_b"]}],
    "gaps": [
        {"text": "本品需要补操控短板", "refs": ["T4:a.overall"]},
        {"text": "对标车需要守安全性优势", "refs": ["T4:b.overall"]},
    ],
    "sample_note": "流通数据尚未接入，本次结论不含规模维度。",
}


def build_service(route, outputs):
    llm = StubLLM(route, outputs)
    service = AgentAnalysisService(reader_factory=lambda: FakeReader(), llm=llm)
    return service, llm


class ToolboxTest(unittest.TestCase):
    def setUp(self):
        self.service = AgentAnalysisService(reader_factory=lambda: FakeReader())
        self.reader = FakeReader()
        self.toolbox = Toolbox(self.service.service, self.reader)
        self.target = self.service.service._model(TARGET_KEY)

    def test_competitor_pool_comes_from_loss_rows_and_keeps_small_rows(self):
        pool = self.toolbox.competitor_candidates(self.target, 3)
        rows = pool["data"]["pool"]
        self.assertEqual([row["model"] for row in rows], [POOL_LABEL, "宋PLUS", "零跑B10"])
        self.assertEqual([row["people"] for row in rows], [8, 2, 1])
        self.assertEqual([row["rank"] for row in rows], [1, 2, 3])
        self.assertEqual(pool["data"]["total_compared"], 11)
        self.assertIsNotNone(rows[0]["ratio"])
        self.assertIsNone(rows[1]["ratio"])

    def test_compare_metric_hides_delta_when_one_side_below_five(self):
        competitor = self.service.service._model("toyota-bz3x")
        result = self.toolbox.compare_metric(self.target, competitor, "attention")
        row = next(item for item in result["data"]["rows"] if item["key"] == "Q3_13__2")
        self.assertIsNone(row["a"]["ratio"])
        self.assertIsNone(row["delta_pp"])
        self.assertEqual(row["level"], "L1")


class WorkflowTest(unittest.TestCase):
    def test_w2_uses_pool_top1_without_asking(self):
        route = {"template": "W2", "metric": "profile", "competitor": None, "confidence": 0.9}
        service, _ = build_service(route, [W2_OK])
        result = service.run(TARGET_KEY, "对比本品和竞品，用户画像、购车关注有何差异")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["template"], "W2")
        self.assertEqual(result["competitor"]["label"], POOL_LABEL)
        self.assertEqual(result["pool_rank"], 1)
        self.assertEqual(result["verification"]["attempts"], 1)
        self.assertEqual(result["answer"]["benchmark"]["refs"], ["T8:pool.0"])

    def test_named_competitor_outside_pool_returns_no_sample(self):
        route = {"template": "W2", "metric": "profile", "competitor": "汉兰达", "confidence": 0.9}
        service, llm = build_service(route, [W2_OK])
        result = service.run(TARGET_KEY, "本品和汉兰达比一下用户画像")
        self.assertEqual(result["status"], "no_comparison_sample")
        self.assertIn("无对比样本", result["message"])
        self.assertEqual([row["model"] for row in result["pool"]][:1], [POOL_LABEL])
        self.assertEqual(llm.compose_calls, 0)

    def test_unverified_number_triggers_one_rewrite(self):
        route = {"template": "W2", "metric": "profile", "competitor": None, "confidence": 0.9}
        bad = json.loads(json.dumps(W2_OK, ensure_ascii=False))
        bad["differences"] = [{"text": "本品满意度 999 分", "refs": ["T4:a.overall"]}]
        service, llm = build_service(route, [bad, W2_OK])
        result = service.run(TARGET_KEY, "对比本品和竞品")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["verification"]["attempts"], 2)
        self.assertEqual(llm.compose_calls, 2)

    def test_second_validation_failure_returns_error_code(self):
        route = {"template": "W2", "metric": "profile", "competitor": None, "confidence": 0.9}
        bad = json.loads(json.dumps(W2_OK, ensure_ascii=False))
        bad["differences"] = [{"text": "本品满意度 999 分", "refs": ["T4:a.overall"]}]
        service, _ = build_service(route, [bad, bad])
        with self.assertRaises(AgentAnalysisError) as context:
            service.run(TARGET_KEY, "对比本品和竞品")
        self.assertEqual(context.exception.code, "E_NUM_UNVERIFIED")

    def test_w1_includes_four_sources_and_circulation_empty_state(self):
        route = {"template": "W1", "metric": None, "competitor": None, "confidence": 0.9}
        service, _ = build_service(route, [W1_OK])
        result = service.run(TARGET_KEY, "综合看关注、战胜战败、满意度和口碑，应该怎么打")
        self.assertEqual(result["status"], "ok")
        tools = {tool["tool"]: tool["status"] for tool in result["tools"]}
        self.assertEqual(tools["bci_market_circulation"], "not_available")
        self.assertEqual(tools["bci_reputation"], "ok")
        self.assertEqual(tools["bci_interview_quotes"], "ok")
        self.assertTrue(any("流通数据尚未接入" in line for line in result["warnings"]))


if __name__ == "__main__":
    unittest.main()
