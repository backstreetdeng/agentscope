"""只读探查：interview 表列名与 question_id 连续性。

用途：确认 source-map 中 metadata 字段名真实存在，以及题号区间。
输出：interview-columns.log（与本脚本同目录）。
"""

from __future__ import annotations

import sys
from pathlib import Path

import psycopg2

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from customer_insight.quant_service import _load_env  # noqa: E402

OUT = Path(__file__).resolve().parent / "interview-columns.log"


def main() -> int:
    cfg = _load_env()
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
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema='user_insight' AND table_name='interview' "
                "ORDER BY ordinal_position"
            )
            columns = cur.fetchall()
            cur.execute("SELECT min(question_id), max(question_id), count(*) FROM user_insight.question")
            qstat = cur.fetchone()
            cur.execute("SELECT count(*) FROM user_insight.question WHERE question_id IS NULL")
            null_q = cur.fetchone()[0]
    finally:
        conn.close()

    lines = ["[interview columns]"]
    lines += [f"{name}\t{typ}" for name, typ in columns]
    lines.append("")
    lines.append(f"[question] min={qstat[0]} max={qstat[1]} count={qstat[2]} null_id={null_q}")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
