"""为 answer 与 tag 表补充 bge-m3 1024 维 embedding（幂等：仅处理 embedding IS NULL 的行）。"""
import json
import sys
import urllib.request
from pathlib import Path

import psycopg2
import psycopg2.extras

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OLLAMA_EMBED_URL = "http://192.168.3.146:11434/api/embed"
EMBED_MODEL = "bge-m3:latest"
EMBED_BATCH = 32


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


def vec_str(vec):
    return "[" + ",".join(f"{x:.8g}" for x in vec) + "]"


def embed_texts(texts, retries=2):
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(
                OLLAMA_EMBED_URL,
                data=json.dumps({"model": EMBED_MODEL, "input": texts}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=300) as r:
                data = json.loads(r.read().decode())
            return [e for e in data["embeddings"]]
        except Exception as e:
            last = e
            print(f"    embed retry {attempt + 1}: {type(e).__name__} {str(e)[:120]}", flush=True)
    raise last


def backfill(cur, table, id_col, fetch_sql, update_sql):
    cur.execute(fetch_sql)
    rows = cur.fetchall()
    total = len(rows)
    print(f"[{table}] embedding 待补 {total} 条", flush=True)
    if total == 0:
        return 0
    done = 0
    for i in range(0, total, EMBED_BATCH):
        chunk = rows[i:i + EMBED_BATCH]
        texts = [r[1] for r in chunk]
        vecs = embed_texts(texts)
        update_rows = [(r[0], vec_str(v)) for r, v in zip(chunk, vecs)]
        psycopg2.extras.execute_values(cur, update_sql, update_rows, page_size=EMBED_BATCH)
        done += len(chunk)
        print(f"  {table} progress {done}/{total}", flush=True)
    return done


def main():
    cfg = load_env()
    conn = connect(cfg)
    conn.autocommit = True
    cur = conn.cursor()

    backfill(
        cur, "answer", "answer_id",
        "SELECT answer_id, answer_text FROM user_insight.answer WHERE embedding IS NULL",
        "UPDATE user_insight.answer AS a SET embedding = v.embedding::vector "
        "FROM (VALUES %s) AS v(answer_id, embedding) WHERE a.answer_id = v.answer_id",
    )
    backfill(
        cur, "tag", "tag_id",
        "SELECT tag_id, COALESCE(tag_name || ': ' || tag_value, tag_name) FROM user_insight.tag WHERE embedding IS NULL",
        "UPDATE user_insight.tag AS a SET embedding = v.embedding::vector "
        "FROM (VALUES %s) AS v(tag_id, embedding) WHERE a.tag_id = v.tag_id",
    )

    for t in ("answer", "tag"):
        cur.execute(f"SELECT count(*) FROM user_insight.{t} WHERE embedding IS NOT NULL")
        print(f"[done] {t} 有 embedding 的行数: {cur.fetchone()[0]}", flush=True)
    conn.close()


if __name__ == "__main__":
    sys.exit(main())
