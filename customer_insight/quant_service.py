"""定量问卷统计服务：按群体维度统计问卷字段分布（只读）。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 白名单维度：切分维度 -> 显示名
DIMENSIONS: dict[str, str] = {
    "purchase_type": "购车类型",
    "price_band": "价格段",
    "age_band": "年龄段",
    "gender": "性别",
    "city": "城市",
    "purchase_model": "车型",
}


def _load_env() -> dict[str, str]:
    cfg: dict[str, str] = {}
    for f in (PROJECT_ROOT / ".env", PROJECT_ROOT / ".env.new-car"):
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip().strip('"').strip("'")
    return cfg


class QuantStatService:
    """定量统计，只读 user_insight.quant_sample / quant_question。"""

    def __init__(self) -> None:
        self._cfg = _load_env()

    def _connect(self) -> psycopg2.extensions.connection:
        return psycopg2.connect(
            host=self._cfg.get("NEW_CAR_PG_HOST", "192.168.3.146"),
            port=int(self._cfg.get("NEW_CAR_PG_PORT", "5432")),
            dbname=self._cfg.get("NEW_CAR_PG_DATABASE", "vectordb"),
            user=self._cfg.get("USER_INSIGHT_LOADER_USER", ""),
            password=self._cfg.get("USER_INSIGHT_LOADER_PASSWORD", ""),
            connect_timeout=8,
        )

    def dimensions(self) -> list[dict[str, str]]:
        return [{"key": k, "label": v} for k, v in DIMENSIONS.items()]

    def list_questions(self, keyword: str = "", limit: int = 2000) -> list[dict[str, Any]]:
        keyword = (keyword or "").strip()
        conn = self._connect()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if keyword:
                    cur.execute(
                        "SELECT question_id, question_text FROM user_insight.quant_question "
                        "WHERE question_text ILIKE %s ORDER BY question_id LIMIT %s",
                        (f"%{keyword}%", limit),
                    )
                else:
                    cur.execute(
                        "SELECT question_id, question_text FROM user_insight.quant_question "
                        "ORDER BY question_id LIMIT %s",
                        (limit,),
                    )
                return cur.fetchall()
        finally:
            conn.close()

    def stat(self, question_id: str, group_by: str, top: int = 20) -> dict[str, Any]:
        question_id = (question_id or "").strip()
        if not question_id:
            raise ValueError("题目编号不能为空。")
        if group_by not in DIMENSIONS:
            raise ValueError(f"不支持的切分维度：{group_by}")
        top = max(1, min(int(top), 100))

        conn = self._connect()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT question_text FROM user_insight.quant_question WHERE question_id = %s", (question_id,))
                qrow = cur.fetchone()
                if qrow is None:
                    raise ValueError(f"题目不存在：{question_id}")
                question_text = qrow["question_text"]

                # 分母：该群体全部样本，不受“是否作答该题”影响（勾选题必须用这个分母）
                cur.execute(
                    f"SELECT {group_by} AS grp, count(*) AS total "
                    "FROM user_insight.quant_sample "
                    f"WHERE {group_by} IS NOT NULL GROUP BY grp"
                )
                group_totals = {str(r["grp"]): r["total"] for r in cur.fetchall()}

                cur.execute(
                    f"SELECT {group_by} AS grp, answers_text->>%s AS val, count(*) AS cnt "
                    "FROM user_insight.quant_sample "
                    f"WHERE {group_by} IS NOT NULL AND answers_text ? %s "
                    "GROUP BY grp, val ORDER BY cnt DESC LIMIT %s",
                    (question_id, question_id, top * 30),
                )
                rows = cur.fetchall()

            # 分组聚合
            by_group: dict[str, list[dict[str, Any]]] = {}
            total = 0
            for r in rows:
                g = str(r["grp"]) if r["grp"] is not None else "(空)"
                by_group.setdefault(g, [])
                by_group[g].append({"value": r["val"], "count": r["cnt"]})
                total += r["cnt"]

            # 勾选题（如 Q3_23 购车关注因素）：取值只有 1，占比应按群体总样本算
            multi_select = bool(rows) and all(str(r["val"]) in ("1", "1.0") for r in rows)

            groups = []
            for g, items in by_group.items():
                g_total = group_totals.get(g, sum(i["count"] for i in items))
                for i in items:
                    i["coverage"] = round(i["count"] / g_total * 100, 1) if g_total else 0.0
                groups.append({
                    "group": g,
                    "total": g_total,
                    "answered": sum(i["count"] for i in items),
                    "items": sorted(items, key=lambda x: -x["count"])[:top],
                })
            groups.sort(key=lambda x: -x["answered"])

            return {
                "question_id": question_id,
                "question_text": question_text,
                "group_by": group_by,
                "group_by_label": DIMENSIONS[group_by],
                "sample_count": total,
                "multi_select": multi_select,
                "groups": groups[:top],
            }
        finally:
            conn.close()

    def stat_in_group(self, question_id: str, filter_field: str, filter_value: str, top: int = 10) -> dict[str, Any]:
        """筛选 filter_field=filter_value 的样本后，统计 question_id 的分布（不做维度切分）。"""
        question_id = (question_id or "").strip()
        if not question_id:
            raise ValueError("题目编号不能为空。")
        if filter_field not in DIMENSIONS:
            raise ValueError(f"不支持的筛选维度：{filter_field}")
        top = max(1, min(int(top), 50))

        conn = self._connect()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT question_text FROM user_insight.quant_question WHERE question_id = %s", (question_id,))
                qrow = cur.fetchone()
                if qrow is None:
                    raise ValueError(f"题目不存在：{question_id}")
                question_text = qrow["question_text"]

                cur.execute(
                    f"SELECT answers_text->>%s AS val, count(*) AS cnt "
                    "FROM user_insight.quant_sample "
                    f"WHERE {filter_field} = %s AND answers_text ? %s "
                    "GROUP BY val ORDER BY cnt DESC LIMIT %s",
                    (question_id, filter_value, question_id, top),
                )
                rows = cur.fetchall()

            items = [{"value": r["val"], "count": r["cnt"]} for r in rows]
            total = sum(i["count"] for i in items)
            return {
                "question_id": question_id,
                "question_text": question_text,
                "filter_field": filter_field,
                "filter_value": filter_value,
                "sample_count": total,
                "items": items,
            }
        finally:
            conn.close()
