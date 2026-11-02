"""竞品对标矩阵交叉校验规则库（MKT-001 / S5）。

规则来源：skills/competitor-benchmarking/references/evidence-rules.md。
被 validate_matrix.py（skill 包验收器）与后续 agent 交付门禁复用。
本模块为纯函数规则，不连库；P0 硬参数对账（连库）在 S7 代表性任务验收时以
真实 miit 配置值执行，见 tools.miit_tools.MiitService。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import validate as _jsonschema_validate
from jsonschema.exceptions import ValidationError

_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "skills" / "competitor-benchmarking" / "assets" / "matrix-schema.json"

# 价格阶梯四级：禁止合并为单一"价格"维度。
PRICE_TIERS = ("指导价", "先享价", "限时价", "经销商价")
_SINGLE_PRICE_NAMES = {"价格", "售价", "终端价", "成交价", "起售价"}


def _schema() -> dict[str, Any]:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def _hard_dimensions(matrix: dict[str, Any]) -> set[str]:
    return {d["name"] for d in matrix.get("dimensions", []) if d.get("category") == "hard_spec"}


def validate_schema(matrix: dict[str, Any]) -> list[str]:
    """契约校验：assets/matrix-schema.json。"""
    try:
        _jsonschema_validate(matrix, _schema())
        return []
    except ValidationError as exc:
        return [f"schema 校验失败：{exc.message} @ {'/'.join(str(p) for p in exc.absolute_path)}"]


def validate_cells(matrix: dict[str, Any]) -> list[str]:
    """单元格完整性：receipt_id / as_of / source_tier / status；disputed 双边呈现。"""
    errors: list[str] = []
    for c in matrix.get("cells", []):
        model = c.get("model", "?")
        dim = c.get("dimension", "?")
        status = c.get("status")
        if status == "na":
            continue
        if not c.get("receipt_id"):
            errors.append(f"{dim}/{model}: 非 na 格缺少 receipt_id")
        if not c.get("as_of"):
            errors.append(f"{dim}/{model}: 缺少 as_of")
        if not c.get("source_tier"):
            errors.append(f"{dim}/{model}: 缺少 source_tier")
        if status == "disputed":
            note = c.get("note") or ""
            if not any(k in note for k in ("口径", "时效", "立场")):
                errors.append(f"{dim}/{model}: disputed 格 note 未标注冲突类型（口径/时效/立场）")
    return errors


def validate_p0_anchor(matrix: dict[str, Any], miit_dsn: str | None = None) -> list[str]:
    """硬参数 P0 锚定校验（声明层；连库对账 S7 执行）。

    规则：硬参数格非 insufficient 时 source_tier 必须为 P0 且带 receipt_id；
    insufficient 格必须注明"无申报记录"，不得用媒体值顶替。
    """
    errors: list[str] = []
    hard = _hard_dimensions(matrix)
    for c in matrix.get("cells", []):
        if c.get("dimension") not in hard:
            continue
        model = c.get("model", "?")
        dim = c.get("dimension", "?")
        if c.get("status") == "insufficient":
            if "无申报" not in (c.get("note") or ""):
                errors.append(f"{dim}/{model}: insufficient 但未注明无申报记录")
            continue
        if c.get("source_tier") != "P0":
            errors.append(f"{dim}/{model}: 硬参数必须以 P0（款型配置信息）为锚，当前 {c.get('source_tier')}")
        if not c.get("receipt_id"):
            errors.append(f"{dim}/{model}: 硬参数缺少 receipt_id")
    return errors


def validate_price_tiers(matrix: dict[str, Any]) -> list[str]:
    """价格阶梯：禁止单一"价格"维度，须分列 指导价/先享价/限时价/经销商价。"""
    errors: list[str] = []
    dims = [d["name"] for d in matrix.get("dimensions", [])]
    single = [d for d in dims if d in _SINGLE_PRICE_NAMES]
    if single:
        errors.append(f"价格未分列阶梯（出现单一维度 {sorted(single)}），应分列 {'/'.join(PRICE_TIERS)}")
    return errors


def validate_matrix(matrix: dict[str, Any], miit_dsn: str | None = None) -> list[str]:
    """聚合全部交叉校验规则，返回失败列表（空列表即通过）。"""
    failures: list[str] = []
    failures += validate_schema(matrix)
    failures += validate_cells(matrix)
    failures += validate_p0_anchor(matrix, miit_dsn)
    failures += validate_price_tiers(matrix)
    return failures
