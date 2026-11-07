"""BCI-004 · 信息渠道呈现层归并。

- 只作用于展示/统计层（`value_json`），原始写法由生成器保留在 `source_ref`；
- 归并表在 `templates/info_channel_aliases.json`，逐条带原写法、目标渠道、次数与依据；
- 表内未收录的写法统一落「未归类」，不丢弃、不硬塞进某个渠道。

表内「未归类」与表外未知写法使用同一个标记，便于统计时单独观察。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from competitor_insight.server.evidence_gate import normalize_value

UNCATEGORIZED = "未归类"
ALIAS_PATH = Path(__file__).resolve().parents[1] / "templates/info_channel_aliases.json"


@lru_cache(maxsize=1)
def load_alias_map() -> dict[str, str]:
    payload = json.loads(ALIAS_PATH.read_text(encoding="utf-8"))
    return {entry["raw"]: entry["target"] for entry in payload["entries"]}


def normalize_channel(value: str, aliases: dict[str, str] | None = None) -> str:
    """单个写法 → 标准渠道；未知或空值 → 未归类。"""
    mapping = load_alias_map() if aliases is None else aliases
    cleaned = normalize_value(value)
    if not cleaned:
        return UNCATEGORIZED
    return mapping.get(cleaned, UNCATEGORIZED)


def normalize_channels(values: Iterable[str], dimension_id: str = "info_channels") -> list[str]:
    """按归并表把一组写法收敛为标准渠道，去重且保持首次出现顺序。"""
    items = [value for value in values if normalize_value(value)]
    if dimension_id != "info_channels":
        return list(dict.fromkeys(items))

    aliases = load_alias_map()
    merged: list[str] = []
    for value in items:
        target = normalize_channel(value, aliases)
        if target not in merged:
            merged.append(target)
    return merged
