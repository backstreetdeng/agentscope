"""洞察服务：圈层画像、满意度痛点、再购意愿、需求配置矩阵等专题洞察（只读）。"""
from __future__ import annotations

from typing import Any

import re
import statistics

import psycopg2
import psycopg2.extras

from customer_insight.quant_service import DIMENSIONS, _load_env
from customer_insight.segment_aliases import distinct_values, expand

# 产品维度（购车关注因素 Q3_13__N 与使用满意度 Q5_2__N 一一对应，N=1..16）
PRODUCT_DIMS: list[tuple[int, str]] = [
    (1, "安全性"), (2, "操控性"), (3, "动力性"), (4, "舒适性"),
    (5, "空间"), (6, "外观"), (7, "内饰"), (8, "质量"),
    (9, "使用费用"), (10, "购车价格"), (11, "品牌"), (12, "服务"),
    (13, "智能座舱"), (14, "智能驾驶"), (15, "纯电续航里程"), (16, "电池特性"),
]
SAT_PREFIX = "Q5_2__"   # 使用感受满意度打分（1-10 分）
ATT_PREFIX = "Q3_13__"  # 购车关注因素（勾选=1）——注意不是 Q3_23
CHOOSE_REASON_PREFIX = "Q3_23__"  # 选择最终购买车型的原因（战胜原因，独立指标，勿与购车关注混用）
SAT_LOW_THRESHOLD = 6   # 满意度 ≤6 分视为不满意/低分

# 需求×配置矩阵四象限的固定阈值（跨群体一致，不随单群体中位数漂移）。
# 来源：全样本 n=1380、16 个产品维度分布（2026-11-02 计算，见 temp/20261102-agentic-rag）。
#   - 关注度（勾选率）：>= 25% 视为「高关注」（约全样本中位数 24%，取整）。
#   - 低分率（打分<=6 比例）：>= 5.7% 视为「高不满」（全样本 P75）。
ATTENTION_THRESHOLD = 0.25
LOW_RATE_THRESHOLD = 0.057

