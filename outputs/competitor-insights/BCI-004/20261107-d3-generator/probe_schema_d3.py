"""只读探查：D3 生成器需要的表结构与标签枚举。

用途：确认 user_insight.interview / answer / tag / tag_evidence / evidence 的真实列名，
避免生成器按记忆写 SQL。
输出：schema-d3.log（与本脚本同目录）。
"""

from __future__ import annotations

import sys
from pathlib import Path

import psycopg2

PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))
from customer_insight.quant_service import _load_env  # noqa: E402

OUT = Path(__file__).resolve().parent / "schema-d3.log"
TABLES = ("interview", "question", "answer", "evidence", "tag", "tag_evidence")


def main() -> int:
    cfg = _load_env()
    conn = psycopg2.connect(
        host=cfg.get("NEW_CAR_PG_HOST", ""),
        port=int(cfg.get("NEW_CAR_PG_PORT", "5432")),
        dbname=cfg.get("NEW_CAR_PG_DATABASE", ""),
        user=cfg.get("USER_INSIGHT_LOADER_USER", ""),
        password=cfg.get("USER_INSIGHT_LOADER_PASSWORD", ""),
        connect_timeout=10,
    )
    lines: list[str] = []
    try:
        with conn.cursor() as cur:
            for table in TABLES:
                cur.execute(
                    "SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_schema='user_insight' AND table_name=%s ORDER BY ordinal_position",
                    (table,),
                )
                lines.append(f"[{table}]")
                lines += [f"  {name}\t{typ}" for name, typ in cur.fetchall()]

            cur.execute(
                "SELECT DISTINCT extraction_status FROM user_insight.tag ORDER BY 1"
            )
            lines.append(f"[tag.extraction_status] {[r[0] for r in cur.fetchall()]}")
            cur.execute("SELECT DISTINCT trust_status FROM user_insight.tag ORDER BY 1")
            lines.append(f"[tag.trust_status] {[r[0] for r in cur.fetchall()]}")
            cur.execute(
                "SELECT tag_name, count(*) FROM user_insight.tag GROUP BY 1 ORDER BY 2 DESC LIMIT 8"
            )
            lines.append(f"[tag sample] {cur.fetchall()}")
            cur.execute(
                "SELECT interview_id, city, vehicle_model, purchase_type FROM user_insight.interview ORDER BY 1 LIMIT 3"
            )
            lines.append(f"[interview sample] {cur.fetchall()}")
    finally:
        conn.close()
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
