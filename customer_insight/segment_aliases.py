"""圈层聚合词 → 库内真实枚举值展开。

量化表（quant_sample）与访谈表（interview）的 purchase_type 都是具体枚举：
量化是长字符串（「换购，本人名下上一辆车卖掉了…」），访谈是短标签（「换购」）。
两表都没有「增换购」这种聚合值，精确匹配会静默返回 0 条。展开逻辑集中在此，供各服务共用。
"""
from __future__ import annotations

import time
from typing import Any, Iterable

# 聚合词 → 需要与真实枚举值做包含匹配的关键词
ALIAS_KEYWORDS: dict[str, tuple[str, ...]] = {
    "增换购": ("换购", "增购"),
    "再购": ("换购", "增购"),
    "复购": ("换购", "增购"),
    "非首购": ("换购", "增购"),
}

_CACHE: dict[tuple[str, str], tuple[float, list[str]]] = {}
_TTL_SECONDS = 300


def clear_cache() -> None:
    """清空枚举值缓存（测试或数据重导后使用）。"""
    _CACHE.clear()


def distinct_values(conn: Any, table: str, field: str) -> list[str]:
    """读取某字段在库里的真实取值，进程内缓存 5 分钟。"""
    key = (table, field)
    now = time.monotonic()
    cached = _CACHE.get(key)
    if cached and now - cached[0] < _TTL_SECONDS:
        return cached[1]
    with conn.cursor() as cur:
        cur.execute(f"SELECT DISTINCT {field} FROM {table} WHERE {field} IS NOT NULL ORDER BY 1")
        values = [str(row[0]) for row in cur.fetchall() if row[0] is not None]
    _CACHE[key] = (now, values)
    return values


def expand(values: Iterable[str], available: Iterable[str]) -> list[str]:
    """聚合词/简写展开为 available 中真实存在的枚举值；无法匹配时保留原值。"""
    available = list(available)
    out: list[str] = []
    for raw in values:
        value = (raw or "").strip()
        if not value:
            continue
        if value in available:
            candidates = [value]
        else:
            keywords = ALIAS_KEYWORDS.get(value, (value,))
            candidates = [item for item in available if any(k in item for k in keywords)]
        for candidate in candidates or [value]:
            if candidate not in out:
                out.append(candidate)
    return out
