"""T6 定量数据导入：把 2025定量数据汇总.xlsx 导入 user_insight.quant_sample / quant_question。

用法：python import_quant.py（幂等，ON CONFLICT DO NOTHING）
"""
import csv
import json
import sys
from pathlib import Path

import openpyxl
import psycopg2
import psycopg2.extras

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(r"D:\work\AI\用户洞察智能体\方案相关\用户洞察智能体_数据底座_v1_20261030")
XLSX = DATA_ROOT / "02_定量/2025定量数据汇总.xlsx"
COLUMNS_CSV = DATA_ROOT / "02_定量/quant_columns.csv"
INDEX_CSV = DATA_ROOT / "02_定量/quant_respondent_index.csv"


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


def to_num(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return v
    s = str(v).strip()
    if s == "":
        return None
    try:
        return float(s) if "." in s else int(s)
    except ValueError:
        return s


def main():
    cfg = load_env()

    # 1. quant_columns.csv -> 题目字典 + 列映射
    questions = []
    num_col_to_qid = {}
    text_col_to_qid = {}
    with COLUMNS_CSV.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            qprefix = (r.get("question_prefix") or "").strip()
            if not qprefix:
                continue
            ci = int(r["column_index"])
            sheet = r["sheet_name"]
            questions.append((qprefix, ci, r["header"], sheet))
            if sheet == "数字版":
                num_col_to_qid[ci] = qprefix
            elif sheet == "中文版":
                text_col_to_qid[ci] = qprefix

    # 2. quant_respondent_index.csv -> 样本维度
    sample_dims = {}
    with INDEX_CSV.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            sample_dims[r["sample_id"]] = {
                "respondent_seq": int(r["respondent_seq"]),
                "purchase_model": r["purchase_model"],
                "purchase_type": r["purchase_type"],
                "price_band": r.get("price_band"),
                "city": r.get("city"),
                "birth_year": int(r["birth_year"]) if r.get("birth_year") else None,
                "age_band": r.get("age_band"),
                "gender": r.get("gender"),
            }

    # 3. 读 xlsx 数字版 + 中文版
    wb = openpyxl.load_workbook(XLSX, read_only=True)
    ws_num = wb["数字版"]
    ws_text = wb["中文版"]

    answers_num = {}
    answers_text = {}
    for row in ws_num.iter_rows(min_row=2, values_only=True):
        if row[1] is None:
            continue
        sample_id = str(row[1])
        answers_num[sample_id] = {
            num_col_to_qid[ci]: to_num(v)
            for ci, v in enumerate(row, start=1)
            if ci in num_col_to_qid and v is not None
        }
    for row in ws_text.iter_rows(min_row=2, values_only=True):
        if row[1] is None:
            continue
        sample_id = str(row[1])
        answers_text[sample_id] = {
            text_col_to_qid[ci]: str(v)
            for ci, v in enumerate(row, start=1)
            if ci in text_col_to_qid and v is not None and str(v).strip() != ""
        }
    wb.close()

    # 4. 写库
    conn = connect(cfg)
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute(
        "CREATE TABLE IF NOT EXISTS user_insight.quant_question ("
        "question_id text PRIMARY KEY, column_index integer, question_text text, sheet_name text)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS user_insight.quant_sample ("
        "sample_id text PRIMARY KEY, respondent_seq integer, purchase_model text, purchase_type text, "
        "price_band text, city text, birth_year integer, age_band text, gender text, "
        "answers_num jsonb NOT NULL DEFAULT '{}'::jsonb, answers_text jsonb NOT NULL DEFAULT '{}'::jsonb)"
    )

    q_rows = [(qid, ci, text, sheet) for qid, ci, text, sheet in questions]
    psycopg2.extras.execute_values(
        cur,
        "INSERT INTO user_insight.quant_question (question_id, column_index, question_text, sheet_name) "
        "VALUES %s ON CONFLICT DO NOTHING",
        q_rows,
        page_size=500,
    )

    s_rows = []
    for sample_id, dim in sample_dims.items():
        s_rows.append((
            sample_id, dim["respondent_seq"], dim["purchase_model"], dim["purchase_type"],
            dim["price_band"], dim["city"], dim["birth_year"], dim["age_band"], dim["gender"],
            psycopg2.extras.Json(answers_num.get(sample_id, {})),
            psycopg2.extras.Json(answers_text.get(sample_id, {})),
        ))
    psycopg2.extras.execute_values(
        cur,
        "INSERT INTO user_insight.quant_sample "
        "(sample_id, respondent_seq, purchase_model, purchase_type, price_band, city, birth_year, age_band, gender, "
        "answers_num, answers_text) VALUES %s ON CONFLICT DO NOTHING",
        s_rows,
        page_size=500,
    )

    cur.execute("SELECT count(*) FROM user_insight.quant_question")
    print("quant_question rows:", cur.fetchone()[0])
    cur.execute("SELECT count(*) FROM user_insight.quant_sample")
    print("quant_sample rows:", cur.fetchone()[0])
    conn.close()


if __name__ == "__main__":
    sys.exit(main())
