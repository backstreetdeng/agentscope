"""BCI-004 · 43 维 source-map 契约层。

职责：加载并校验 `competitor_insight/templates/<template_id>.source-map.json`，
保证维度集合、顺序、分组与模板定义一致，且题号 / 标签 / 元数据字段可被真实数据源满足。

本模块不连接数据库。数据库侧的存在性校验由调用方注入真实集合：
`validate_against_question_ids()` 与 `validate_against_tag_names()`。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

FILL_MODES: tuple[str, ...] = ("tag", "metadata", "derived", "llm", "none")
SCOPES: tuple[str, ...] = ("interview", "questions")

# 与 user_insight.interview 真实列名一致（2026-11-07 实测）
ALLOWED_METADATA_FIELDS: tuple[str, ...] = (
    "vehicle_model",
    "purchase_type",
    "city",
)

_REQUIRED_TOP_KEYS = (
    "source_map_version",
    "template_id",
    "template_version",
    "dimensions",
)


class SourceMapError(ValueError):
    """source-map 结构或交叉校验失败。"""


@dataclass(frozen=True)
class DimensionSource:
    dimension_id: str
    group_id: str
    fill_mode: str
    scope: str
    question_ids: tuple[int, ...] = ()
    tag_names: tuple[str, ...] = ()
    metadata_fields: tuple[str, ...] = ()
    derivation: str | None = None
    no_source_reason: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class SourceMap:
    template_id: str
    template_version: str
    source_map_version: int
    dimensions: tuple[DimensionSource, ...]
    evidence_basis: str | None = None

    def by_id(self) -> dict[str, DimensionSource]:
        return {d.dimension_id: d for d in self.dimensions}

    def question_ids(self) -> set[int]:
        return {qid for d in self.dimensions for qid in d.question_ids}

    def tag_names(self) -> set[str]:
        return {name for d in self.dimensions for name in d.tag_names}

    def no_source_dimensions(self) -> tuple[DimensionSource, ...]:
        return tuple(d for d in self.dimensions if d.fill_mode == "none")

    def fill_mode_counts(self) -> dict[str, int]:
        counts = {mode: 0 for mode in FILL_MODES}
        for dim in self.dimensions:
            counts[dim.fill_mode] += 1
        return counts


def _read_json(path: str | Path) -> dict[str, Any]:
    file = Path(path)
    if not file.exists():
        raise SourceMapError(f"文件不存在：{file}")
    try:
        data = json.loads(file.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise SourceMapError(f"JSON 解析失败：{file}：{exc}") from exc
    if not isinstance(data, dict):
        raise SourceMapError(f"顶层必须是对象：{file}")
    return data


def load_template_definition(path: str | Path) -> dict[str, Any]:
    """加载模板定义 JSON；只做最小结构校验，完整规则由 template_registry 负责。"""
    data = _read_json(path)
    for key in ("template_id", "version", "groups", "dimensions"):
        if key not in data:
            raise SourceMapError(f"模板定义缺少字段 {key}：{path}")
    if not isinstance(data["dimensions"], list) or not data["dimensions"]:
        raise SourceMapError(f"模板定义 dimensions 必须是非空数组：{path}")
    return data


def _as_int_list(raw: Any, dim_id: str) -> tuple[int, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise SourceMapError(f"{dim_id}.question_ids 必须是数组")
    result: list[int] = []
    seen: set[int] = set()
    for item in raw:
        if isinstance(item, bool) or not isinstance(item, int):
            raise SourceMapError(f"{dim_id}.question_ids 含非整数：{item!r}")
        if item <= 0:
            raise SourceMapError(f"{dim_id}.question_ids 含非法题号：{item}")
        if item in seen:
            raise SourceMapError(f"{dim_id}.question_ids 重复题号：{item}")
        seen.add(item)
        result.append(item)
    return tuple(result)


def _as_str_list(raw: Any, dim_id: str, field: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise SourceMapError(f"{dim_id}.{field} 必须是数组")
    result: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise SourceMapError(f"{dim_id}.{field} 含空值或非字符串：{item!r}")
        if item in result:
            raise SourceMapError(f"{dim_id}.{field} 重复：{item}")
        result.append(item)
    return tuple(result)


def _parse_dimension(raw: Any) -> DimensionSource:
    if not isinstance(raw, dict):
        raise SourceMapError(f"dimensions 元素必须是对象：{raw!r}")
    dim_id = raw.get("dimension_id")
    if not isinstance(dim_id, str) or not dim_id.strip():
        raise SourceMapError("dimension_id 缺失或为空")

    group_id = raw.get("group_id")
    if not isinstance(group_id, str) or not group_id.strip():
        raise SourceMapError(f"{dim_id}.group_id 缺失或为空")

    fill_mode = raw.get("fill_mode")
    if fill_mode not in FILL_MODES:
        raise SourceMapError(f"{dim_id}.fill_mode 非法：{fill_mode!r}，允许 {FILL_MODES}")

    scope = raw.get("scope", "questions")
    if scope not in SCOPES:
        raise SourceMapError(f"{dim_id}.scope 非法：{scope!r}，允许 {SCOPES}")

    question_ids = _as_int_list(raw.get("question_ids"), dim_id)
    tag_names = _as_str_list(raw.get("tag_names"), dim_id, "tag_names")
    metadata_fields = _as_str_list(raw.get("metadata_fields"), dim_id, "metadata_fields")

    derivation = raw.get("derivation")
    if derivation is not None and (not isinstance(derivation, str) or not derivation.strip()):
        raise SourceMapError(f"{dim_id}.derivation 必须是非空字符串或省略")

    reason = raw.get("no_source_reason")
    if reason is not None and (not isinstance(reason, str) or not reason.strip()):
        raise SourceMapError(f"{dim_id}.no_source_reason 必须是非空字符串或省略")

    note = raw.get("note")
    if note is not None and not isinstance(note, str):
        raise SourceMapError(f"{dim_id}.note 必须是字符串")

    source = DimensionSource(
        dimension_id=dim_id,
        group_id=group_id,
        fill_mode=fill_mode,
        scope=scope,
        question_ids=question_ids,
        tag_names=tag_names,
        metadata_fields=metadata_fields,
        derivation=derivation,
        no_source_reason=reason,
        note=note,
    )
    _validate_dimension_source(source)
    return source


def _validate_dimension_source(dim: DimensionSource) -> None:
    dim_id = dim.dimension_id

    if dim.scope == "interview":
        if dim.question_ids or dim.tag_names or dim.metadata_fields or dim.derivation:
            raise SourceMapError(f"{dim_id}：scope=interview 时不得声明题号/标签/元数据/派生")

    if dim.fill_mode == "none":
        if not dim.no_source_reason:
            raise SourceMapError(f"{dim_id}：fill_mode=none 必须写 no_source_reason")
        if dim.question_ids or dim.tag_names or dim.metadata_fields or dim.derivation:
            raise SourceMapError(f"{dim_id}：fill_mode=none 不得再声明来源，避免用模型兜底")
        return

    if dim.no_source_reason:
        raise SourceMapError(f"{dim_id}：只有 fill_mode=none 才能写 no_source_reason")

    if dim.fill_mode == "tag":
        if not dim.tag_names:
            raise SourceMapError(f"{dim_id}：fill_mode=tag 必须声明 tag_names")
    elif dim.fill_mode == "metadata":
        if not dim.metadata_fields:
            raise SourceMapError(f"{dim_id}：fill_mode=metadata 必须声明 metadata_fields")
        unknown = [f for f in dim.metadata_fields if f not in ALLOWED_METADATA_FIELDS]
        if unknown:
            raise SourceMapError(
                f"{dim_id}：metadata_fields 不在允许范围 {ALLOWED_METADATA_FIELDS}：{unknown}"
            )
    elif dim.fill_mode == "derived":
        if not dim.derivation:
            raise SourceMapError(f"{dim_id}：fill_mode=derived 必须声明 derivation")
    elif dim.fill_mode == "llm":
        if dim.scope == "questions" and not (dim.question_ids or dim.tag_names):
            raise SourceMapError(f"{dim_id}：fill_mode=llm 必须给出可引用的题号或标签")


def load_source_map(path: str | Path) -> SourceMap:
    """加载并做结构校验；不依赖模板与数据库。"""
    data = _read_json(path)
    for key in _REQUIRED_TOP_KEYS:
        if key not in data:
            raise SourceMapError(f"source-map 缺少字段 {key}：{path}")

    raw_dimensions = data["dimensions"]
    if not isinstance(raw_dimensions, list) or not raw_dimensions:
        raise SourceMapError("source-map dimensions 必须是非空数组")

    parsed: list[DimensionSource] = []
    seen: set[str] = set()
    for raw in raw_dimensions:
        dim = _parse_dimension(raw)
        if dim.dimension_id in seen:
            raise SourceMapError(f"维度重复：{dim.dimension_id}")
        seen.add(dim.dimension_id)
        parsed.append(dim)

    try:
        version = int(data["source_map_version"])
    except (TypeError, ValueError) as exc:
        raise SourceMapError("source_map_version 必须是整数") from exc

    return SourceMap(
        template_id=str(data["template_id"]),
        template_version=str(data["template_version"]),
        source_map_version=version,
        dimensions=tuple(parsed),
        evidence_basis=data.get("evidence_basis"),
    )


def validate_against_template(source_map: SourceMap, template: dict[str, Any]) -> None:
    """维度集合、顺序、分组必须与模板定义完全一致。"""
    if source_map.template_id != template.get("template_id"):
        raise SourceMapError(
            f"template_id 不一致：source-map={source_map.template_id}，模板={template.get('template_id')}"
        )
    if source_map.template_version != str(template.get("version")):
        raise SourceMapError(
            f"template_version 不一致：source-map={source_map.template_version}，"
            f"模板={template.get('version')}"
        )

    template_dims = template["dimensions"]
    template_ids = [d.get("id") for d in template_dims]
    map_ids = [d.dimension_id for d in source_map.dimensions]

    missing = [dim_id for dim_id in template_ids if dim_id not in set(map_ids)]
    extra = [dim_id for dim_id in map_ids if dim_id not in set(template_ids)]
    if missing or extra:
        raise SourceMapError(f"维度集合不一致：缺少 {missing}，多余 {extra}")
    if template_ids != map_ids:
        raise SourceMapError("维度顺序必须与模板定义一致")

    groups = {g.get("id") for g in template.get("groups", [])}
    for dim, tpl_dim in zip(source_map.dimensions, template_dims):
        if dim.group_id != tpl_dim.get("group"):
            raise SourceMapError(
                f"{dim.dimension_id} 分组不一致：source-map={dim.group_id}，模板={tpl_dim.get('group')}"
            )
        if dim.group_id not in groups:
            raise SourceMapError(f"{dim.dimension_id} 的分组 {dim.group_id} 不在模板 groups 中")


def validate_against_question_ids(source_map: SourceMap, known_ids: Iterable[int]) -> None:
    """所有题号必须存在于真实 question 表。"""
    known = {int(qid) for qid in known_ids}
    unknown = sorted(source_map.question_ids() - known)
    if unknown:
        raise SourceMapError(f"题号不存在于 user_insight.question：{unknown}")


def validate_against_tag_names(source_map: SourceMap, known_tags: Iterable[str]) -> None:
    """所有标签名必须存在于真实 tag 表。"""
    known = set(known_tags)
    unknown = sorted(source_map.tag_names() - known)
    if unknown:
        raise SourceMapError(f"标签不存在于 user_insight.tag：{unknown}")
