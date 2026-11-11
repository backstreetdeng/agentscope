"""BCI-007 · 洞察档案跨人聚合（只读）。

口径（用户 2026-11-11 确认）：
- 只统计「当前有效」档案：同一访谈 + 同一模板 + 同一模板版本取最大 revision，且 status ∈ ready/partial；
- 必须按车型收口：用 `analysis_models.json` 的 `interview_models` 精确匹配 `user_insight.interview.vehicle_model`，
  不允许把全库 17 份档案塞进每一款车；
- 分母恒为「该车型已生成档案人数」，不是访谈总数，也不是原始标签覆盖人数；
- 只输出人数与原话，不输出比例（每车 3–5 人，不到 10 人不出比例）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable, Iterable

from competitor_insight.server.channel_normalizer import UNCATEGORIZED, normalize_channels

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_PATH = PROJECT_ROOT / "competitor_insight/templates/user_insight_archive_template.json"
DEFAULT_TEMPLATE_ID = "user_insight_archive"

_CHANNEL_DIMENSION = "info_channels"
_CONTENT_DIMENSION = "content_format_preference"
_MULTI_VALUED = {_CHANNEL_DIMENSION, _CONTENT_DIMENSION}

_EMPTY_TEXTS = {"", "无", "未提及", "不详", "未知", "null", "none", "n/a", "-"}


class ArchiveUnavailable(RuntimeError):
    """档案不可读或模板版本不一致。"""


def _clean(value: Any) -> str:
    text = str(value if value is not None else "").strip()
    return "" if text.casefold() in _EMPTY_TEXTS else text


def value_items(value_json: Any, value_text: str | None = None) -> list[str]:
    """把 value_json 摊平为字符串项：支持 list / dict / 标量，文本字段作为补充。"""
    items: list[str] = []
    if isinstance(value_json, list):
        for entry in value_json:
            if isinstance(entry, dict):
                for key in ("label", "name", "value", "text"):
                    if _clean(entry.get(key)):
                        items.append(_clean(entry[key]))
                        break
            else:
                cleaned = _clean(entry)
                if cleaned:
                    items.append(cleaned)
    elif isinstance(value_json, dict):
        for key in ("items", "values", "labels", "value", "text"):
            if key in value_json:
                items.extend(value_items(value_json[key]))
                break
        else:
            for entry in value_json.values():
                items.extend(value_items(entry))
    elif value_json is not None:
        cleaned = _clean(value_json)
        if cleaned:
            items.append(cleaned)
    text = _clean(value_text)
    if text and not items:
        parts = [part.strip() for part in re.split(r"[；;、]", text) if part.strip()]
        items.extend(parts)
    return list(dict.fromkeys(items))


class ArchiveAggregator:
    """只读聚合器；`connect` 与 `fetch` 可注入，便于单测脱离数据库。"""

    def __init__(
        self,
        connect: Callable[[], Any] | None = None,
        *,
        template_id: str = DEFAULT_TEMPLATE_ID,
        template_path: Path | None = None,
        fetch: Callable[[str, tuple], list[tuple]] | None = None,
    ) -> None:
        self.connect = connect
        self.template_id = template_id
        self.template_path = Path(template_path or TEMPLATE_PATH)
        self.fetch = fetch

    # ---------------------------------------------------------------- 基础信息

    def template(self) -> dict[str, Any]:
        try:
            return json.loads(self.template_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ArchiveUnavailable(f"档案模板不可读：{exc.__class__.__name__}") from exc

    def template_version(self) -> str:
        version = _clean(self.template().get("version"))
        if not version:
            raise ArchiveUnavailable("档案模板缺少 version，无法锁定报告口径")
        return version

    def _query(self, sql: str, params: tuple) -> list[tuple]:
        if self.fetch is not None:
            return self.fetch(sql, params)
        if self.connect is None:
            raise ArchiveUnavailable("未配置数据库连接")
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchall()
        finally:
            conn.close()

    # ---------------------------------------------------------------- 访谈范围

    def interviews(self, interview_models: Iterable[str]) -> list[dict[str, Any]]:
        """当前有效档案（按车型收口）；返回处置后仍为同一访谈多版本时只取最大 revision。"""
        names = [str(name) for name in interview_models if _clean(name)]
        if not names:
            return []
        version = self.template_version()
        sql = """
            select a.archive_id, a.interview_id, a.revision, a.template_version,
                   a.updated_at, i.respondent_code, i.city, i.vehicle_model
            from bci.archive a
            join user_insight.interview i on i.interview_id = a.interview_id
            where a.template_id = %s
              and a.template_version = %s
              and a.status in ('ready', 'partial')
              and i.vehicle_model = any(%s)
              and a.revision = (
                  select max(a2.revision) from bci.archive a2
                  where a2.interview_id = a.interview_id
                    and a2.template_id = a.template_id
                    and a2.template_version = a.template_version
              )
            order by i.respondent_code
        """
        rows = self._query(sql, (self.template_id, version, names))
        return [
            {
                "archive_id": int(row[0]),
                "interview_id": str(row[1]),
                "revision": int(row[2]),
                "template_version": str(row[3]),
                "updated_at": row[4].isoformat() if hasattr(row[4], "isoformat") else str(row[4] or ""),
                "respondent_code": str(row[5] or row[1]),
                "city": str(row[6] or ""),
                "vehicle_model": str(row[7] or ""),
            }
            for row in rows
        ]

    def interview_total(self, interview_models: Iterable[str]) -> int:
        names = [str(name) for name in interview_models if _clean(name)]
        if not names:
            return 0
        rows = self._query(
            "select count(*) from user_insight.interview where vehicle_model = any(%s)",
            (names,),
        )
        return int(rows[0][0]) if rows else 0

    # ---------------------------------------------------------------- 聚合主体

    def aggregate(self, interview_models: Iterable[str]) -> dict[str, Any]:
        interviews = self.interviews(interview_models)
        if not interviews:
            return {
                "template_id": self.template_id,
                "template_version": self.template_version(),
                "interviews": [],
                "dimensions": {},
                "values": {},
                "coverage": {"archived": 0, "interview_total": self.interview_total(interview_models)},
            }

        archive_ids = [item["archive_id"] for item in interviews]
        rows = self._query(
            """
            select archive_id, dimension_id, value_text, value_json, no_data_reason, review_status
            from bci.archive_field
            where archive_id = any(%s)
            """,
            (archive_ids,),
        )
        by_archive = {item["archive_id"]: item for item in interviews}
        values: dict[str, list[dict[str, Any]]] = {}
        stats: dict[str, dict[str, int]] = {}
        for archive_id, dimension_id, value_text, value_json, no_data_reason, review_status in rows:
            owner = by_archive[int(archive_id)]
            items = value_items(value_json, value_text)
            stats.setdefault(dimension_id, {"total": len(interviews), "filled": 0, "suspects": 0})
            if items:
                stats[dimension_id]["filled"] += 1
            if review_status == "suspect":
                stats[dimension_id]["suspects"] += 1
            values.setdefault(dimension_id, []).append(
                {
                    "interview_id": owner["interview_id"],
                    "respondent_code": owner["respondent_code"],
                    "vehicle_model": owner["vehicle_model"],
                    "text": _clean(value_text)[:300],
                    "items": [item[:120] for item in items][:8],
                    "suspect": review_status == "suspect",
                    "no_data_reason": _clean(no_data_reason),
                }
            )

        return {
            "template_id": self.template_id,
            "template_version": self.template_version(),
            "interviews": interviews,
            "dimensions": stats,
            "values": values,
            "coverage": {"archived": len(interviews), "interview_total": self.interview_total(interview_models)},
        }

    # ---------------------------------------------------------------- 渠道计数

    @staticmethod
    def channel_counts(entries: Iterable[dict[str, Any]]) -> dict[str, int]:
        """渠道提及人数：一个人在同一渠道出现多次只算 1 人。"""
        counter: dict[str, int] = {}
        for entry in entries:
            merged = normalize_channels(entry.get("items") or [], _CHANNEL_DIMENSION)
            for channel in merged:
                counter[channel] = counter.get(channel, 0) + 1
        return counter

    @staticmethod
    def content_counts(entries: Iterable[dict[str, Any]]) -> dict[str, int]:
        counter: dict[str, int] = {}
        for entry in entries:
            for item in dict.fromkeys(entry.get("items") or []):
                counter[item] = counter.get(item, 0) + 1
        return counter


__all__ = ["ArchiveAggregator", "ArchiveUnavailable", "UNCATEGORIZED", "value_items"]
