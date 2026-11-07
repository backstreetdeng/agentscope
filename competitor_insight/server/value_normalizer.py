"""枚举取值归一：标签里常见的修饰词、口语、标点与多值写法集中在此处理。

约定（与 D3 契约一致）：
- `exact`      标准值（去标点后命中模板选项）→ 直接使用；
- `normalized` 口语/修饰写法能唯一推出选项 → 归一使用，并在来源里记录原值；
- `no_value`   明确表示没有数据（空值、「未提及」「不适用」等）→ 落 no_data_reason；
- `ambiguous`  多个互斥选项同时出现 → 不臆断，落 no_data_reason + suspect；
- `fallback`   互斥时由 `interview.purchase_type` 交叉校验唯一命中 → 取值并留修正记录；
- `unknown`    既非标准值也不是可识别的同义写法 → 抛 invalid_enum，不硬猜。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from competitor_insight.server.evidence_gate import EvidenceGateError, normalize_value

# 「没有数据」的表述：归一后按缺失处理，不算错误。
NO_VALUE_MARKERS = (
    "未提及",
    "未涉及",
    "未回答",
    "未答",
    "不适用",
    "没有提及",
    "不知道",
    "不清楚",
    "暂无",
)

# 否定表述：不能因为句子里出现选项词就当成该选项。
NEGATION_MARKERS = ("不是", "并非", "不属于", "没有", "非")

# 常见修饰前缀：去掉后若能唯一命中选项，即视为同义写法。
MODIFIER_PREFIXES = (
    "实际",
    "确切",
    "确实",
    "确为",
    "的确",
    "基本",
    "大致",
    "算是",
    "属于",
    "就是",
    "应该是",
    "应为",
    "是",
    "为",
)

SPLIT_PATTERN = re.compile(r"[；;、,，/]")

# 互斥多值时的元数据回退字段（目前只有购车属性有对应元数据）。
METADATA_FALLBACK_FIELD = "purchase_type"
FALLBACK_RULE = "ambiguous_tag_metadata_fallback"


@dataclass
class EnumResolution:
    raw: str
    value: str | None
    status: str
    reason: str = ""
    candidates: list[str] = field(default_factory=list)
    correction: dict | None = None

    def as_source_ref(self) -> dict:
        """写进 source_ref 的归一记录，保证可追溯。"""
        if self.status != "normalized":
            return {}
        return {"normalized_from": self.raw, "normalized_rule": self.reason}


def _match_single(text: str, allowed: list[str]) -> str | None:
    """单个片段 → 选项；只做「唯一命中」判断，不做猜测。"""
    cleaned = normalize_value(text)
    if not cleaned:
        return None
    if cleaned in allowed:
        return cleaned

    body = cleaned
    for prefix in MODIFIER_PREFIXES:
        if body.startswith(prefix) and body[len(prefix):] in allowed:
            return body[len(prefix):]

    # 同义关系：选项作为完整词出现在句子里，且只出现一个选项。
    hits = [option for option in allowed if len(option) >= 2 and option in cleaned]
    distinct = list(dict.fromkeys(hits))
    if len(distinct) == 1:
        return distinct[0]
    return None


def resolve_enum(raw: str, options: list[str]) -> EnumResolution:
    """把标签原值解析成模板选项之一；无法确定时返回状态而不是猜测。"""
    text = normalize_value(raw)
    allowed = [normalize_value(option) for option in options]

    if not text:
        return EnumResolution(raw=raw, value=None, status="no_value", reason="空值")
    if text in NO_VALUE_MARKERS:
        return EnumResolution(raw=raw, value=None, status="no_value", reason=f"原值「{text}」表示没有数据")
    if any(marker in text for marker in NO_VALUE_MARKERS):
        return EnumResolution(raw=raw, value=None, status="no_value", reason=f"原值「{text}」表示没有数据")
    if any(marker in text for marker in NEGATION_MARKERS):
        return EnumResolution(raw=raw, value=None, status="unknown", reason=f"原值「{text}」含否定表述，不能据此取值")

    parts = [normalize_value(part) for part in SPLIT_PATTERN.split(text) if normalize_value(part)]
    if len(parts) > 1:
        candidates: list[str] = []
        unmatched: list[str] = []
        for part in parts:
            hit = _match_single(part, allowed)
            if hit is None:
                unmatched.append(part)
            elif hit not in candidates:
                candidates.append(hit)
        if len(candidates) > 1:
            return EnumResolution(
                raw=raw, value=None, status="ambiguous",
                reason=f"标签含多个互斥取值：{'；'.join(parts)}，无法确定单一选项",
                candidates=candidates,
            )
        if unmatched:
            return EnumResolution(
                raw=raw, value=None, status="unknown",
                reason=f"原值「{text}」中有无法归一为模板选项的片段：{'；'.join(unmatched)}",
                candidates=candidates,
            )
        return EnumResolution(
            raw=raw, value=candidates[0], status="normalized",
            reason=f"多片段归一为同一选项：{'；'.join(parts)}",
            candidates=candidates,
        )

    hit = _match_single(text, allowed)
    if hit is None:
        return EnumResolution(
            raw=raw, value=None, status="unknown",
            reason=f"原值「{text}」既不在模板选项 {allowed} 中，也不属于可识别的同义写法",
        )
    if hit == text:
        return EnumResolution(raw=raw, value=hit, status="exact")
    return EnumResolution(raw=raw, value=hit, status="normalized", reason=f"口语/修饰写法归一：{text} → {hit}")


def resolve_enum_or_raise(dimension_id: str, raw: str, options: list[str]) -> EnumResolution:
    """供生成器使用：unknown 直接按 invalid_enum 失败，其余状态交给调用方分流。"""
    resolved = resolve_enum(raw, options)
    if resolved.status == "unknown":
        raise EvidenceGateError(
            "invalid_enum",
            f"{dimension_id}：取值 {raw!r} 不在模板选项 {list(options)} 中，且无法归一",
        )
    return resolved


def resolve_enum_with_fallback(
    dimension_id: str,
    raw: str,
    options: list[str],
    metadata: dict,
) -> EnumResolution:
    """互斥多值时回退查 `interview.purchase_type`。

    只有元数据恰好等于其中一个候选才采用；元数据缺失或与候选都不一致时
    保持 `ambiguous`，由调用方落 suspect，不猜。
    """
    resolved = resolve_enum(raw, options)
    if resolved.status == "unknown":
        raise EvidenceGateError(
            "invalid_enum",
            f"{dimension_id}：取值 {raw!r} 不在模板选项 {list(options)} 中，且无法归一",
        )
    if resolved.status != "ambiguous":
        return resolved

    meta_value = normalize_value(str(metadata.get(METADATA_FALLBACK_FIELD) or ""))
    if meta_value and meta_value in resolved.candidates:
        return EnumResolution(
            raw=raw,
            value=meta_value,
            status="fallback",
            reason=(
                f"标签含多个互斥取值（{'、'.join(resolved.candidates)}），"
                f"按 {METADATA_FALLBACK_FIELD}={meta_value} 交叉校验采用"
            ),
            candidates=resolved.candidates,
            correction={
                "from_raw_tag_value": raw,
                "metadata": {"field": METADATA_FALLBACK_FIELD, "value": meta_value},
                "rule": FALLBACK_RULE,
                "basis": (
                    f"标签「{raw}」含互斥候选 {'、'.join(resolved.candidates)}；"
                    f"interview.{METADATA_FALLBACK_FIELD}={meta_value} 恰为其一"
                ),
            },
        )
    return resolved
