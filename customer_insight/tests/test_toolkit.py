"""agentic 自由问答工具集与证据注册表的轻量单元测试（不连数据库）。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from customer_insight.retrieval_service import (  # noqa: E402
    _is_definite_question,
    _looks_like_question,
    _pick_evidence_segments,
    _segment_score,
)
from customer_insight.segment_aliases import expand  # noqa: E402
from customer_insight.tool import build_user_insight_toolkit  # noqa: E402
from tools.custom_tools import (  # noqa: E402
    clear_evidence_registry,
    get_collected_evidence,
    register_evidence,
)


class TestUserInsightToolkit(unittest.TestCase):
    def test_toolkit_contains_all_tools(self):
        tools = build_user_insight_toolkit()
        names = {t.name for t in tools}
        self.assertEqual(len(tools), 13)
        self.assertEqual(
            names,
            {
                "interview_evidence_search",
                "battle_search",
                "quant_list_questions",
                "quant_stat",
                "quant_stat_in_group",
                "segment_clusters",
                "satisfaction_painpoints",
                "repurchase_intent",
                "demand_config_matrix",
                "config_detail",
                "competitor_compare",
                "web_search",
                "web_fetch",
            },
        )

    def test_every_tool_has_schema(self):
        for tool in build_user_insight_toolkit():
            self.assertTrue(tool.name)
            self.assertTrue(tool.description)
            self.assertIsInstance(tool.input_schema, dict)

    def test_evidence_registry_renumber_globally(self):
        clear_evidence_registry()
        first = register_evidence([{"evidence_id": "E1", "quote": "a"}])
        second = register_evidence([{"evidence_id": "E1", "quote": "b"}])
        self.assertEqual([e["evidence_id"] for e in first], ["E1"])
        # 第二次调用沿用全局编号，避免跨轮 [E#] 冲突
        self.assertEqual([e["evidence_id"] for e in second], ["E2"])
        self.assertEqual([e["evidence_id"] for e in get_collected_evidence()], ["E1", "E2"])

    def test_clear_evidence_registry(self):
        register_evidence([{"evidence_id": "E1", "quote": "a"}])
        clear_evidence_registry()
        self.assertEqual(get_collected_evidence(), [])


class TestSegmentAliases(unittest.TestCase):
    def test_exact_value_is_kept(self):
        self.assertEqual(expand(["首购"], ["首购", "换购", "增购"]), ["首购"])

    def test_aggregate_word_expands_to_real_values(self):
        self.assertEqual(
            sorted(expand(["增换购"], ["首购", "换购", "增购", "换购(报废)"])),
            sorted(["换购", "增购", "换购(报废)"]),
        )

    def test_unknown_value_is_preserved(self):
        self.assertEqual(expand(["置换"], ["首购", "换购", "增购"]), ["置换"])


class TestQuestionFilterLayering(unittest.TestCase):
    """问句过滤分层：确定性信号硬过滤，弱问句线索只降权保留。"""

    def test_prefixed_is_definite_question(self):
        for raw in ("M：那您主要考虑哪些方面呀？", "问：预算大概多少？", "访谈员：为什么选唐L？"):
            self.assertTrue(_is_definite_question({"quote_text": raw, "question_text": "为什么"}), raw)

    def test_clean_question_only_is_definite_question(self):
        row = {"quote_text": "那您主要考虑哪些方面呀？", "question_text": "购车主要考虑哪些方面？"}
        self.assertTrue(_is_definite_question(row))

    def test_respondent_speech_with_cue_is_not_definite(self):
        # 受访者口语含「怎么样」，不应被确定性信号命中
        row = {"quote_text": "感觉也不怎么样，就那样吧。", "question_text": "购车主要考虑哪些方面？"}
        self.assertFalse(_is_definite_question(row))

    def test_soft_cue_is_downgraded_in_scoring(self):
        # 弱线索命中：疑似提问（保持旧口径），打分上应比同类正分证据更低
        soft_row = {"quote_text": "感觉也不怎么样，就那样吧。", "question_text": "购车主要考虑哪些方面？"}
        plain_row = {"quote_text": "外观内饰很满意，空间也够大。", "question_text": "购车主要考虑哪些方面？"}
        answer = "外观内饰满意空间大"
        self.assertTrue(_looks_like_question(soft_row))
        self.assertLess(_segment_score(soft_row, answer), _segment_score(plain_row, answer))

    def test_soft_cue_row_can_be_picked(self):
        # 弱线索条目不再被整条丢弃：池子里只有它时仍可入选证据
        soft_row = {
            "quote_text": "感觉也不怎么样，就那样吧。",
            "question_text": "购车主要考虑哪些方面？",
            "start_sec": 1.0,
        }
        picked = _pick_evidence_segments([soft_row], "外观内饰很满意", limit=2)
        self.assertEqual(len(picked), 1)

    def test_definite_question_never_picked(self):
        row = {
            "quote_text": "M：那您主要考虑哪些方面呀？",
            "question_text": "购车主要考虑哪些方面？",
            "start_sec": 1.0,
        }
        picked = _pick_evidence_segments([row], "购车考虑哪些方面", limit=2)
        self.assertEqual(picked, [])


if __name__ == "__main__":
    unittest.main()
