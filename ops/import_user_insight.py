"""T2 数据导入：将数据底座定性访谈数据导入 146 vectordb 的 user_insight schema。

用法：
  测试模式（限制行数）:
    python import_user_insight.py --limit 5
  全量导入:
    python import_user_insight.py

导入顺序按外键依赖：question -> interview -> answer -> evidence -> tag -> tag_evidence。
所有写入幂等（ON CONFLICT DO NOTHING），可重复执行。
embedding 不在此脚本生成；导入后运行 backfill_embedding.py 补充 answer/tag 向量。
"""
import argparse
import csv
import json
import re
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(r"D:\work\AI\用户洞察智能体\方案相关\用户洞察智能体_数据底座_v1_20261030")


def load_env():
    cfg = {}
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


def connect(cfg):
    return psycopg2.connect(
        host=cfg.get("NEW_CAR_PG_HOST", "192.168.3.146"),
        port=int(cfg.get("NEW_CAR_PG_PORT", "5432")),
        dbname=cfg.get("NEW_CAR_PG_DATABASE", "vectordb"),
        user=cfg.get("USER_INSIGHT_LOADER_USER", ""),
        password=cfg.get("USER_INSIGHT_LOADER_PASSWORD", ""),
        connect_timeout=10,
    )


def to_bool(v):
    return str(v).strip().lower() in ("true", "1", "yes", "t")


def to_num(v):
    if v is None or str(v).strip() == "":
        return None
    return float(v)


def parse_qids(v):
    """'Q68' / 'Q68、Q70' / '' -> [68] / [68,70] / []"""
    if not v or not str(v).strip():
        return []
    return [int(x) for x in re.findall(r"(?<!\d)\d{1,3}(?!\d)", str(v))]


def parse_json(v):
    if not v or not str(v).strip():
        return None
    try:
        return json.loads(v)
    except Exception:
        return str(v)


def to_jsonb(v):
    """把 CSV 里的 JSON 字符串解析为 psycopg2 Json 对象，空值回退为 []。"""
    parsed = parse_json(v)
    if parsed is None:
        parsed = []
    return psycopg2.extras.Json(parsed)


def batch_insert(cur, sql, rows, page_size=1000):
    for i in range(0, len(rows), page_size):
        psycopg2.extras.execute_values(cur, sql, rows[i:i + page_size], page_size=page_size)


def import_questions(cur, limit):
    p = DATA_ROOT / "01_定性访谈/题目/questions_85_clean.csv"
    rows = []
    with p.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if limit and len(rows) >= limit:
                break
            rows.append((int(r["question_id"]), r["category"], r["section"], r["priority"], r["question_text"]))
    batch_insert(cur, "INSERT INTO user_insight.question (question_id,category,section,priority,question_text) "
                      "VALUES %s ON CONFLICT DO NOTHING", rows)
    return len(rows)


def import_interviews(cur, limit):
    p = DATA_ROOT / "01_定性访谈/结构化/interviews.csv"
    rows = []
    with p.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if limit and len(rows) >= limit:
                break
            meta = parse_json(r.get("metadata_json")) or {}
            rows.append((r["interview_id"], "2025H2-depth-interview", r["respondent_code"], r["source_label"],
                         r.get("city"), r.get("vehicle_model"), r.get("purchase_type"), r.get("source_version"),
                         r.get("transcript_uri"), "internal_research_only", psycopg2.extras.Json(meta)))
    batch_insert(cur, "INSERT INTO user_insight.interview "
                      "(interview_id,project_id,respondent_code,source_label,city,vehicle_model,purchase_type,"
                      "source_version,transcript_uri,consent_scope,metadata) VALUES %s ON CONFLICT DO NOTHING", rows)
    return len(rows)


def import_answers(cur, limit):
    p = DATA_ROOT / "01_定性访谈/结构化/qa_pairs.csv"
    rows = []
    with p.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if limit and len(rows) >= limit:
                break
            rows.append((r["answer_id"], r["interview_id"], int(r["question_id"]), r["question_text"],
                         r["answer_text"], r.get("confidence"), to_jsonb(r.get("unanswered_items")),
                         to_jsonb(r.get("evidence_ranges")), r.get("source_format"), r.get("source_uri"),
                         to_bool(r.get("time_available"))))
    batch_insert(cur, "INSERT INTO user_insight.answer "
                      "(answer_id,interview_id,question_id,question_text,answer_text,confidence,unanswered_items,"
                      "evidence_ranges,source_format,source_uri,time_available) "
                      "VALUES %s ON CONFLICT DO NOTHING", rows)
    return len(rows)


