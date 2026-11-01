"""洞察服务：圈层画像、满意度痛点、再购意愿、需求配置矩阵等专题洞察（只读）。"""
from __future__ import annotations

from typing import Any

import psycopg2
import psycopg2.extras

from customer_insight.quant_service import DIMENSIONS, _load_env


class InsightService:
    """复用 quant_sample 做专题洞察，只读。"""

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

    def _dist(self, cur: Any, field: str, where: str, params: tuple, top: int = 8) -> list[dict[str, Any]]:
        cur.execute(
            f"SELECT {field} AS v, count(*) AS cnt FROM user_insight.quant_sample "
            f"WHERE {where} GROUP BY v ORDER BY cnt DESC LIMIT %s",
            params + (top,),
        )
        return [{"value": r["v"], "count": r["cnt"]} for r in cur.fetchall()]

    def segment_clusters(self, min_samples: int = 30) -> dict[str, Any]:
        """圈层画像聚类：按购车类型主维度，输出每个圈层的画像特征。"""
        min_samples = max(10, min(int(min_samples), 500))
        conn = self._connect()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT purchase_type, count(*) AS cnt FROM user_insight.quant_sample "
                    "WHERE purchase_type IS NOT NULL GROUP BY purchase_type "
                    "HAVING count(*) >= %s ORDER BY cnt DESC",
                    (min_samples,),
                )
                seg_rows = cur.fetchall()

                segments = []
                for s in seg_rows:
                    pt = s["purchase_type"]
                    where = "purchase_type = %s AND price_band IS NOT NULL"
                    price_bands = self._dist(cur, "price_band", where, (pt,))
                    age_bands = self._dist(cur, "age_band", "purchase_type = %s AND age_band IS NOT NULL", (pt,))
                    genders = self._dist(cur, "gender", "purchase_type = %s AND gender IS NOT NULL", (pt,))
                    models = self._dist(cur, "purchase_model", "purchase_type = %s AND purchase_model IS NOT NULL", (pt,), 10)
                    segments.append({
                        "name": pt,
                        "sample_count": s["cnt"],
                        "price_bands": price_bands,
                        "age_bands": age_bands,
                        "genders": genders,
                        "top_models": models,
                    })
                return {"segments": segments, "total": sum(x["sample_count"] for x in segments)}
        finally:
            conn.close()

    def satisfaction_painpoints(self, group_field: str, group_value: str, top: int = 10) -> dict[str, Any]:
        """满意度痛点：统计某群体「最不满意」的分布（Q5_2 满意度逐条打分）。"""
        if group_field not in DIMENSIONS:
            raise ValueError(f"不支持的维度：{group_field}")
        conn = self._connect()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # 满意度题前缀 Q5_2（使用感受逐条打分），取打分低的条目
                cur.execute(
                    f"SELECT question_id, question_text FROM user_insight.quant_question "
                    "WHERE question_id LIKE 'Q5_2%%' AND question_text NOT LIKE '%【%' ORDER BY question_id LIMIT 30",
                )
                qs = cur.fetchall()
                items = []
                for q in qs:
                    cur.execute(
                        f"SELECT answers_text->>%s AS val, count(*) AS cnt FROM user_insight.quant_sample "
                        f"WHERE {group_field} = %s AND answers_text ? %s GROUP BY val ORDER BY cnt DESC LIMIT 5",
                        (q["question_id"], group_value, q["question_id"]),
                    )
                    dist = [{"value": r["val"], "count": r["cnt"]} for r in cur.fetchall()]
                    items.append({"question_id": q["question_id"], "question_text": q["question_text"], "dist": dist})
                return {
                    "group_field": group_field,
                    "group_value": group_value,
                    "items": items,
                }
        finally:
            conn.close()

    def repurchase_intent(self, group_field: str, group_value: str) -> dict[str, Any]:
        """再购意愿：统计某群体再次购车的品牌/燃料类型意向。"""
        if group_field not in DIMENSIONS:
            raise ValueError(f"不支持的维度：{group_field}")
        conn = self._connect()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                result: dict[str, Any] = {"group_field": group_field, "group_value": group_value}
                for qid, label in (("Q6_2", "再购燃料类型"), ("Q6_3", "再购品牌")):
                    cur.execute(
                        "SELECT question_text FROM user_insight.quant_question WHERE question_id LIKE %s LIMIT 1",
                        (qid + "%",),
                    )
                    qrow = cur.fetchone()
                    if not qrow:
                        result[label] = None
                        continue
                    cur.execute(
                        f"SELECT answers_text->>%s AS val, count(*) AS cnt FROM user_insight.quant_sample "
                        f"WHERE {group_field} = %s AND answers_text ? %s GROUP BY val ORDER BY cnt DESC LIMIT 8",
                        (qrow["question_id"], group_value, qrow["question_id"]),
                    )
                    result[label] = {
                        "question_text": qrow["question_text"],
                        "dist": [{"value": r["val"], "count": r["cnt"]} for r in cur.fetchall()],
                    }
                return result
        finally:
            conn.close()
