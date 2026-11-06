"""只读探查：关键标签的取值样例，供 D3 生成器确定解析方式。"""

from __future__ import annotations

import sys
from pathlib import Path

import psycopg2

PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))
from customer_insight.quant_service import _load_env  # noqa: E402

OUT = Path(__file__).resolve().parent / "tag-values-d3.log"
NAMES = ("年龄", "购车预算", "核心对比车型", "最终核心对比车型", "满意点", "不满意点", "本次购车关注", "首增换购属性", "选择当前车辆的原因")


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
            for name in NAMES:
                cur.execute(
                    "SELECT interview_id, tag_value, trust_status, extraction_status "
                    "FROM user_insight.tag WHERE tag_name=%s ORDER BY interview_id LIMIT 3",
                    (name,),
                )
                rows = cur.fetchall()
                lines.append(f"[{name}]")
                lines += [f"  {r[0]}\t{r[1]}\t{r[2]}\t{r[3]}" for r in rows]
            cur.execute(
                "SELECT interview_id, question_id, left(answer_text, 180) FROM user_insight.answer "
                "WHERE question_id IN (59, 63, 26) ORDER BY interview_id LIMIT 6"
            )
            lines.append("[answers]")
            lines += [f"  {r[0]} Q{r[1]} {r[2]}" for r in cur.fetchall()]
            cur.execute(
                "SELECT count(*) FROM user_insight.evidence WHERE interview_id='R001'"
            )
            lines.append(f"[evidence R001] {cur.fetchone()[0]}")
    finally:
        conn.close()
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