def import_evidence(cur, limit):
    p = DATA_ROOT / "01_定性访谈/结构化/answer_evidence.jsonl"
    rows = []
    with p.open(encoding="utf-8-sig") as f:
        for line in f:
            if limit and len(rows) >= limit:
                break
            r = json.loads(line)
            loc = r.get("source_locator")
            loc = parse_json(loc) if isinstance(loc, str) else loc
            rows.append((r["evidence_id"], r["answer_id"], r["interview_id"], int(r["question_id"]),
                         to_num(r.get("start_sec")), to_num(r.get("end_sec")), r.get("time_precision"),
                         r.get("speaker_label"), r.get("quote_text"), int(r.get("block_index") or 0),
                         int(r.get("segment_index") or 0), psycopg2.extras.Json(loc or {}), r.get("checksum")))
    batch_insert(cur, "INSERT INTO user_insight.evidence "
                      "(evidence_id,answer_id,interview_id,question_id,start_sec,end_sec,time_precision,"
                      "speaker_label,quote_text,block_index,segment_index,source_locator,checksum) "
                      "VALUES %s ON CONFLICT DO NOTHING", rows)
    return len(rows)


def import_tags(cur, limit):
    p = DATA_ROOT / "01_定性访谈/结构化/tags.csv"
    rows = []
    with p.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if limit and len(rows) >= limit:
                break
            extra_meta = {k: r.get(k) for k in ("source_row", "batch_question_pool", "source_question",
                                                 "filtered_out_of_scope_question_ids",
                                                 "programmatic_evidence_original", "source_question_and_time_ranges")}
            rows.append((r["tag_id"], r["interview_id"], r["batch_code"], r["content_group"], r["tag_name"],
                         r.get("allowed_values"), parse_qids(r.get("mapped_question_ids")), r["tag_value"],
                         r.get("programmatic_qa_evidence"), r.get("extraction_status"),
                         r.get("cross_question_review"), r.get("format_review"), r.get("trust_status"),
                         r.get("confidence"), r.get("source_uri"), psycopg2.extras.Json(extra_meta)))
    batch_insert(cur, "INSERT INTO user_insight.tag "
                      "(tag_id,interview_id,batch_code,content_group,tag_name,allowed_values,mapped_question_ids,"
                      "tag_value,programmatic_evidence,extraction_status,cross_question_review,format_review,"
                      "trust_status,confidence,source_uri,metadata) "
                      "VALUES %s ON CONFLICT DO NOTHING", rows)
    return len(rows)


def import_tag_evidence(cur, limit):
    p = DATA_ROOT / "01_定性访谈/结构化/tag_evidence.csv"
    rows = []
    with p.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if limit and len(rows) >= limit:
                break
            loc = parse_json(r.get("source_locator"))
            rows.append((r["tag_evidence_id"], r["tag_id"], int(r["question_id"]) if r.get("question_id") else None,
                         r.get("time_range_text"), to_num(r.get("start_sec")), to_num(r.get("end_sec")),
                         r.get("speaker_label"), r.get("question_text"), r.get("quote_text"),
                         int(r["source_row"]) if r.get("source_row") else None,
                         psycopg2.extras.Json(loc or {}), r.get("checksum")))
    batch_insert(cur, "INSERT INTO user_insight.tag_evidence "
                      "(tag_evidence_id,tag_id,question_id,time_range_text,start_sec,end_sec,speaker_label,"
                      "question_text,quote_text,source_row,source_locator,checksum) "
                      "VALUES %s ON CONFLICT DO NOTHING", rows)
    return len(rows)


def count_table(cur, table):
    cur.execute(f"SELECT count(*) FROM user_insight.{table}")
    return cur.fetchone()[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="每表最多导入行数（0=全量），测试用")
    args = ap.parse_args()

    cfg = load_env()
    conn = connect(cfg)
    conn.autocommit = True
    cur = conn.cursor()

    steps = [
        ("question", import_questions),
        ("interview", import_interviews),
        ("answer", import_answers),
        ("evidence", import_evidence),
        ("tag", import_tags),
        ("tag_evidence", import_tag_evidence),
    ]
    for name, fn in steps:
        n = fn(cur, args.limit)
        print(f"[import] {name}: 读取 {n} 行")

    print("=== 最终各表行数 ===")
    for t in ("question", "interview", "answer", "evidence", "tag", "tag_evidence"):
        print(f"  {t}: {count_table(cur, t)}")
    conn.close()


if __name__ == "__main__":
    sys.exit(main())
