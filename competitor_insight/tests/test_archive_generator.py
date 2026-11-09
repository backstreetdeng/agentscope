"""BCI-004 · D3 生成器与证据硬门测试。

不连数据库：用固定 fixture 构造 InterviewBundle，覆盖
- 43 维逐维落位，确定性维度不调用模型；
- 8 个无来源维直接落 no_source_reason；
- LLM 只回证据 ID，原话由服务端截取；
- 伪造 ID / 跨人证据 / 非法枚举 / 证据超限 / 非法 JSON 均整人失败；
- 满意度只取 Q59 明确数字（区间取中点），无分数时如实标注原因。
"""

from __future__ import annotations

import json
import re
import unittest

from competitor_insight.server.archive_generator import (
    NO_SCORE_ABSENT,
    NO_SCORE_DESCRIPTIVE,
    ArchiveGenerator,
    GenerationError,
    InterviewBundle,
    TagValue,
)
from competitor_insight.server.evidence_gate import EvidenceCandidate, EvidenceGate

INTERVIEW_ID = "R900"

BASE_ANSWERS: dict[int, str] = {
    5: "埃安的车机系统还可以，但内饰一般。",
    20: "空间最重要，其次是品牌和性价比。",
    21: "上次主要看外观和动力。",
    26: "对比理想L7、问界M8、星纪元，最终还是选了唐L。",
    29: "后排中间位置有点妥协。",
    46: "每天通勤 40 公里，周末带家人出游。",
    50: "经常跑高速，需要智驾。",
    55: "家里两个小孩，需要大空间。",
    56: "停车位比较窄。",
    59: "综合7-8分，空间满意，智驾不满意。",
    60: "主要在城市和高速使用。",
    63: "售后咨询过异响，答复一般。",
    65: "再购会优先考虑增程。",
    66: "再购可能看理想或问界。",
    68: "26-30岁。",
    81: "主要看垂媒和短视频。",
}

BASE_TAGS: list[tuple[str, str, str, str, str]] = [
    ("T01", "年龄", "26-30岁。", "可信", "matched_option"),
    ("T02", "首增换购属性", "增购。", "可信", "matched_option"),
    ("T03", "核心对比车型", "理想L7；问界M8；星纪元。", "可信", "matched_option"),
    ("T04", "最终核心对比车型", "唐L。", "可信", "matched_option"),
    ("T05", "购车预算", "25万元。", "可信", "matched_option"),
    ("T06", "本次购车关注", "空间（重要程度=最重要）；品牌；性价比", "可信", "matched_option"),
    ("T07", "上次购车关注", "外观；动力", "可信", "matched_option"),
    ("T08", "满意点", "空间；操控。", "可信", "matched_option"),
    ("T09", "不满意点", "智驾；内饰。", "可信", "matched_option"),
    ("T10", "汽车触媒偏好", "懂车帝；抖音。", "可信", "matched_option"),
    ("T11", "再购燃料类型", "增程。", "可信", "matched_option"),
    ("T12", "再购考虑的品牌类型", "新势力。", "可信", "custom_summary"),
    ("T13", "再购对不同品牌的看法", "理想更成熟。", "可信", "custom_summary"),
    ("T14", "用车过程关注", "续航；补能。", "可信", "matched_option"),
]

BASE_INTERVIEW = {
    "interview_id": INTERVIEW_ID,
    "city": "重庆",
    "vehicle_model": "唐L",
    "purchase_type": "增购",
    "metadata": {},
}


def build_bundle(
    *,
    answers: dict[int, str] | None = None,
    tags: list[tuple[str, str, str, str, str]] | None = None,
    candidates: list[EvidenceCandidate] | None = None,
    tag_evidence_ids: dict[str, list[str]] | None = None,
) -> InterviewBundle:
    answers = BASE_ANSWERS if answers is None else answers
    tags = BASE_TAGS if tags is None else tags
    if candidates is None:
        candidates = [
            EvidenceCandidate(f"EV-{qid}", "evidence", INTERVIEW_ID, qid, "受访者", text)
            for qid, text in answers.items()
        ]
    grouped: dict[str, list[TagValue]] = {}
    for tag_id, name, value, trust, status in tags:
        grouped.setdefault(name, []).append(TagValue(tag_id, name, value, trust, status))
    return InterviewBundle(
        interview=dict(BASE_INTERVIEW),
        answers={qid: {"answer_id": f"A-{qid}", "answer_text": text} for qid, text in answers.items()},
        tags={name: tuple(values) for name, values in grouped.items()},
        gate=EvidenceGate(INTERVIEW_ID, candidates),
        tag_evidence_ids={k: tuple(v) for k, v in (tag_evidence_ids or {}).items()},
    )


