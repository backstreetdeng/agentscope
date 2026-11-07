"""BCI-004：核实 R046「购车属性（首增换购）」互斥值 suspect 的来源链路与原始原文。只读。

输出：字段行、模板映射、interview.purchase_type、answer 原文、tag、evidence 时间段落。
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from competitor_insight.server import db  # noqa: E402

TARGET = sys.argv[1] if len(sys.argv) > 1 else "R046"

conn = db.connect()
with conn.cursor() as cur:
    # 1) 档案字段行
    cur.execute(
        "select a.archive_id, a.interview_id, a.template_id, a.revision, a.status,"
        " f.dimension_id, f.value_text, f.fill_mode, f.review_status, f.confidence,"
        " f.source_ref, f.evidence_refs, f.no_data_reason, f.updated_at"
        " from bci.archive a join bci.archive_field f using (archive_id)"
        " where a.interview_id = %s and f.dimension_id = 'purchase_attribute'",
        (TARGET,),
    )
    for row in cur.fetchall():
        print("FIELD", json.dumps(dict(zip(
            ["archive_id", "interview_id", "template_id", "revision", "status",
             "dimension_id", "value_text", "fill_mode", "review_status", "confidence",
             "source_ref", "evidence_refs", "no_data_reason", "updated_at"], row)),
            ensure_ascii=False, default=str))

    # 2) 访谈基础信息
    cur.execute("select * from user_insight.interview where interview_id = %s", (TARGET,))
    cols = [d[0] for d in cur.description]
    for row in cur.fetchall():
        info = dict(zip(cols, row))
        keep = {k: info.get(k) for k in (
            "interview_id", "purchase_type", "vehicle_model", "city", "interview_date",
            "respondent_code") if k in info}
        print("INTERVIEW", json.dumps(keep, ensure_ascii=False, default=str))

    # 3) 题 1 的答案原文
    cur.execute(
        "select answer_id, question_id, answer_text"
        " from user_insight.answer where interview_id = %s and question_id = 1",
        (TARGET,),
    )
    for row in cur.fetchall():
        print("ANSWER", json.dumps(dict(zip(["answer_id", "question_id", "answer_text"], row)),
                                   ensure_ascii=False, default=str))

    # 4) 标签
    cur.execute(
        "select tag_id, tag_name, tag_value, mapped_question_ids, extraction_status, trust_status"
        " from user_insight.tag where interview_id = %s and tag_name like %s",
        (TARGET, "%首增换购%"),
    )
    for row in cur.fetchall():
        print("TAG", json.dumps(dict(zip(
            ["tag_id", "tag_name", "tag_value", "mapped_question_ids",
             "extraction_status", "trust_status"], row)), ensure_ascii=False, default=str))

    # 5) 证据（题 1 及全部含购车/增购/换购字样的原话）
    cur.execute(
        "select evidence_id, question_id, left(quote_text, 400), start_sec, end_sec"
        " from user_insight.evidence where interview_id = %s"
        " and (question_id = 1 or quote_text like %s or quote_text like %s"
        "      or quote_text like %s or quote_text like %s)"
        " order by question_id, evidence_id limit 40",
        (TARGET, "%增购%", "%换购%", "%置换%", "%第一辆车%"),
    )
    for row in cur.fetchall():
        print("EVID", json.dumps(dict(zip(
            ["evidence_id", "question_id", "text", "time_start", "time_end"], row)),
            ensure_ascii=False, default=str))

conn.close()
