"""BCI-004 · 档案生成器。

确定性优先：
- `tag` / `metadata` / `derived` 维度直接取库，不调用模型；
- `none` 维度直接落 `no_source_reason`（Q11），不用模型兜底；
- `llm` 维度才调用模型，模型只能返回证据 ID，由 EvidenceGate 校验并截取原话；
- 满意度评分不做模型估计：只从 Q59 原文提取明确数字（Q12）。

任一步校验失败即抛 `GenerationError`，由调用方整人判失败、不落库。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from dataclasses import field as dataclasses_field
from typing import Any, Callable, Protocol

from competitor_insight.server.archive_store import ArchiveDraft, ArchiveFieldRecord
from competitor_insight.server.channel_normalizer import normalize_channels
from competitor_insight.server.evidence_gate import (
    MAX_EVIDENCE_PER_FIELD,
    EvidenceCandidate,
    EvidenceGate,
    EvidenceGateError,
    normalize_value,
    validate_enum,
)
from competitor_insight.server.source_map import DimensionSource, SourceMap
from competitor_insight.server.template_registry import ARCHIVE_TEMPLATE_ID, TemplateRegistry
from competitor_insight.server.value_normalizer import resolve_enum_with_fallback
from competitor_insight.server.vehicle_naming import resolve_name

LlmClient = Callable[[str], str]

SCORE_PATTERNS = (
    re.compile(r"(\d+(?:\.\d+)?)\s*[-–—~至到]\s*(\d+(?:\.\d+)?)\s*分"),
    re.compile(r"(\d+(?:\.\d+)?)\s*分"),
)
NO_SCORE_DESCRIPTIVE = "访谈中未给出明确评分，仅有描述性评价"
NO_SCORE_ABSENT = "访谈中未给出明确评分"


class GenerationError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class TagValue:
    tag_id: str
    tag_name: str
    value: str
    trust_status: str
    extraction_status: str

    @property
    def usable(self) -> bool:
        if self.trust_status != "可信":
            return False
        if self.extraction_status in ("not_asked", "not_applicable"):
            return False
        return normalize_value(self.value) not in ("", "未提及", "不适用", "无")


@dataclass(frozen=True)
class InterviewBundle:
    interview: dict[str, Any]
    answers: dict[int, dict[str, Any]]
    tags: dict[str, tuple[TagValue, ...]]
    gate: EvidenceGate
    # 标签名 → 该标签的证据 ID（tag_evidence）；供 LLM 引用标签原话，防止编造 ID
    tag_evidence_ids: dict[str, tuple[str, ...]] = dataclasses_field(default_factory=dict)

    def answer_text(self, question_id: int) -> str:
        return (self.answers.get(question_id) or {}).get("answer_text") or ""

    def tag_values(self, names: tuple[str, ...]) -> list[TagValue]:
        return [tag for name in names for tag in self.tags.get(name, ()) if tag.usable]


class InterviewSource(Protocol):
    def load(self, interview_id: str) -> InterviewBundle: ...


class PostgresInterviewSource:
    """只读 user_insight.*；证据索引包含 evidence 与 tag_evidence 两类 ID。"""

    def __init__(self, connect_fn) -> None:
        self._connect = connect_fn

    def load(self, interview_id: str) -> InterviewBundle:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT interview_id, city, vehicle_model, purchase_type, metadata FROM user_insight.interview WHERE interview_id = %s",
                    (interview_id,),
                )
                row = cur.fetchone()
                if row is None:
                    raise GenerationError("interview_not_found", f"受访者不存在：{interview_id}")
                interview = {
                    "interview_id": row[0],
                    "city": row[1],
                    "vehicle_model": row[2],
                    "purchase_type": row[3],
                    "metadata": row[4] or {},
                }

                cur.execute(
                    "SELECT question_id, answer_id, answer_text FROM user_insight.answer WHERE interview_id = %s",
                    (interview_id,),
                )
                answers = {r[0]: {"answer_id": r[1], "answer_text": r[2]} for r in cur.fetchall()}

                cur.execute(
                    """
                    SELECT tag_id, tag_name, tag_value, trust_status, extraction_status
                    FROM user_insight.tag WHERE interview_id = %s
                    """,
                    (interview_id,),
                )
                tags: dict[str, list[TagValue]] = {}
                for tag_id, name, value, trust, status in cur.fetchall():
                    tags.setdefault(name, []).append(
                        TagValue(tag_id, name, value or "", trust or "", status or "")
                    )

                cur.execute(
                    """
                    SELECT evidence_id, 'evidence', interview_id, question_id, speaker_label, quote_text
                    FROM user_insight.evidence WHERE interview_id = %s
                    """,
                    (interview_id,),
                )
                candidates = [
                    EvidenceCandidate(r[0], r[1], r[2], r[3], r[4], r[5] or "") for r in cur.fetchall()
                ]
                cur.execute(
                    """
                    SELECT te.tag_evidence_id, 'tag_evidence', t.interview_id, te.question_id,
                           te.speaker_label, te.quote_text
                    FROM user_insight.tag_evidence te
                    JOIN user_insight.tag t ON t.tag_id = te.tag_id
                    WHERE t.interview_id = %s
                    """,
                    (interview_id,),
                )
                candidates += [
                    EvidenceCandidate(r[0], r[1], r[2], r[3], r[4], r[5] or "") for r in cur.fetchall()
                ]
                cur.execute(
                    """
                    SELECT t.tag_name, te.tag_evidence_id
                    FROM user_insight.tag_evidence te
                    JOIN user_insight.tag t ON t.tag_id = te.tag_id
                    WHERE t.interview_id = %s
                    ORDER BY te.question_id
                    """,
                    (interview_id,),
                )
                tag_evidence: dict[str, list[str]] = {}
                for name, te_id in cur.fetchall():
                    tag_evidence.setdefault(name, []).append(te_id)
        finally:
            conn.close()

        return InterviewBundle(
            interview=interview,
            answers=answers,
            tags={name: tuple(values) for name, values in tags.items()},
            gate=EvidenceGate(interview_id, candidates),
            tag_evidence_ids={name: tuple(ids[:5]) for name, ids in tag_evidence.items()},
        )


class ArchiveGenerator:
    def __init__(
        self,
        source: InterviewSource,
        *,
        registry: TemplateRegistry | None = None,
        llm: LlmClient | None = None,
        model: str | None = None,
        prompt_version: str = "d3-v1",
    ) -> None:
        bundle = (registry or TemplateRegistry()).load_ready(ARCHIVE_TEMPLATE_ID)
        self.source_map: SourceMap = bundle.require_source_map()
        self.template = bundle.definition
        self.template_id = bundle.template_id
        self.template_version = bundle.version
        self._dims = {d["id"]: d for d in self.template["dimensions"]}
        self._source = source
        self._llm = llm
        self._model = model
        self.prompt_version = prompt_version

    def generate(
        self,
        interview_id: str,
        should_stop: Callable[[], bool] | None = None,
    ) -> ArchiveDraft:
        bundle = self._source.load(interview_id)
        fields: list[ArchiveFieldRecord] = []
        for dim in self.source_map.dimensions:
            # 批量任务中止：每个维度开始前检查一次，已在途的模型请求无法中断，
            # 但不会再发起新的调用；未生成的草稿整体丢弃、不落库。
            if should_stop is not None and should_stop():
                raise GenerationError("cancelled", "运行已被用户中止")
            fields.append(self._build_field(dim, bundle))

        required_total = sum(1 for d in self.template["dimensions"] if d.get("required", True))
        required_filled = sum(
            1
            for field in fields
            if self._dims[field.dimension_id].get("required", True) and _has_value(field)
        )
        coverage = round(required_filled / required_total * 100, 2) if required_total else 0.0
        status = "ready" if required_filled == required_total else "partial"

        return ArchiveDraft(
            interview_id=interview_id,
            template_id=self.template_id,
            template_version=self.template_version,
            template_snapshot=self.template,
            status=status,
            coverage_required=coverage,
            fields=tuple(fields),
            model=self._model,
            prompt_version=self.prompt_version,
        )

    def _build_field(self, dim: DimensionSource, bundle: InterviewBundle) -> ArchiveFieldRecord:
        if dim.fill_mode == "none":
            return self._none_field(dim)
        if dim.fill_mode == "metadata":
            return self._metadata_field(dim, bundle)
        if dim.fill_mode == "tag":
            return self._tag_field(dim, bundle)
        if dim.fill_mode == "derived":
            return self._derived_field(dim, bundle)
        return self._llm_field(dim, bundle)

    def _none_field(self, dim: DimensionSource) -> ArchiveFieldRecord:
        if not dim.no_source_reason:
            raise GenerationError("missing_no_source_reason", f"{dim.dimension_id} 缺少 no_source_reason")
        return ArchiveFieldRecord(
            dimension_id=dim.dimension_id,
            group_id=dim.group_id,
            fill_mode="none",
            no_data_reason=dim.no_source_reason,
            source_ref={"no_source_scope": "template"},
            review_status="missing",
        )

    def _metadata_field(self, dim: DimensionSource, bundle: InterviewBundle) -> ArchiveFieldRecord:
        values = [bundle.interview.get(field) for field in dim.metadata_fields]
        value = next((v for v in values if v), None)
        if not value:
            return self._no_data(dim, f"访谈元数据缺少 {', '.join(dim.metadata_fields)}")
        return ArchiveFieldRecord(
            dimension_id=dim.dimension_id,
            group_id=dim.group_id,
            fill_mode="metadata",
            value_text=str(value),
            source_ref={"fields": list(dim.metadata_fields)},
        )

    def _tag_field(self, dim: DimensionSource, bundle: InterviewBundle) -> ArchiveFieldRecord:
        tags = bundle.tag_values(dim.tag_names)
        if not tags:
            return self._no_data(dim, f"所依赖标签未提取到可信值：{'、'.join(dim.tag_names)}")

        tpl = self._dims.get(dim.dimension_id, {})
        dim_type = tpl.get("type", "text")
        joined = "；".join(normalize_value(tag.value) for tag in tags)

        value_text: str | None = joined
        value_json: Any = None
        normalized_ref: dict = {}
        review_status = "auto"
        if dim_type == "enum":
            options = tpl.get("options", [])
            try:
                resolved = resolve_enum_with_fallback(
                    dim.dimension_id, tags[0].value, options, bundle.interview
                )
            except EvidenceGateError as exc:
                raise GenerationError(exc.code, str(exc)) from exc
            source_base = {
                "tag_ids": [tag.tag_id for tag in tags],
                "tag_names": list(dim.tag_names),
            }
            if resolved.status == "no_value":
                source_base["raw_tag_value"] = tags[0].value
                return ArchiveFieldRecord(
                    dimension_id=dim.dimension_id,
                    group_id=dim.group_id,
                    fill_mode="none",
                    no_data_reason=resolved.reason,
                    source_ref={**source_base, "no_source_scope": "interview"},
                    review_status="missing",
                )
            if resolved.status == "ambiguous":
                # 单选维遇到多个互斥选项且元数据无法裁决：不臆断取第一个，留待人工复核。
                return ArchiveFieldRecord(
                    dimension_id=dim.dimension_id,
                    group_id=dim.group_id,
                    fill_mode="none",
                    no_data_reason=resolved.reason,
                    source_ref={**source_base, "raw_tag_value": tags[0].value},
                    review_status="suspect",
                )
            value_text = resolved.value
            if resolved.status == "fallback":
                # 元数据交叉校验取值：留完整修正记录，重跑结果稳定。
                normalized_ref = {"correction": resolved.correction}
                review_status = "ok"
            else:
                normalized_ref = resolved.as_source_ref()
        elif dim_type == "multi":
            raw_parts: list[str] = []
            for tag in tags:
                for part in re.split(r"[；;、]", tag.value):
                    cleaned = normalize_value(part)
                    if cleaned and cleaned not in raw_parts:
                        raw_parts.append(cleaned)
            value_text = None
            # 展示/统计层归并；原始写法完整保留在 source_ref，便于回溯与重新归并。
            value_json = normalize_channels(raw_parts, dim.dimension_id)
            normalized_ref = {
                "raw_values": [tag.value for tag in tags],
                "raw_parts": raw_parts,
                "channel_normalization": "presentation",
            }

        return ArchiveFieldRecord(
            dimension_id=dim.dimension_id,
            group_id=dim.group_id,
            fill_mode="tag",
            value_text=value_text,
            value_json=value_json,
            source_ref={
                "tag_ids": [tag.tag_id for tag in tags],
                "tag_names": list(dim.tag_names),
                **normalized_ref,
            },
            review_status=review_status,
        )

    def _derived_field(self, dim: DimensionSource, bundle: InterviewBundle) -> ArchiveFieldRecord:
        if dim.derivation != "core_minus_final":
            raise GenerationError("unknown_derivation", f"{dim.dimension_id} 未知派生：{dim.derivation}")
        core_tags = bundle.tag_values(("核心对比车型",))
        final_tags = bundle.tag_values(("最终核心对比车型",))
        if not core_tags or not final_tags:
            return self._no_data(dim, "核心对比车型或最终核心对比车型缺失，无法派生")
        core = [normalize_value(x) for x in re.split(r"[；;、]", core_tags[0].value) if normalize_value(x)]
        final_raw = final_tags[0].value
        abandoned = [model for model in core if normalize_value(model) not in final_raw]
        if not abandoned:
            return self._no_data(dim, "核心对比车型均已进入最终对比，无被淘汰车型")
        return ArchiveFieldRecord(
            dimension_id=dim.dimension_id,
            group_id=dim.group_id,
            fill_mode="derived",
            value_json=abandoned,
            value_text="；".join(abandoned),
            source_ref={"derivation": dim.derivation, "tag_ids": [core_tags[0].tag_id, final_tags[0].tag_id]},
        )

    def _llm_field(self, dim: DimensionSource, bundle: InterviewBundle) -> ArchiveFieldRecord:
        if dim.dimension_id == "satisfaction_score":
            return self._satisfaction_field(dim, bundle)

        material = self._material(dim, bundle)
        if not material["answers"] and not material["tags"]:
            return self._no_data(dim, "访谈中未涉及该维度（无对应答案与标签）")
        if not any(material["evidence_ids"].values()):
            return self._no_data(dim, "访谈中未涉及该维度（无可用证据）")
        if self._llm is None:
            raise GenerationError("llm_client_required", f"{dim.dimension_id} 需要模型但未配置 llm client")

        prompt = self._build_prompt(dim, material, bundle)
        raw = self._llm(prompt)
        payload = self._parse_llm_json(dim, raw)

        # 模型可判定「无足够依据」而不给值；此时按个人维度无数据处理，不视为失败。
        value = payload.get("value")
        if value is None or value == "" or value == []:
            return self._no_data(dim, "模型判定访谈无足够依据，未生成值")

        returned_ids = [
            str(item).strip()
            for item in (payload.get("evidence_ids") or [])
            if str(item).strip()
        ]
        try:
            evidence = bundle.gate.resolve(
                dim.dimension_id, list(dict.fromkeys(returned_ids))
            )
        except EvidenceGateError as exc:
            # 伪造/跨人证据仍是硬失败（整人不落库）；模型没给 ID 只影响该维，不连坐。
            raise GenerationError(exc.code, str(exc)) from exc
        if not evidence:
            # 值无法绑定证据 → 不发布该值，仅该维记缺失（用户 2026-11-09 R002 反馈后调整）。
            return self._no_data(dim, "模型未返回可绑定的证据 ID，该维未生成")

        tpl = self._dims.get(dim.dimension_id, {})
        if tpl.get("type") == "enum":
            try:
                value = validate_enum(dim.dimension_id, str(value), tpl.get("options", []))
            except EvidenceGateError as exc:
                raise GenerationError(exc.code, str(exc)) from exc

        return ArchiveFieldRecord(
            dimension_id=dim.dimension_id,
            group_id=dim.group_id,
            fill_mode="llm",
            value_text=value if isinstance(value, str) else None,
            value_json=value if not isinstance(value, str) else None,
            evidence_refs=evidence,
            source_ref={"question_ids": list(dim.question_ids)},
        )

    def _satisfaction_field(self, dim: DimensionSource, bundle: InterviewBundle) -> ArchiveFieldRecord:
        text = bundle.answer_text(59)
        if not text:
            return self._no_data(dim, NO_SCORE_ABSENT)
        match = None
        for pattern in SCORE_PATTERNS:
            match = pattern.search(text)
            if match:
                break
        if match is None:
            descriptive = bool(re.search(r"满意|不满|可以|还行|不错", text))
            return self._no_data(dim, NO_SCORE_DESCRIPTIVE if descriptive else NO_SCORE_ABSENT)

        groups = [g for g in match.groups() if g is not None]
        if len(groups) == 2:
            low, high = float(groups[0]), float(groups[1])
            # 区间是访谈原文明确给出的，取中点仅作单一数值表示，同时保留原文与区间
            score = round((low + high) / 2, 1)
            value_json = {"score": score, "score_low": low, "score_high": high, "raw": match.group(0)}
        else:
            score = float(groups[0])
            value_json = {"score": score, "raw": match.group(0)}

        if match.group(0).replace(" ", "") not in text.replace(" ", ""):
            raise GenerationError("score_not_in_source", f"{dim.dimension_id}：提取分数未出现在 Q59 原文")

        evidence = []
        answer = bundle.answers.get(59) or {}
        if answer.get("answer_id"):
            ids = bundle.gate.ids_for_question(59)[:1]
            if ids:
                try:
                    evidence = bundle.gate.resolve(dim.dimension_id, ids)
                except EvidenceGateError:
                    evidence = []
        return ArchiveFieldRecord(
            dimension_id=dim.dimension_id,
            group_id=dim.group_id,
            fill_mode="derived",
            value_text=match.group(0),
            value_json=value_json,
            evidence_refs=evidence,
            source_ref={"question_id": 59, "answer_id": answer.get("answer_id")},
        )

    def _material(self, dim: DimensionSource, bundle: InterviewBundle) -> dict[str, Any]:
        # scope=questions 但未声明题号（仅挂标签）的维度：以全量答案节选作证据池，
        # 避免无证据 ID 被误判为「无材料」。
        if dim.scope == "interview" or not dim.question_ids:
            keys = sorted(bundle.answers)[:30]
            answers = {qid: bundle.answer_text(qid)[:400] for qid in keys}
        else:
            keys = [qid for qid in dim.question_ids if bundle.answer_text(qid)]
            answers = {qid: bundle.answer_text(qid)[:600] for qid in keys}
        tags = {tag.tag_name: normalize_value(tag.value) for tag in bundle.tag_values(dim.tag_names)}
        tag_evidence_ids = {
            name: list(bundle.tag_evidence_ids.get(name, ()))[:5]
            for name in dim.tag_names
            if bundle.tag_evidence_ids.get(name)
        }
        evidence_ids = {qid: bundle.gate.ids_for_question(qid) for qid in keys}
        return {
            "answers": answers,
            "tags": tags,
            "evidence_ids": evidence_ids,
            "tag_evidence_ids": tag_evidence_ids,
        }

    def _build_prompt(
        self, dim: DimensionSource, material: dict[str, Any], bundle: InterviewBundle
    ) -> str:
        tpl = self._dims.get(dim.dimension_id, {})
        vehicle = (bundle.interview.get("vehicle_model") or "") if bundle.interview else ""
        lines = [
            f"dimension_id: {dim.dimension_id}",
            f"维度：{resolve_name(tpl.get('name', dim.dimension_id), vehicle)}"
            f"（类型 {tpl.get('type', 'text')}）",
            f"任务：{resolve_name(tpl.get('description', ''), vehicle)}",
            f"合格标准：{resolve_name(tpl.get('qualified', ''), vehicle)}",
        ]
        if tpl.get("options"):
            lines.append(f"允许取值：{'、'.join(tpl['options'])}")
        lines.append("只能引用下列证据 ID，不得编造原话：")
        for qid in material["answers"]:
            ids = material["evidence_ids"].get(qid) or []
            if ids:
                lines.append(f"- Q{qid} 证据ID：{', '.join(ids[:3])}")
            else:
                lines.append(f"- Q{qid} 无可用证据ID，不得引用该题")
        lines.append("访谈材料：")
        for qid, text in material["answers"].items():
            lines.append(f"Q{qid}: {text}")
        if material["tags"]:
            lines.append("相关标签：" + "；".join(f"{k}={v}" for k, v in material["tags"].items()))
        if material.get("tag_evidence_ids"):
            lines.append("标签证据 ID（引用标签原话时只能用这些）：")
            for name, ids in material["tag_evidence_ids"].items():
                lines.append(f"- {name}：{', '.join(ids)}")
        lines.append(
            '输出 JSON：{"value": 字符串或数组, "evidence_ids": ["证据ID"]}'
            f"（evidence_ids 最多 {MAX_EVIDENCE_PER_FIELD} 个，按重要性排序）"
        )
        return "\n".join(lines)

    @staticmethod
    def _parse_llm_json(dim: DimensionSource, raw: str) -> dict[str, Any]:
        text = (raw or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise GenerationError("invalid_llm_json", f"{dim.dimension_id}：模型返回不是 JSON") from exc
        if not isinstance(payload, dict):
            raise GenerationError("invalid_llm_json", f"{dim.dimension_id}：模型返回必须是对象")
        return payload

    def _no_data(self, dim: DimensionSource, reason: str) -> ArchiveFieldRecord:
        # 个人层面无值也归为 fill_mode=none：存储层禁止「非 none 维带 no_data_reason」，
        # 且前端可凭 source_ref.no_source_scope 区分「本期无来源」与「该受访者未提及」。
        return ArchiveFieldRecord(
            dimension_id=dim.dimension_id,
            group_id=dim.group_id,
            fill_mode="none",
            no_data_reason=reason,
            source_ref={"no_source_scope": "interview"},
            review_status="missing",
        )


def _has_value(field: ArchiveFieldRecord) -> bool:
    if field.value_text not in (None, ""):
        return True
    return field.value_json not in (None, "", [], {})