class FakeSource:
    def __init__(self, bundle: InterviewBundle) -> None:
        self.bundle = bundle

    def load(self, interview_id: str) -> InterviewBundle:
        return self.bundle


class RecordingLlm:
    """默认按 prompt 里第一个真实证据 ID 作答，记录每次调用。"""

    def __init__(self, reply=None) -> None:
        self.prompts: list[str] = []
        self._reply = reply

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if self._reply is not None:
            return self._reply(prompt) if callable(self._reply) else self._reply
        ids = re.findall(r"证据ID：([^\n]+)", prompt)
        first = ids[0].split(",")[0].strip() if ids else ""
        return json.dumps({"value": "归纳值", "evidence_ids": [first]}, ensure_ascii=False)

    def dimension_ids(self) -> list[str]:
        return re.findall(r"dimension_id: (\S+)", "\n".join(self.prompts))


def make_generator(bundle: InterviewBundle, llm=None) -> tuple[ArchiveGenerator, RecordingLlm | None]:
    recorder = llm if isinstance(llm, RecordingLlm) else llm
    generator = ArchiveGenerator(FakeSource(bundle), llm=recorder, model="test-model")
    return generator, recorder


def field_of(draft, dimension_id: str):
    return next(f for f in draft.fields if f.dimension_id == dimension_id)


def has_value(field) -> bool:
    if field.value_text not in (None, ""):
        return True
    return field.value_json not in (None, "", [], {})


class ArchiveGeneratorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.generator, cls.llm = make_generator(build_bundle(), RecordingLlm())
        cls.draft = cls.generator.generate(INTERVIEW_ID)
        cls.source_map = cls.generator.source_map
        cls.template = cls.generator.template

    def test_fixture_covers_all_43_dimensions_in_template_order(self):
        self.assertEqual(len(self.draft.fields), 43)
        self.assertEqual(
            [f.dimension_id for f in self.draft.fields],
            [d.dimension_id for d in self.source_map.dimensions],
        )
        self.assertEqual(
            [f.dimension_id for f in self.draft.fields],
            [d["id"] for d in self.template["dimensions"]],
        )

    def test_draft_passes_store_validation(self):
        self.draft.validate()

    def test_deterministic_dimensions_never_call_llm(self):
        called = set(self.llm.dimension_ids())
        deterministic = {
            d.dimension_id
            for d in self.source_map.dimensions
            if d.fill_mode in ("tag", "metadata", "derived", "none")
            and d.dimension_id != "satisfaction_score"
        }
        self.assertFalse(called & deterministic)
        self.assertTrue(called.issubset({d.dimension_id for d in self.source_map.dimensions if d.fill_mode == "llm"}))

    def test_no_source_dimensions_carry_template_reason(self):
        no_source = self.source_map.no_source_dimensions()
        self.assertEqual(len(no_source), 3)
        for dim in no_source:
            field = field_of(self.draft, dim.dimension_id)
            self.assertEqual(field.fill_mode, "none")
            self.assertEqual(field.no_data_reason, dim.no_source_reason)
            self.assertEqual(field.source_ref.get("no_source_scope"), "template")
            self.assertFalse(has_value(field))
            self.assertEqual(field.review_status, "missing")

    def test_status_is_partial_and_no_source_is_not_counted_as_filled(self):
        required_ids = {d["id"] for d in self.template["dimensions"] if d.get("required", True)}
        filled = sum(
            1 for f in self.draft.fields if f.dimension_id in required_ids and has_value(f)
        )
        self.assertEqual(len(required_ids), 38)
        self.assertEqual(self.draft.coverage_required, round(filled / 38 * 100, 2))
        self.assertEqual(self.draft.status, "partial")
        self.assertLess(self.draft.coverage_required, 100.0)
        for dim in self.source_map.no_source_dimensions():
            if dim.dimension_id in required_ids:
                self.assertFalse(has_value(field_of(self.draft, dim.dimension_id)))

    def test_metadata_dimension_takes_interview_column(self):
        field = field_of(self.draft, "purchased_model_owned")
        self.assertEqual(field.fill_mode, "metadata")
        self.assertEqual(field.value_text, "唐L")
        self.assertEqual(field.source_ref.get("fields"), ["vehicle_model"])

    def test_tag_enum_value_is_normalized_to_template_option(self):
        field = field_of(self.draft, "purchase_attribute")
        self.assertEqual(field.fill_mode, "tag")
        self.assertEqual(field.value_text, "增购")
        self.assertIn("T02", field.source_ref.get("tag_ids", []))

    def test_tag_multi_value_is_split_into_list(self):
        field = field_of(self.draft, "info_channels")
        self.assertEqual(field.fill_mode, "tag")
        self.assertIsNone(field.value_text)
        self.assertEqual(field.value_json, ["懂车帝", "抖音"])

    def test_derived_dimension_subtracts_final_models(self):
        field = field_of(self.draft, "abandoned_models")
        self.assertEqual(field.fill_mode, "derived")
        self.assertEqual(field.value_json, ["理想L7", "问界M8", "星纪元"])

    def test_llm_field_quote_comes_from_server_not_model(self):
        field = field_of(self.draft, "consideration_priority")
        self.assertEqual(field.fill_mode, "llm")
        self.assertEqual(field.value_text, "归纳值")
        self.assertEqual(len(field.evidence_refs), 1)
        ref = field.evidence_refs[0]
        self.assertEqual(ref["id"], "EV-20")
        self.assertEqual(ref["quote"], BASE_ANSWERS[20])
        self.assertEqual(ref["kind"], "evidence")
        self.assertFalse(ref["source_missing"])

    def test_prompt_lists_real_evidence_ids(self):
        prompt = next(p for p in self.llm.prompts if "dimension_id: consideration_priority" in p)
        self.assertIn("- Q20 证据ID：EV-20", prompt)
        self.assertIn("- Q21 证据ID：EV-21", prompt)

    def test_aion_impression_uses_brand_tag_material(self):
        """2026-11-09 参数化后：品牌印象维用「对各品牌的看法」标签材料，维度名按受访者车系替换。"""
        tags = list(BASE_TAGS) + [
            ("T30", "对不同品牌的看法及原因", "对自主品牌印象一般，网约车多。", "可信", "custom_summary"),
        ]
        generator, llm = make_generator(
            build_bundle(
                tags=tags,
                tag_evidence_ids={"对不同品牌的看法及原因": ["TE-30a", "TE-30b"]},
            ),
            RecordingLlm(),
        )
        generator.generate(INTERVIEW_ID)
        prompt = next(p for p in llm.prompts if "dimension_id: aion_brand_impression" in p)
        self.assertIn("维度：对比亚迪品牌的印象和了解", prompt)  # {brand} 按 唐L→比亚迪 替换
        self.assertIn("对不同品牌的看法及原因=对自主品牌印象一般", prompt)
        self.assertIn("- 对不同品牌的看法及原因：TE-30a, TE-30b", prompt)  # 标签证据 ID 已暴露给模型

    def test_llm_value_without_evidence_ids_degrades_to_no_data(self):
        """2026-11-09 R002 反馈：模型给值但不绑证据 → 仅该维缺失，不再整人失败。"""
        llm = RecordingLlm(json.dumps({"value": "某结论", "evidence_ids": []}))
        generator, _ = make_generator(build_bundle(), llm)
        draft = generator.generate(INTERVIEW_ID)
        field = field_of(draft, "archive_summary")
        self.assertEqual(field.fill_mode, "none")
        self.assertIn("未返回可绑定", field.no_data_reason)
        self.assertEqual(field.review_status, "missing")

    def test_satisfaction_range_uses_midpoint_and_keeps_raw(self):
        field = field_of(self.draft, "satisfaction_score")
        self.assertEqual(field.fill_mode, "derived")
        self.assertEqual(field.value_text, "7-8分")
        self.assertEqual(field.value_json["score"], 7.5)
        self.assertEqual(field.value_json["score_low"], 7.0)
        self.assertEqual(field.value_json["score_high"], 8.0)
        self.assertEqual(field.source_ref.get("question_id"), 59)
        self.assertEqual(field.evidence_refs[0]["id"], "EV-59")