# 四象限标签（业务解释框架）：
#   (高关注, 高不满) -> 优先诊断（改进候选）
#   (高关注, 低不满) -> 重点维持（优势候选）
#   (低关注, 高不满) -> 局部痛点（分群排查）
#   (低关注, 低不满) -> 保持监测
QUADRANT_LABELS: dict[tuple[bool, bool], str] = {
    (True, True): "优先诊断",
    (True, False): "重点维持",
    (False, True): "局部痛点",
    (False, False): "保持监测",
}
# 前端展示顺序（优先级从高到低）
QUADRANT_ORDER = {"优先诊断": 0, "重点维持": 1, "局部痛点": 2, "保持监测": 3}


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
        """满意度痛点：统计某群体在 16 个产品维度上的低分率（打分 ≤6）与均分，按低分率降序。"""
        if group_field not in DIMENSIONS:
            raise ValueError(f"不支持的维度：{group_field}")
        top = max(1, min(int(top), 16))
        conn = self._connect()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                items: list[dict[str, Any]] = []
                for idx, dim in PRODUCT_DIMS:
                    qid = f"{SAT_PREFIX}{idx}"
                    cur.execute(
                        f"SELECT "
                        "count(*) FILTER (WHERE (answers_text->>%s)::int <= %s) AS low_cnt, "
                        "avg((answers_text->>%s)::float) AS mean_score, "
                        "count(*) AS total "
                        "FROM user_insight.quant_sample "
                        f"WHERE {group_field} = %s AND answers_text->>%s ~ '^[0-9]+$'",
                        (qid, SAT_LOW_THRESHOLD, qid, group_value, qid),
                    )
                    row = cur.fetchone()
                    total = row["total"] or 0
                    if not total:
                        continue
                    low_cnt = row["low_cnt"] or 0
                    items.append({
                        "dimension": dim,
                        "question_id": qid,
                        "mean_score": round(float(row["mean_score"]), 2) if row["mean_score"] is not None else None,
                        "low_count": low_cnt,
                        "total": total,
                        "low_rate": round(low_cnt / total, 4),
                    })
                items.sort(key=lambda x: -x["low_rate"])
                return {
                    "group_field": group_field,
                    "group_label": DIMENSIONS[group_field],
                    "group_value": group_value,
                    "threshold": SAT_LOW_THRESHOLD,
                    "items": items[:top],
                }
        finally:
            conn.close()

    def repurchase_intent(self, group_field: str, group_value: str) -> dict[str, Any]:
        """再购意愿与品牌忠诚：统计某群体再次购车的时间、技术类型、意向品牌及是否同品牌。"""
        if group_field not in DIMENSIONS:
            raise ValueError(f"不支持的维度：{group_field}")
        questions = [
            ("Q6_3", "再购时间"),
            ("Q6_4", "再购技术类型"),
            ("Q6_5", "再购意向品牌"),
            ("Q2_7", "品牌忠诚（是否同品牌）"),
        ]
        conn = self._connect()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                items: list[dict[str, Any]] = []
                for qid, label in questions:
                    cur.execute(
                        "SELECT question_text FROM user_insight.quant_question WHERE question_id = %s",
                        (qid,),
                    )
                    qrow = cur.fetchone()
                    cur.execute(
                        f"SELECT answers_text->>%s AS val, count(*) AS cnt FROM user_insight.quant_sample "
                        f"WHERE {group_field} = %s AND answers_text ? %s GROUP BY val ORDER BY cnt DESC LIMIT 8",
                        (qid, group_value, qid),
                    )
                    dist = [{"value": r["val"], "count": r["cnt"]} for r in cur.fetchall()]
                    items.append({
                        "question_id": qid,
                        "label": label,
                        "question_text": qrow["question_text"] if qrow else label,
                        "sample_count": sum(i["count"] for i in dist),
                        "dist": dist,
                    })
                return {
                    "group_field": group_field,
                    "group_label": DIMENSIONS[group_field],
                    "group_value": group_value,
                    "items": items,
                }
        finally:
            conn.close()

    def demand_config_matrix(self, group_field: str, group_value: str) -> dict[str, Any]:
        """需求×配置匹配矩阵：16 个产品维度的购车关注度 × 使用满意度，划分四象限。"""
        if group_field not in DIMENSIONS:
            raise ValueError(f"不支持的维度：{group_field}")
        conn = self._connect()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # 圈层取值是具体枚举，没有「增换购」这类聚合值：先展开，避免精确匹配静默返回 0。
                available: list[str] = []
                values = [group_value]
                if group_field == "purchase_type":
                    available = distinct_values(conn, "user_insight.quant_sample", group_field)
                    values = expand([group_value], available)
                cur.execute(
                    f"SELECT count(*) AS total FROM user_insight.quant_sample WHERE {group_field} = ANY(%s)",
                    (values,),
                )
                total = cur.fetchone()["total"] or 0
                items: list[dict[str, Any]] = []
                for idx, dim in PRODUCT_DIMS:
                    att_qid = f"{ATT_PREFIX}{idx}"
                    sat_qid = f"{SAT_PREFIX}{idx}"
                    cur.execute(
                        f"SELECT "
                        "count(*) FILTER (WHERE answers_text ? %s) AS att_cnt, "
                        "count(*) FILTER (WHERE answers_text->>%s ~ '^[0-9]+$') AS sat_total, "
                        "count(*) FILTER (WHERE answers_text->>%s ~ '^[0-9]+$' AND (answers_text->>%s)::int <= %s) AS low_cnt, "
                        "avg(CASE WHEN answers_text->>%s ~ '^[0-9]+$' THEN (answers_text->>%s)::float END) AS mean_score "
                        "FROM user_insight.quant_sample "
                        f"WHERE {group_field} = ANY(%s)",
                        (att_qid, sat_qid, sat_qid, sat_qid, SAT_LOW_THRESHOLD, sat_qid, sat_qid, values),
                    )
                    row = cur.fetchone()
                    att_cnt = row["att_cnt"] or 0
                    sat_total = row["sat_total"] or 0
                    low_cnt = row["low_cnt"] or 0
                    items.append({
                        "dimension": dim,
                        "attention_rate": round(att_cnt / total, 4) if total else 0.0,
                        "attention_count": att_cnt,
                        "mean_score": round(float(row["mean_score"]), 2) if row["mean_score"] is not None else None,
                        "low_rate": round(low_cnt / sat_total, 4) if sat_total else 0.0,
                        "low_count": low_cnt,
                        "sat_total": sat_total,
                    })

                if total == 0:
                    return {
                        "group_field": group_field,
                        "group_label": DIMENSIONS[group_field],
                        "group_value": group_value,
                        "expanded_values": values,
                        "sample_count": 0,
                        "available_values": available[:8],
                        "hint": (
                            f"「{group_value}」在 {group_field} 中无匹配样本；"
                            f"库内实际取值为：{'；'.join(available[:8])}"
                        ) if available else "该维度无样本。",
                        "attention_threshold": ATTENTION_THRESHOLD,
                        "low_rate_threshold": LOW_RATE_THRESHOLD,
                        "items": [],
                    }

                for it in items:
                    hi_att = it["attention_rate"] >= ATTENTION_THRESHOLD
                    hi_low = it["low_rate"] >= LOW_RATE_THRESHOLD
                    it["quadrant"] = QUADRANT_LABELS[(hi_att, hi_low)]
                items.sort(key=lambda x: (QUADRANT_ORDER.get(x["quadrant"], 9), -x["attention_rate"]))

                return {
                    "group_field": group_field,
                    "group_label": DIMENSIONS[group_field],
                    "group_value": group_value,
                    "expanded_values": values,
                    "sample_count": total,
                    "attention_threshold": ATTENTION_THRESHOLD,
                    "low_rate_threshold": LOW_RATE_THRESHOLD,
                    "items": items,
                }
        finally:
            conn.close()

    def config_detail(self, group_field: str, group_value: str, top: int = 15) -> dict[str, Any]:
        """具体配置项下钻：Q3_13_1__NN 明细层（94 项）按勾选率排序，隶属 16 产品维度之下。"""
        if group_field not in DIMENSIONS:
            raise ValueError(f"不支持的维度：{group_field}")
        top = max(1, min(int(top), 50))
        conn = self._connect()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                available: list[str] = []
                values = [group_value]
                if group_field == "purchase_type":
                    available = distinct_values(conn, "user_insight.quant_sample", group_field)
                    values = expand([group_value], available)

                cur.execute(
                    f"SELECT count(*) AS n FROM user_insight.quant_sample WHERE {group_field} = ANY(%s)",
                    (values,),
                )
                total = cur.fetchone()["n"] or 0
                if total == 0:
                    return {
                        "group_field": group_field,
                        "group_label": DIMENSIONS[group_field],
                        "group_value": group_value,
                        "expanded_values": values,
                        "sample_count": 0,
                        "available_values": available[:8],
                        "hint": (
                            f"「{group_value}」在 {group_field} 中无匹配样本；"
                            f"库内实际取值为：{'；'.join(available[:8])}"
                        ) if available else "该维度无样本。",
                        "items": [],
                    }

                cur.execute(
                    "SELECT q.question_id, q.question_text, "
                    "count(*) FILTER (WHERE s.answers_text ? q.question_id) AS cnt "
                    "FROM user_insight.quant_question q CROSS JOIN user_insight.quant_sample s "
                    "WHERE q.question_id ~ '^Q3_13_1__[0-9]+$' AND s." + group_field + " = ANY(%s) "
                    "GROUP BY q.question_id, q.question_text "
                    "ORDER BY cnt DESC, q.question_id LIMIT %s",
                    (values, top),
                )
                items = [
                    {
                        "question_id": r["question_id"],
                        "config_item": re.sub(
                            rf"^{re.escape(r['question_id'])}\s*", "", r["question_text"] or ""
                        ).strip() or r["question_text"],
                        "attention_count": r["cnt"],
                        "attention_rate": round(r["cnt"] / total, 4),
                    }
                    for r in cur.fetchall()
                ]
                return {
                    "group_field": group_field,
                    "group_label": DIMENSIONS[group_field],
                    "group_value": group_value,
                    "expanded_values": values,
                    "sample_count": total,
                    "metric": "Q3_13_1__NN 购车关注具体配置项（勾选率=勾选人数/群体总样本）",
                    "items": items,
                }
        finally:
            conn.close()

    def competitor_compare(
        self,
        focus: str = "attention",
        min_samples: int = 20,
        top_models: int = 8,
        top_dims: int = 5,
    ) -> dict[str, Any]:
        """竞品横向对比：按车型分组，计算各产品维度的关注度/满意度低分率矩阵，识别差异最大的维度。"""
        focus = "attention" if focus != "satisfaction" else "satisfaction"
        min_samples = max(5, min(int(min_samples), 500))
        top_models = max(2, min(int(top_models), 20))
        top_dims = max(1, min(int(top_dims), 16))

        cols: list[str] = []
        if focus == "attention":
            for idx, _dim in PRODUCT_DIMS:
                qid = f"{ATT_PREFIX}{idx}"
                cols.append(f"count(*) FILTER (WHERE answers_text ? '{qid}') AS v{idx}")
        else:
            for idx, _dim in PRODUCT_DIMS:
                qid = f"{SAT_PREFIX}{idx}"
                cols.append(
                    f"count(*) FILTER (WHERE answers_text->>'{qid}' ~ '^[0-9]+$' "
                    f"AND (answers_text->>'{qid}')::int <= {SAT_LOW_THRESHOLD}) AS v{idx}"
                )

        conn = self._connect()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = (
                    "SELECT purchase_model, count(*) AS total, " + ", ".join(cols) +
                    " FROM user_insight.quant_sample WHERE purchase_model IS NOT NULL "
                    "GROUP BY purchase_model HAVING count(*) >= %s ORDER BY total DESC LIMIT %s"
                )
                cur.execute(sql, (min_samples, top_models))
                rows = cur.fetchall()

            dims = [dim for _idx, dim in PRODUCT_DIMS]
            models: list[dict[str, Any]] = []
            matrix_rows: list[dict[str, Any]] = []
            for r in rows:
                total = r["total"] or 0
                values = {dim: round(r[f"v{idx}"] / total, 4) if total else 0.0 for idx, dim in PRODUCT_DIMS}
                models.append({"model": r["purchase_model"], "total": total})
                matrix_rows.append({"model": r["purchase_model"], "total": total, "values": values})

            diff_dims: list[dict[str, Any]] = []
            for idx, dim in PRODUCT_DIMS:
                vals = [row["values"][dim] for row in matrix_rows]
                std = statistics.pstdev(vals) if len(vals) > 1 else 0.0
                diff_dims.append({"dimension": dim, "std": round(std, 4)})
            diff_dims.sort(key=lambda x: -x["std"])

            return {
                "focus": focus,
                "focus_label": "购车关注度" if focus == "attention" else "满意度低分率",
                "min_samples": min_samples,
                "models": models,
                "dims": dims,
                "rows": matrix_rows,
                "top_diff_dims": diff_dims[:top_dims],
            }
        finally:
            conn.close()
