"""只读探查：当前库账号是否具备建 schema 权限，bci schema 是否已存在。

用途：判断 D2（建表）能否直接执行，还是需要用户提供有 DDL 权限的账号。
只读：查询 pg_namespace 与 has_schema_privilege。
输出：db-privilege.log（与本脚本同目录）。
"""

from __future__ import annotations

import sys
from pathlib import Path

import psycopg2

PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))
from customer_insight.quant_service import _load_env  # noqa: E402

OUT = Path(__file__).resolve().parent / "db-privilege.log"


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
            cur.execute("SELECT current_user, current_database()")
            who = cur.fetchone()
            cur.execute("SELECT nspname FROM pg_namespace WHERE nspname = 'bci'")
            schema = [row[0] for row in cur.fetchall()]
            cur.execute("SELECT has_database_privilege(current_user, current_database(), 'CREATE')")
            db_create = cur.fetchone()[0]
            cur.execute("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
            public_create = cur.fetchone()[0]
            cur.execute("SELECT rolsuper, rolcreatedb FROM pg_roles WHERE rolname = current_user")
            role = cur.fetchone()
    finally:
        conn.close()

    lines = [
        f"user={who[0]} database={who[1]}",
        f"bci_schema_exists={bool(schema)}",
        f"has_database_create={db_create}",
        f"has_public_schema_create={public_create}",
        f"rolsuper={role[0]} rolcreatedb={role[1]}",
    ]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
