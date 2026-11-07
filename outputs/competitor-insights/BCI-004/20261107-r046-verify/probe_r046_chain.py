"""R046「首增换购属性」来源链路 + 原话证据 + 影响面统计。只读。"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from competitor_insight.server import db  # noqa: E402

TARGET = "R046"
TAG_ID = "TAG-377357cc173d61c8ce47"

conn = db.connect()
with conn.cursor() as cur:
    cur.execute(
        "select tag_id, tag_name, tag_value, allowed_values, mapped_question_ids,"
        " programmatic_evidence, extraction_status, trust_status, confidence"
        " from user_insight.tag where tag_id = %s",
        (TAG_ID,),
    )
    cols = [d[0] for d in cur.description]
    for row in cur.fetchall():
        print("TAG", json.dumps(dict(zip(cols, row)), ensure_ascii=False, default=str))

    cur.execute(
        "select tag_evidence_id, question_id, question_text, quote_text,"
        " time_range_text, start_sec, end_sec, speaker_label"
        " from user_insight.tag_evidence where tag_id = %s order by question_id, start_sec",
        (TAG_ID,),
    )
    for row in cur.fetchall():
        print("TAG_EVID", json.dumps(dict(zip(
            ["id", "question_id", "question_text", "quote", "time_range",
             "start", "end", "speaker"], row)), ensure_ascii=False, default=str))

    cur.execute(
        "select evidence_id, question_id, quote_text, start_sec, end_sec, time_precision"
        " from user_insight.evidence where interview_id = %s order by question_id, start_sec",
        (TARGET,),
    )
    rows = cur.fetchall()
    print("EVIDENCE_COUNT", len(rows))
    hits = [r for r in rows if any(k in (r[2] or "") for k in ("增购", "换购", "首购", "置换", "雅阁"))]
    print("EVIDENCE_HITS", len(hits))
    for row in hits[:12]:
        print("EVID", json.dumps(dict(zip(
            ["evidence_id", "question_id", "quote", "start", "end", "precision"], row)),
            ensure_ascii=False, default=str))

    # ID 体系：是否存在 RE010，两者 Q1 是否同文
    cur.execute("select interview_id, respondent_code from user_insight.interview"
                " where interview_id in ('R046', 'RE010')")
    print("IDS", cur.fetchall())
    cur.execute("select interview_id, answer_id, left(answer_text, 120) from user_insight.answer"
                " where interview_id in ('R046', 'RE010') and question_id = 1")
    for row in cur.fetchall():
        print("Q1", row[0], row[1], row[2])

    # 影响面 1：库内已产出的 suspect 字段
    cur.execute(
        "select a.interview_id, f.dimension_id, f.value_text, left(f.no_data_reason, 40)"
        " from bci.archive_field f join bci.archive a using (archive_id)"
        " where f.review_status = 'suspect' order by 1, 2"
    )
    print("ARCHIVE_SUSPECT", cur.fetchall())

    # 影响面 2：全库「首增换购属性」标签的多值情况（触发条件）
    cur.execute(
        "select tag_value, count(*) from user_insight.tag"
        " where tag_name = '首增换购属性' group by 1 order by 2 desc"
    )
    print("TAG_VALUE_DIST", cur.fetchall())
    cur.execute(
        "select interview_id, tag_value from user_insight.tag"
        " where tag_name = '首增换购属性' and (tag_value like %s or tag_value like %s)"
        " order by 1",
        ("%；%", "%;%"),
    )
    rows = cur.fetchall()
    print("MULTI_VALUE_TAGS", len(rows), rows)
conn.close()