class RejectionTest(unittest.TestCase):
    def test_fabricated_evidence_id_fails_whole_interview(self):
        llm = RecordingLlm(json.dumps({"value": "x", "evidence_ids": ["EV-FAKE"]}))
        generator, _ = make_generator(build_bundle(), llm)
        with self.assertRaises(GenerationError) as ctx:
            generator.generate(INTERVIEW_ID)
        self.assertEqual(ctx.exception.code, "cross_interview_or_fabricated_evidence")

    def test_evidence_from_another_interview_fails(self):
        candidates = [
            EvidenceCandidate(f"EV-{qid}", "evidence", INTERVIEW_ID, qid, "受访者", text)
            for qid, text in BASE_ANSWERS.items()
        ]
        candidates.append(EvidenceCandidate("EV-OTHER", "evidence", "R999", 20, "他人", "跨人原话"))
        llm = RecordingLlm(json.dumps({"value": "x", "evidence_ids": ["EV-OTHER"]}))
        generator, _ = make_generator(build_bundle(candidates=candidates), llm)
        with self.assertRaises(GenerationError) as ctx:
            generator.generate(INTERVIEW_ID)
        self.assertEqual(ctx.exception.code, "cross_interview_or_fabricated_evidence")

    def test_illegal_enum_fails(self):
        tags = [
            (tag_id, name, "置换。" if name == "首增换购属性" else value, trust, status)
            for tag_id, name, value, trust, status in BASE_TAGS
        ]
        generator, _ = make_generator(build_bundle(tags=tags), RecordingLlm())
        with self.assertRaises(GenerationError) as ctx:
            generator.generate(INTERVIEW_ID)
        self.assertEqual(ctx.exception.code, "invalid_enum")

    def test_more_than_five_evidence_fails(self):
        candidates = [
            EvidenceCandidate(f"EV-{qid}", "evidence", INTERVIEW_ID, qid, "受访者", text)
            for qid, text in BASE_ANSWERS.items()
        ]
        candidates += [
            EvidenceCandidate(f"EV-20-{i}", "evidence", INTERVIEW_ID, 20, "受访者", BASE_ANSWERS[20])
            for i in range(6)
        ]
        llm = RecordingLlm(
            json.dumps({"value": "x", "evidence_ids": [f"EV-20-{i}" for i in range(6)]})
        )
        generator, _ = make_generator(build_bundle(candidates=candidates), llm)
        with self.assertRaises(GenerationError) as ctx:
            generator.generate(INTERVIEW_ID)
        self.assertEqual(ctx.exception.code, "too_many_evidence")

    def test_non_json_reply_fails(self):
        generator, _ = make_generator(build_bundle(), RecordingLlm("这不是 JSON"))
        with self.assertRaises(GenerationError) as ctx:
            generator.generate(INTERVIEW_ID)
        self.assertEqual(ctx.exception.code, "invalid_llm_json")

    def test_missing_llm_client_fails_instead_of_faking(self):
        generator = ArchiveGenerator(FakeSource(build_bundle()), llm=None)
        with self.assertRaises(GenerationError) as ctx:
            generator.generate(INTERVIEW_ID)
        self.assertEqual(ctx.exception.code, "llm_client_required")

    def test_quote_is_truncated_to_300_chars(self):
        long_text = "空间很大。" * 80
        answers = dict(BASE_ANSWERS)
        answers[20] = long_text
        generator, _ = make_generator(build_bundle(answers=answers), RecordingLlm())
        field = field_of(generator.generate(INTERVIEW_ID), "brand_product_service_rank")
        self.assertEqual(len(field.evidence_refs[0]["quote"]), 300)


class NoDataTest(unittest.TestCase):
    def test_untrusted_tag_is_not_used(self):
        tags = [
            (tag_id, name, value, "不可信：格式失败：value 中混入了属性内容" if name == "首增换购属性" else trust, status)
            for tag_id, name, value, trust, status in BASE_TAGS
        ]
        generator, _ = make_generator(build_bundle(tags=tags), RecordingLlm())
        field = field_of(generator.generate(INTERVIEW_ID), "purchase_attribute")
        self.assertEqual(field.fill_mode, "none")
        self.assertIn("未提取到可信值", field.no_data_reason)
        self.assertEqual(field.source_ref.get("no_source_scope"), "interview")

    def test_llm_dimension_without_evidence_skips_model(self):
        answers = dict(BASE_ANSWERS)
        candidates = [
            EvidenceCandidate(f"EV-{qid}", "evidence", INTERVIEW_ID, qid, "受访者", text)
            for qid, text in answers.items()
            if qid != 63
        ]
        llm = RecordingLlm()
        generator, _ = make_generator(build_bundle(answers=answers, candidates=candidates), llm)
        field = field_of(generator.generate(INTERVIEW_ID), "sales_marketing_attention")
        self.assertEqual(field.fill_mode, "none")
        self.assertIn("无可用证据", field.no_data_reason)
        self.assertNotIn("sales_marketing_attention", llm.dimension_ids())

    def test_satisfaction_with_only_descriptive_text(self):
        answers = dict(BASE_ANSWERS)
        answers[59] = "整体满意，空间大，智驾一般。"
        generator, _ = make_generator(build_bundle(answers=answers), RecordingLlm())
        field = field_of(generator.generate(INTERVIEW_ID), "satisfaction_score")
        self.assertEqual(field.fill_mode, "none")
        self.assertEqual(field.no_data_reason, NO_SCORE_DESCRIPTIVE)

    def test_satisfaction_absent_question(self):
        answers = {qid: text for qid, text in BASE_ANSWERS.items() if qid != 59}
        generator, _ = make_generator(build_bundle(answers=answers), RecordingLlm())
        field = field_of(generator.generate(INTERVIEW_ID), "satisfaction_score")
        self.assertEqual(field.fill_mode, "none")
        self.assertEqual(field.no_data_reason, NO_SCORE_ABSENT)


