"""只读校验：source-map 的题号与标签是否全部能在真实库中找到。

用途：为 D1 验收「question_ids 全部存在于 question 表」提供库侧证据。
只读：SELECT question_id / tag_name。
输出：validate.log（与本脚本同目录）。
"""

from __future__ import annotations

import sys
from pathlib import Path

import psycopg2

PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))

from competitor_insight.server.source_map import (  # noqa: E402
    load_source_map,
    load_template_definition,
    validate_against_question_ids,
    validate_against_tag_names,
    validate_against_template,
)
from customer_insight.quant_service import _load_env  # noqa: E402

MAP_PATH = PROJECT_ROOT / "competitor_insight" / "templates" / "user_insight_archive.source-map.json"
TPL_PATH = PROJECT_ROOT / "competitor_insight" / "templates" / "user_insight_archive_template.json"
OUT = Path(__file__).resolve().parent / "validate.log"


def main() -> int:
    source_map = load_source_map(MAP_PATH)
    template = load_template_definition(TPL_PATH)
    validate_against_template(source_map, template)

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
            cur.execute("SELECT question_id FROM user_insight.question")
            db_questions = {row[0] for row in cur.fetchall()}
            cur.execute("SELECT DISTINCT tag_name FROM user_insight.tag")
            db_tags = {row[0] for row in cur.fetchall()}
    finally:
        conn.close()

    validate_against_question_ids(source_map, db_questions)
    validate_against_tag_names(source_map, db_tags)

    counts = source_map.fill_mode_counts()
    lines = [
        "[source-map]",
        f"template={source_map.template_id}@{source_map.template_version} dimensions={len(source_map.dimensions)}",
        f"fill_mode={counts}",
        f"distinct_question_ids={len(source_map.question_ids())} "
        f"all_exist={source_map.question_ids() <= db_questions}",
        f"distinct_tag_names={len(source_map.tag_names())} "
        f"all_exist={source_map.tag_names() <= db_tags}",
        f"db_questions={len(db_questions)} db_tags={len(db_tags)}",
        "",
        "[no-source dimensions]",
    ]
    for dim in source_map.no_source_dimensions():
        lines.append(f"{dim.dimension_id}\t{dim.no_source_reason}")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
