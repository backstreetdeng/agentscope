"""访谈证据检索服务：白名单过滤 → 向量召回 → Reranker 重排 → 证据打包。

只读查询 user_insight schema，不写库。依赖：
- PostgreSQL/pgvector（向量余弦召回）
- Ollama bge-m3（query embedding）
- Reranker FastAPI（http://192.168.3.146:8082/rerank）
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OLLAMA_EMBED_URL = "http://192.168.3.146:11434/api/embed"
EMBED_MODEL = "bge-m3:latest"
RERANK_URL = "http://192.168.3.146:8082/rerank"

# 白名单过滤字段，禁止任意 SQL/列名/正则/路径。
ALLOWED_FILTERS = {
    "city", "vehicle_model", "purchase_type", "question_ids",
    "tag_names", "tag_values", "respondent_codes",
}

DEFAULT_TOP_K = 6
MAX_TOP_K = 8
RECALL_LIMIT = 30
MAX_EVIDENCE_PER_ANSWER = 1
MAX_EVIDENCE_PER_RESPONDENT = 3


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


def _embed(texts: list[str]) -> list[list[float]]:
    req = urllib.request.Request(
        OLLAMA_EMBED_URL,
        data=json.dumps({"model": EMBED_MODEL, "input": texts}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read().decode())
    return [e for e in data["embeddings"]]


def _rerank(query: str, documents: list[str], top_k: int) -> list[dict[str, Any]]:
    req = urllib.request.Request(
        RERANK_URL,
        data=json.dumps({"query": query, "documents": documents, "top_k": top_k}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=12) as r:
        data = json.loads(r.read().decode())
    return data.get("results", [])


def _vec_str(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.8g}" for x in vec) + "]"


def _format_seconds(sec: float | None) -> str:
    if sec is None:
        return ""
    total = float(sec)
    minutes = int(total // 60)
    seconds = total - minutes * 60
    return f"{minutes}:{seconds:04.1f}"


def _time_label(row: dict[str, Any]) -> str:
    if row.get("time_precision") == "second" and row.get("start_sec") is not None:
        start = _format_seconds(row.get("start_sec"))
        end = _format_seconds(row.get("end_sec"))
        return f"{start}–{end}" if end else start
    loc = row.get("source_locator") or {}
    if isinstance(loc, str):
        try:
            loc = json.loads(loc)
        except Exception:
            loc = {}
    if isinstance(loc, dict):
        for key in ("range", "paragraph", "time_range", "locator"):
            if loc.get(key):
                return str(loc[key])
    return ""


class InterviewRetrievalService:
    """确定性访谈证据检索，不依赖模型工具选择的随机性。"""

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

    def _validate_filters(self, filters: dict[str, Any] | None) -> tuple[dict[str, Any], list[str]]:
        warnings: list[str] = []
        clean: dict[str, Any] = {}
        if not filters:
            return clean, warnings
        if not isinstance(filters, dict):
            raise ValueError("filters 必须是对象。")
        for key, value in filters.items():
            if key not in ALLOWED_FILTERS:
                warnings.append(f"忽略不支持的过滤字段：{key}")
                continue
            if key in {"question_ids"}:
                values = value if isinstance(value, list) else [value]
                clean[key] = [int(v) for v in values if str(v).strip().lstrip("-").isdigit()]
            else:
                values = value if isinstance(value, list) else [value]
                clean[key] = [str(v).strip() for v in values if str(v).strip()]
        return clean, warnings

    def search(
        self,
        question: str,
        filters: dict[str, Any] | None = None,
        top_k: int = DEFAULT_TOP_K,
    ) -> dict[str, Any]:
        question = (question or "").strip()
        if not question:
            raise ValueError("问题不能为空。")
        top_k = max(1, min(int(top_k), MAX_TOP_K))
        clean_filters, warnings = self._validate_filters(filters)

        # 1. query embedding
        query_vec = _vec_str(_embed([question])[0])

        # 2. 向量召回（结构化过滤后余弦 top N）
        conn = self._connect()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                conds: list[str] = ["a.embedding IS NOT NULL"]
                params: list[Any] = []
                if clean_filters.get("city"):
                    conds.append("i.city = ANY(%s)")
                    params.append(clean_filters["city"])
                if clean_filters.get("vehicle_model"):
                    conds.append("i.vehicle_model = ANY(%s)")
                    params.append(clean_filters["vehicle_model"])
                if clean_filters.get("purchase_type"):
                    conds.append("i.purchase_type = ANY(%s)")
                    params.append(clean_filters["purchase_type"])
                if clean_filters.get("respondent_codes"):
                    conds.append("i.respondent_code = ANY(%s)")
                    params.append(clean_filters["respondent_codes"])
                if clean_filters.get("question_ids"):
                    conds.append("a.question_id = ANY(%s)")
                    params.append(clean_filters["question_ids"])
                if clean_filters.get("tag_names") or clean_filters.get("tag_values"):
                    tag_conds: list[str] = []
                    tag_params: list[Any] = []
                    if clean_filters.get("tag_names"):
                        tag_conds.append("t.tag_name = ANY(%s)")
                        tag_params.append(clean_filters["tag_names"])
                    if clean_filters.get("tag_values"):
                        tag_conds.append("t.tag_value = ANY(%s)")
                        tag_params.append(clean_filters["tag_values"])
                    conds.append(
                        "EXISTS (SELECT 1 FROM user_insight.tag t "
                        "WHERE t.interview_id = a.interview_id AND " + " AND ".join(tag_conds) + ")"
                    )
                    params.extend(tag_params)

                where = " AND ".join(conds)
                sql = (
                    "SELECT a.answer_id, a.interview_id, a.question_id, a.question_text, "
                    "a.answer_text, a.confidence, a.source_format, a.source_uri, "
                    "i.respondent_code, i.city, i.vehicle_model, i.purchase_type, "
                    "1 - (a.embedding <=> %s::vector) AS similarity "
                    "FROM user_insight.answer a "
                    "JOIN user_insight.interview i ON a.interview_id = i.interview_id "
                    f"WHERE {where} "
                    "ORDER BY a.embedding <=> %s::vector "
                    "LIMIT %s"
                )
                cur.execute(sql, [query_vec] + params + [query_vec, RECALL_LIMIT])
                candidates = cur.fetchall()
        finally:
            conn.close()

        if not candidates:
            return {"evidence": [], "retrieval": {"matched_by": "none", "recalled": 0}, "warnings": warnings}

        # 3. Reranker 重排
        candidate_texts = [c["answer_text"] for c in candidates]
        rerank_degraded = False
        try:
            ranked = _rerank(question, candidate_texts, top_k=top_k)
        except Exception as exc:  # reranker 故障降级为向量顺序
            ranked = [{"index": i, "score": 0.0} for i in range(min(top_k, len(candidates)))]
            rerank_degraded = True
            warnings.append(f"重排服务降级：{type(exc).__name__}")

        selected = [candidates[r["index"]] for r in ranked if r["index"] < len(candidates)]

        # 4. 取证据明细
        evidence = self._load_evidence(selected)

        # 5. 同受访者限量 + 截断到 top_k（最多 8 条证据）
        evidence = self._cap_per_respondent(evidence, MAX_EVIDENCE_PER_RESPONDENT)[:top_k]

        # 6. 编号 E1..En 并附检索元数据
        score_by_answer = {
            candidates[r["index"]]["answer_id"]: round(float(r["score"]), 4)
            for r in ranked if r["index"] < len(candidates)
        }
        for idx, ev in enumerate(evidence, start=1):
            answer_ref = ev.pop("answer_ref", "")
            ev["evidence_id"] = f"E{idx}"
            ev["retrieval"] = {
                "rank": idx,
                "score": score_by_answer.get(answer_ref, 0.0),
                "rerank_score": score_by_answer.get(answer_ref, 0.0),
                "matched_by": "vector+rerank" if not rerank_degraded else "vector",
            }

        retrieval = {
            "matched_by": "vector+rerank" if not rerank_degraded else "vector",
            "recalled": len(candidates),
            "reranked": len(selected),
            "returned": len(evidence),
            "reranker_degraded": rerank_degraded,
        }
        return {"evidence": evidence, "retrieval": retrieval, "warnings": warnings}

    def _load_evidence(self, selected: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not selected:
            return []
        answer_ids = [c["answer_id"] for c in selected]
        conn = self._connect()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT e.evidence_id, e.answer_id, e.interview_id, e.question_id, "
                    "e.quote_text, e.speaker_label, e.start_sec, e.end_sec, e.time_precision, "
                    "e.block_index, e.segment_index, e.source_locator, e.checksum, "
                    "a.question_text, a.confidence, a.source_format, a.source_uri, "
                    "i.respondent_code, i.city, i.vehicle_model, i.purchase_type, i.source_version "
                    "FROM user_insight.evidence e "
                    "JOIN user_insight.answer a ON e.answer_id = a.answer_id "
                    "JOIN user_insight.interview i ON e.interview_id = i.interview_id "
                    "WHERE e.answer_id = ANY(%s) "
                    "ORDER BY e.answer_id, (e.time_precision = 'second') DESC, "
                    "e.start_sec ASC NULLS LAST, e.block_index, e.segment_index",
                    (answer_ids,),
                )
                rows = cur.fetchall()
        finally:
            conn.close()

        # 按 answer 分组，每组取至多 MAX_EVIDENCE_PER_ANSWER 条
        by_answer: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            by_answer.setdefault(row["answer_id"], []).append(row)

        selected_by_id = {c["answer_id"]: c for c in selected}
        evidence: list[dict[str, Any]] = []
        for answer_id in answer_ids:
            for row in by_answer.get(answer_id, [])[:MAX_EVIDENCE_PER_ANSWER]:
                loc = row.get("source_locator") or {}
                if isinstance(loc, str):
                    try:
                        loc = json.loads(loc)
                    except Exception:
                        loc = {}
                evidence.append({
                    "answer_ref": answer_id,
                    "db_evidence_id": row["evidence_id"],
                    "respondent_code": row["respondent_code"],
                    "city": row["city"],
                    "vehicle_model": row["vehicle_model"],
                    "purchase_type": row["purchase_type"],
                    "question_id": row["question_id"],
                    "question_text": row["question_text"],
                    "quote": row["quote_text"],
                    "speaker": row["speaker_label"],
                    "start_sec": float(row["start_sec"]) if row["start_sec"] is not None else None,
                    "end_sec": float(row["end_sec"]) if row["end_sec"] is not None else None,
                    "time_label": _time_label(row),
                    "time_precision": row["time_precision"],
                    "confidence": row["confidence"],
                    "source": {
                        "source_format": row["source_format"],
                        "source_version": row["source_version"],
                        "document_id": f"{row['respondent_code']}-Q{row['question_id']:03d}",
                        "checksum": row["checksum"],
                    },
                })
        return evidence

    @staticmethod
    def _cap_per_respondent(evidence: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        out: list[dict[str, Any]] = []
        for ev in evidence:
            code = ev["respondent_code"]
            if counts.get(code, 0) >= limit:
                continue
            counts[code] = counts.get(code, 0) + 1
            out.append(ev)
        return out
