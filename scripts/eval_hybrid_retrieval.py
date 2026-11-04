"""检索质量评测：dense-only vs dense+sparse 混合（RRF 融合）。

用 tag 语义标注作为 ground truth：每个 query 对应一个 content_group + tag_value 模式，
相关 answer = 该 tag 关联的 answer（interview_id 匹配 + question_id = ANY(mapped_question_ids)）。

指标：Recall@10 / Recall@30 / MRR（均基于召回阶段，不经过 rerank 与证据打包）。
用法：..\\Scripts\\python.exe -B scripts/eval_hybrid_retrieval.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from customer_insight.retrieval_service import (  # noqa: E402
    InterviewRetrievalService,
    _embed,
    _embed_sparse,
    _vec_str,
    _sparse_vec_str,
    RECALL_LIMIT,
    RRF_K,
)

EVAL_QUERIES = [
    {"q": "哪些用户提到续航焦虑？", "cg": "能源偏好", "pat": "%续航焦虑%"},
    {"q": "用户为什么觉得纯电使用成本低？", "cg": "能源偏好", "pat": "%使用成本低%"},
    {"q": "谁认为增程技术落后？", "cg": "能源偏好", "pat": "%增程技术落后%"},
    {"q": "为什么用户不认可插混或增程？", "cg": "能源偏好", "pat": "%不认可插混/增程%"},
    {"q": "用户主要上下班通勤用车吗？", "cg": "用车场景", "pat": "%上下班通勤%"},
    {"q": "哪些用户用车搭载子女？", "cg": "用车场景", "pat": "%子女%"},
    {"q": "用户长途出行距离有多远？", "cg": "用车场景", "pat": "%长途%"},
    {"q": "用户怎么看800V快充？", "cg": "产品需求", "pat": "%800V%"},
    {"q": "用户对纯电续航的需求是多少？", "cg": "产品需求", "pat": "%续航%"},
    {"q": "用户对自动驾驶的态度如何？", "cg": "产品需求", "pat": "%自动驾驶%"},
]

SELECT_COLS = "a.answer_id"
FROM_CLAUSE = (
    "FROM user_insight.answer a "
    "JOIN user_insight.interview i ON a.interview_id = i.interview_id"
)


def ground_truth(conn, cg: str, pat: str) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT a.answer_id FROM user_insight.answer a "
            "JOIN user_insight.tag t ON a.interview_id = t.interview_id "
            "AND a.question_id = ANY(t.mapped_question_ids) "
            "WHERE t.content_group = %s AND t.tag_value LIKE %s",
            (cg, pat),
        )
        return {r[0] for r in cur.fetchall()}


def recall(conn, question: str, use_sparse: bool) -> list[str]:
    """召回阶段：dense-only 或 dense+sparse RRF 融合，返回 answer_id 列表。"""
    query_vec = _vec_str(_embed([question])[0])
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {SELECT_COLS} {FROM_CLAUSE} WHERE a.embedding IS NOT NULL "
            "ORDER BY a.embedding <=> %s::vector LIMIT %s",
            (query_vec, RECALL_LIMIT),
        )
        dense_ids = [r[0] for r in cur.fetchall()]

    if not use_sparse:
        return dense_ids

    try:
        qsv = _sparse_vec_str(_embed_sparse([question])[0])
    except Exception:
        return dense_ids

    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {SELECT_COLS} {FROM_CLAUSE} WHERE a.sparse_embedding IS NOT NULL "
            "ORDER BY a.sparse_embedding <#> %s::sparsevec LIMIT %s",
            (qsv, RECALL_LIMIT),
        )
        sparse_ids = [r[0] for r in cur.fetchall()]

    rrf: dict[str, float] = {}
    for i, aid in enumerate(dense_ids):
        rrf[aid] = rrf.get(aid, 0.0) + 1.0 / (RRF_K + i + 1)
    for i, aid in enumerate(sparse_ids):
        rrf[aid] = rrf.get(aid, 0.0) + 1.0 / (RRF_K + i + 1)
    fused = sorted(set(dense_ids + sparse_ids), key=lambda x: rrf.get(x, 0.0), reverse=True)
    return fused[:RECALL_LIMIT]


def recall_at(hits: list[str], gt: set[str], k: int) -> float | None:
    if not gt:
        return None
    return len(set(hits[:k]) & gt) / len(gt)


def mrr(hits: list[str], gt: set[str]) -> float:
    for i, aid in enumerate(hits, start=1):
        if aid in gt:
            return 1.0 / i
    return 0.0


def _mean(xs: list[float | None]) -> float:
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else 0.0


def main() -> None:
    svc = InterviewRetrievalService()
    conn = svc._connect()
    try:
        header = (
            f"{'query':<26} {'gt':>4} {'R@10d':>7} {'R@10h':>7} "
            f"{'R@30d':>7} {'R@30h':>7} {'MRR_d':>7} {'MRR_h':>7}"
        )
        print(header)
        agg = {"d10": [], "h10": [], "d30": [], "h30": [], "dmrr": [], "hmrr": []}
        for item in EVAL_QUERIES:
            gt = ground_truth(conn, item["cg"], item["pat"])
            dh = recall(conn, item["q"], use_sparse=False)
            hh = recall(conn, item["q"], use_sparse=True)
            d10, h10 = recall_at(dh, gt, 10), recall_at(hh, gt, 10)
            d30, h30 = recall_at(dh, gt, 30), recall_at(hh, gt, 30)
            dm, hm = mrr(dh, gt), mrr(hh, gt)
            agg["d10"].append(d10)
            agg["h10"].append(h10)
            agg["d30"].append(d30)
            agg["h30"].append(h30)
            agg["dmrr"].append(dm)
            agg["hmrr"].append(hm)
            print(
                f"{item['q'][:12]:<26} {len(gt):>4} {d10:>7.3f} {h10:>7.3f} "
                f"{d30:>7.3f} {h30:>7.3f} {dm:>7.3f} {hm:>7.3f}"
            )
        print("-" * 78)
        print(
            f"{'平均':<26} {'':>4} {_mean(agg['d10']):>7.3f} {_mean(agg['h10']):>7.3f} "
            f"{_mean(agg['d30']):>7.3f} {_mean(agg['h30']):>7.3f} "
            f"{_mean(agg['dmrr']):>7.3f} {_mean(agg['hmrr']):>7.3f}"
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