class EnumFallbackTest(unittest.TestCase):
    """互斥多值 → purchase_type：一致才取值，缺失/冲突保持 suspect。"""

    @staticmethod
    def _bundle(purchase_type):
        tags = [
            ("T02", "首增换购属性", "换购；增购。", "可信", "matched_option")
            if name == "首增换购属性"
            else (tag_id, name, value, trust, status)
            for tag_id, name, value, trust, status in BASE_TAGS
        ]
        bundle = build_bundle(tags=tags)
        bundle.interview["purchase_type"] = purchase_type
        return bundle

    def test_metadata_match_takes_value_and_records_correction(self):
        generator, _ = make_generator(self._bundle("增购"), RecordingLlm())
        field = field_of(generator.generate(INTERVIEW_ID), "purchase_attribute")
        self.assertEqual(field.fill_mode, "tag")
        self.assertEqual(field.value_text, "增购")
        self.assertEqual(field.review_status, "ok")
        self.assertIsNone(field.no_data_reason)
        correction = field.source_ref["correction"]
        self.assertEqual(correction["from_raw_tag_value"], "换购；增购。")
        self.assertEqual(correction["metadata"], {"field": "purchase_type", "value": "增购"})
        self.assertEqual(correction["rule"], "ambiguous_tag_metadata_fallback")
        self.assertIn("换购", correction["basis"])

    def test_metadata_conflict_stays_suspect(self):
        generator, _ = make_generator(self._bundle("首购"), RecordingLlm())
        field = field_of(generator.generate(INTERVIEW_ID), "purchase_attribute")
        self.assertEqual(field.fill_mode, "none")
        self.assertEqual(field.review_status, "suspect")
        self.assertIn("多个互斥取值", field.no_data_reason)
        self.assertEqual(field.source_ref["raw_tag_value"], "换购；增购。")

    def test_metadata_missing_stays_suspect(self):
        generator, _ = make_generator(self._bundle(None), RecordingLlm())
        field = field_of(generator.generate(INTERVIEW_ID), "purchase_attribute")
        self.assertEqual(field.fill_mode, "none")
        self.assertEqual(field.review_status, "suspect")


class MultiChannelNormalizationTest(unittest.TestCase):
    """信息渠道只在展示层归并，原始写法必须留在 source_ref。"""

    def test_channels_merged_for_display_and_raw_preserved(self):
        tags = [
            ("T10", "汽车触媒偏好", "哔哩哔哩；视频号；未提及；怪渠道。", "可信", "matched_option")
            if name == "汽车触媒偏好"
            else (tag_id, name, value, trust, status)
            for tag_id, name, value, trust, status in BASE_TAGS
        ]
        generator, _ = make_generator(build_bundle(tags=tags), RecordingLlm())
        field = field_of(generator.generate(INTERVIEW_ID), "info_channels")
        self.assertEqual(field.fill_mode, "tag")
        self.assertEqual(field.value_json, ["B站", "其他", "未归类"])
        source = field.source_ref
        self.assertEqual(source["raw_values"], ["哔哩哔哩；视频号；未提及；怪渠道。"])
        self.assertEqual(source["raw_parts"], ["哔哩哔哩", "视频号", "未提及", "怪渠道"])
        self.assertEqual(source["channel_normalization"], "presentation")


if __name__ == "__main__":
    unittest.main()
