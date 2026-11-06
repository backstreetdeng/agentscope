"""BCI-004 · 证据硬门。

规则（与方案 §2.3/D4 一致）：
- 模型只允许返回证据 ID，原话必须由服务端按 ID 截取，不接受模型生成文本；
- 证据必须属于当前受访者，跨人或不存在的 ID 一律判失败；
- 单维最多 5 条；重复 ID 去重；
- 枚举维度只接受模板声明的选项。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

MAX_EVIDENCE_PER_FIELD = 5
MAX_QUOTE_CHARS = 300


class EvidenceGateError(RuntimeError):
    """证据或枚举校验失败；code 用于调用方区分原因。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class EvidenceCandidate:
    evidence_id: str
    kind: str
    interview_id: str
    question_id: int | None
    speaker: str | None
    quote: str


class EvidenceGate:
    """当前受访者的证据索引；不在索引内的 ID 视为伪造或跨人。"""

    def __init__(self, interview_id: str, candidates: Iterable[EvidenceCandidate]) -> None:
        self.interview_id = interview_id
        self._index: dict[str, EvidenceCandidate] = {}
        for item in candidates:
            if item.interview_id != interview_id:
                continue
            self._index[item.evidence_id] = item

    def __len__(self) -> int:
        return len(self._index)

    def ids_for_question(self, question_id: int | None) -> list[str]:
        """返回该题下属于本受访者的证据 ID；用于在 prompt 中只暴露可引用的 ID。"""
        if question_id is None:
            return []
        return [key for key, item in self._index.items() if item.question_id == question_id]

    def resolve(self, dimension_id: str, refs: Any) -> list[dict[str, Any]]:
        if refs is None:
            return []
        if not isinstance(refs, list):
            raise EvidenceGateError("invalid_evidence_payload", f"{dimension_id}：evidence_ids 必须是数组")

        resolved: list[dict[str, Any]] = []
        seen: set[str] = set()
        for ref in refs:
            if isinstance(ref, dict):
                evidence_id = ref.get("id")
            elif isinstance(ref, str):
                evidence_id = ref
            else:
                raise EvidenceGateError(
                    "invalid_evidence_payload", f"{dimension_id}：证据项必须是 ID 字符串或含 id 的对象"
                )
            if not isinstance(evidence_id, str) or not evidence_id.strip():
                raise EvidenceGateError("invalid_evidence_payload", f"{dimension_id}：证据 ID 为空")
            evidence_id = evidence_id.strip()
            if evidence_id in seen:
                continue
            seen.add(evidence_id)
            candidate = self._index.get(evidence_id)
            if candidate is None:
                raise EvidenceGateError(
                    "cross_interview_or_fabricated_evidence",
                    f"{dimension_id}：证据 {evidence_id} 不属于受访者 {self.interview_id} 或不存在",
                )
            resolved.append(
                {
                    "kind": candidate.kind,
                    "id": candidate.evidence_id,
                    "question_id": candidate.question_id,
                    "speaker": candidate.speaker,
                    "quote": (candidate.quote or "")[:MAX_QUOTE_CHARS],
                    "source_missing": False,
                }
            )
            if len(resolved) > MAX_EVIDENCE_PER_FIELD:
                raise EvidenceGateError(
                    "too_many_evidence",
                    f"{dimension_id}：证据超过 {MAX_EVIDENCE_PER_FIELD} 条",
                )
        return resolved


def normalize_value(value: str) -> str:
    return (value or "").strip().strip("。；;，, ").strip()


def validate_enum(dimension_id: str, value: str, options: Iterable[str]) -> str:
    cleaned = normalize_value(value)
    allowed = [normalize_value(option) for option in options]
    if cleaned not in allowed:
        raise EvidenceGateError(
            "invalid_enum",
            f"{dimension_id}：取值 {value!r} 不在模板选项 {list(options)} 中",
        )
    return allowed[allowed.index(cleaned)]
