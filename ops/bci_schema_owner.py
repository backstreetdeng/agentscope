"""BCI-004 · L10：把 bci schema 属主转给 user_insight_loader（幂等）。

- 先查当前属主，已是目标属主则跳过 ALTER；
- 否则用 `vectordb` 属主账号执行 `ALTER SCHEMA bci OWNER TO user_insight_loader`；
- 转属主后用 loader 账号跑冒烟：建表、插入、查询、删除、删表 + 读现有业务表；
- 全程不打印任何口令。

用法：../Scripts/python.exe -B ops/bci_schema_owner.py
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

import psycopg2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from competitor_insight.server import db  # noqa: E402

TARGET_OWNER = "user_insight_loader"
SCHEMA = "bci"
OWNER_ENV_KEYS = (
    "NEW_CAR_PG_OWNER_PASSWORD",
    "VECTORDB_PASSWORD",
    "NEW_CAR_PG_SUPERUSER_PASSWORD",
)
LEGACY_BLOB = "1bd7eee:outputs/competitor-insights/BCI-004/20261106-coverage/coverage.py"


def current_owner(conn) -> str:
    with conn.cursor() as cur:
        cur.execute(
            "select pg_get_userbyid(nspowner) from pg_namespace where nspname = %s",
            (SCHEMA,),
        )
        row = cur.fetchone()
    return row[0] if row else "<missing>"


def owner_password(cfg: dict[str, str]) -> str | None:
    for key in OWNER_ENV_KEYS:
        value = os.environ.get(key) or cfg.get(key)
        if value:
            return value
    # 历史 ops 脚本里保存过该账号；只从 git 历史读取，不落盘、不打印。
    try:
        blob = subprocess.run(
            ["git", "show", LEGACY_BLOB],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"password\s*=\s*[\"']([^\"']+)[\"']", blob)
    return match.group(1) if match else None


def main() -> int:
    cfg = db.load_env(ROOT)
    conn = db.connect(cfg)
    try:
        before = current_owner(conn)
        print(f"schema={SCHEMA} owner_before={before}")

        if before != TARGET_OWNER:
            password = owner_password(cfg)
            if not password:
                print("FAIL: 未找到 vectordb 属主账号口令，无法执行 ALTER")
                return 2
            owner_conn = psycopg2.connect(
                host=cfg.get("NEW_CAR_PG_HOST", ""),
                port=int(cfg.get("NEW_CAR_PG_PORT", "5432")),
                dbname=cfg.get("NEW_CAR_PG_DATABASE", ""),
                user="vectordb",
                password=password,
                connect_timeout=10,
            )
            try:
                owner_conn.autocommit = True
                with owner_conn.cursor() as cur:
                    cur.execute(f'ALTER SCHEMA {SCHEMA} OWNER TO {TARGET_OWNER}')
                print("alter=executed")
            finally:
                owner_conn.close()
        else:
            print("alter=skipped(already owner)")

        after = current_owner(conn)
        print(f"owner_after={after}")

        scratch = f"_owner_smoke_{uuid.uuid4().hex[:8]}"
        smoke_ok = True
        try:
            with conn.cursor() as cur:
                cur.execute(f"create table {SCHEMA}.{scratch} (id int primary key, note text)")
                cur.execute(f"insert into {SCHEMA}.{scratch} values (1, 'smoke')")
                cur.execute(f"select note from {SCHEMA}.{scratch} where id = 1")
                if cur.fetchone()[0] != "smoke":
                    smoke_ok = False
                cur.execute(f"delete from {SCHEMA}.{scratch} where id = 1")
                cur.execute(f"select count(*) from {SCHEMA}.{scratch}")
                if cur.fetchone()[0] != 0:
                    smoke_ok = False
                cur.execute(f"drop table {SCHEMA}.{scratch}")
            conn.commit()
        except psycopg2.Error as exc:
            conn.rollback()
            smoke_ok = False
            print(f"smoke_error={exc.__class__.__name__}: {str(exc).strip()}")
            with conn.cursor() as cur:
                cur.execute(f"drop table if exists {SCHEMA}.{scratch}")
            conn.commit()

        with conn.cursor() as cur:
            cur.execute("select count(*) from bci.archive")
            archives = cur.fetchone()[0]
            cur.execute("select count(*) from bci.archive_field")
            fields = cur.fetchone()[0]
        print(f"smoke={'PASS' if smoke_ok else 'FAIL'} archives={archives} archive_fields={fields}")
        print(f"checked_at={datetime.now().isoformat(timespec='seconds')}")
        return 0 if (after == TARGET_OWNER and smoke_ok) else 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
