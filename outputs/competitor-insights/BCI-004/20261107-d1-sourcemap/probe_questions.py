"""只读探查：导出 85 个题目的编号/题干，以及 85 个标签与题号的映射关系。

用途：为 BCI-004 的 source-map.json 提供真实题号依据，避免手写题号。
只读：仅 SELECT user_insight.question / user_insight.tag。
输出：questions.tsv、tags.tsv、probe.log（与本脚本同目录）。
"""

from __future__ import annotations

import sys
from pathlib import Path

import psycopg2

PROJECT_ROOT = Path(__file__).resolve().parents[4]
OUT_DIR = Path(__file__).resolve().parent


def load_env() -> dict[str, str]:
    cfg: dict[str, str] = {}
    for name in (".env", ".env.new-car"):
        path = PROJECT_ROOT / name
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            cfg[key.strip()] = value.strip().strip('"').strip("'")
    return cfg


def main() -> int:
    cfg = load_env()
    conn = psycopg2.connect(
        host=cfg.get("NEW_CAR_PG_HOST", "192.168.3.146"),
        port=int(cfg.get("NEW_CAR_PG_PORT", "5432")),
        dbname=cfg.get("NEW_CAR_PG_DATABASE", "vectordb"),
        user=cfg.get("USER_INSIGHT_LOADER_USER", ""),
        password=cfg.get("USER_INSIGHT_LOADER_PASSWORD", ""),
        connect_timeout=10,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT question_id, question_text FROM user_insight.question ORDER BY question_id"
            )
            questions = cur.fetchall()

            cur.execute(
                "SELECT DISTINCT t.tag_name, q.qid "
                "FROM user_insight.tag t, unnest(t.mapped_question_ids) AS q(qid) "
                "ORDER BY t.tag_name, q.qid"
            )
            tag_q = cur.fetchall()

            cur.execute(
                "SELECT tag_name, count(*) FROM user_insight.tag GROUP BY tag_name ORDER BY tag_name"
            )
            tag_counts = cur.fetchall()
    finally:
        conn.close()

    (OUT_DIR / "questions.tsv").write_text(
        "question_id\tquestion_text\n"
        + "".join(f"{qid}\t{(text or '').replace(chr(9), ' ')}\n" for qid, text in questions),
        encoding="utf-8",
    )
    (OUT_DIR / "tags.tsv").write_text(
        "tag_name\tquestion_id\n" + "".join(f"{name}\t{qid}\n" for name, qid in tag_q),
        encoding="utf-8",
    )
    (OUT_DIR / "probe.log").write_text(
        f"questions={len(questions)} distinct_tags={len(tag_counts)} tag_question_pairs={len(tag_q)}\n"
        + "".join(f"{name}\t{count}\n" for name, count in tag_counts),
        encoding="utf-8",
    )
    print(f"questions={len(questions)} distinct_tags={len(tag_counts)} pairs={len(tag_q)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
