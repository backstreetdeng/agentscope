"""BCI-004 · D2：执行 bci.archive* 的 DDL 并按真实库做权限、结构、冒烟验证。

步骤：
1. 以 owner 级账号（.env.new-car 的 NEW_CAR_PG_*）执行 ops/bci_archive_ddl_owner.sql；
2. 以 user_insight_loader 执行 ops/bci_archive_ddl.sql；
3. 记录执行前后 has_database_privilege / has_schema_privilege 的真实结果；
4. 用 pg_catalog / information_schema 核对 4 张表、主键、唯一约束、外键与索引；
5. 用测试数据做 insert/select/delete 冒烟并清理。

不打印任何密码；输出同时写入 outputs/competitor-insights/BCI-004/20261107-d2-ddl/apply.log。
可重复执行。
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import psycopg2

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OPS_DIR = PROJECT_ROOT / "ops"
LOG_DIR = PROJECT_ROOT / "outputs" / "competitor-insights" / "BCI-004" / "20261107-d2-ddl"
LOG_PATH = LOG_DIR / "apply.log"

SMOKE_RUN_ID = "00000000-0000-4000-8000-00000000d2aa"
SMOKE_INTERVIEW = "__smoke_bci004__"
SMOKE_TEMPLATE = "__smoke_template__"


class DdlError(RuntimeError):
    pass


def load_env() -> dict[str, str]:
    cfg: dict[str, str] = {}
    for name in (".env", ".env.new-car"):
        path = PROJECT_ROOT / name
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            cfg[key.strip()] = value.strip().strip('"').strip("'")
    return cfg


def connect(cfg: dict[str, str], user_key: str, password_key: str) -> psycopg2.extensions.connection:
    user = cfg.get(user_key, "")
    password = cfg.get(password_key, "")
    if not user or not password:
        raise DdlError(f"缺少凭据：{user_key} / {password_key}")
    return psycopg2.connect(
        host=cfg.get("NEW_CAR_PG_HOST", ""),
        port=int(cfg.get("NEW_CAR_PG_PORT", "5432")),
        dbname=cfg.get("NEW_CAR_PG_DATABASE", ""),
        user=user,
        password=password,
        connect_timeout=10,
    )


def fetch(cur, sql: str, params: tuple = ()):
    cur.execute(sql, params)
    return cur.fetchall()


def privilege_snapshot(cur, schema: str) -> list[str]:
    rows = fetch(
        cur,
        """
        SELECT current_user,
               has_database_privilege(current_user, current_database(), 'CREATE')
        """,
    )
    user, db_create = rows[0]
    exists = bool(fetch(cur, "SELECT 1 FROM pg_namespace WHERE nspname = %s", (schema,)))
    if exists:
        schema_usage, schema_create = fetch(
            cur,
            """
            SELECT has_schema_privilege(current_user, %s, 'USAGE'),
                   has_schema_privilege(current_user, %s, 'CREATE')
            """,
            (schema, schema),
        )[0]
    else:
        schema_usage = schema_create = "schema_absent"
    return [
        f"user={user}",
        f"has_database_create={db_create}",
        f"has_schema_usage({schema})={schema_usage}",
        f"has_schema_create({schema})={schema_create}",
    ]


def verify_structure(cur) -> list[str]:
    lines: list[str] = []
    tables = fetch(
        cur,
        """
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'bci' AND table_type = 'BASE TABLE'
        ORDER BY table_name
        """,
    )
    names = [row[0] for row in tables]
    expected = ["archive", "archive_field", "archive_run", "archive_run_item"]
    lines.append(f"tables={names}")
    missing = [name for name in expected if name not in names]
    if missing:
        raise DdlError(f"缺少表：{missing}")

    constraints = fetch(
        cur,
        """
        SELECT conrelid::regclass::text, contype, pg_get_constraintdef(oid)
        FROM pg_constraint
        WHERE connamespace = 'bci'::regnamespace
        ORDER BY 1, 2
        """,
    )
    for table, ctype, definition in constraints:
        lines.append(f"constraint {table} [{ctype}] {definition}")

    indexes = fetch(
        cur,
        """
        SELECT tablename, indexname FROM pg_indexes
        WHERE schemaname = 'bci' ORDER BY tablename, indexname
        """,
    )
    for table, index in indexes:
        lines.append(f"index {table}.{index}")

    seq = fetch(cur, "SELECT sequencename FROM pg_sequences WHERE schemaname = 'bci'")
    lines.append(f"sequences={[row[0] for row in seq]}")
    return lines


def smoke_test(cur) -> list[str]:
    lines: list[str] = []
    cur.execute(
        """
        INSERT INTO bci.archive_run
            (run_id, template_id, template_version, mode, request_json, status, total)
        VALUES (%s, %s, 'v1', 'single', %s::jsonb, 'running', 1)
        """,
        (SMOKE_RUN_ID, SMOKE_TEMPLATE, '{"smoke": true}'),
    )
    cur.execute(
        "INSERT INTO bci.archive_run_item (run_id, interview_id, status) VALUES (%s, %s, 'running')",
        (SMOKE_RUN_ID, SMOKE_INTERVIEW),
    )
    cur.execute(
        """
        INSERT INTO bci.archive
            (interview_id, template_id, template_version, template_snapshot, run_id, revision, status)
        VALUES (%s, %s, 'v1', %s::jsonb, %s, 1, 'partial')
        RETURNING archive_id
        """,
        (SMOKE_INTERVIEW, SMOKE_TEMPLATE, '{"template_id": "__smoke_template__"}', SMOKE_RUN_ID),
    )
    archive_id = cur.fetchone()[0]
    cur.execute(
        """
        INSERT INTO bci.archive_field
            (archive_id, dimension_id, group_id, fill_mode, no_data_reason)
        VALUES (%s, 'first_choice_ranking', 'comparison', 'none', '冒烟测试')
        """,
        (archive_id,),
    )

    cur.execute(
        """
        SELECT a.archive_id, a.status, count(f.dimension_id)
        FROM bci.archive a JOIN bci.archive_field f ON f.archive_id = a.archive_id
        WHERE a.interview_id = %s GROUP BY a.archive_id, a.status
        """,
        (SMOKE_INTERVIEW,),
    )
    found = cur.fetchall()
    if len(found) != 1 or found[0][2] != 1:
        raise DdlError(f"冒烟读取异常：{found}")
    lines.append(f"select_ok=archive_id:{found[0][0]} status:{found[0][1]} fields:{found[0][2]}")

    cur.execute("DELETE FROM bci.archive WHERE interview_id = %s", (SMOKE_INTERVIEW,))
    cur.execute("DELETE FROM bci.archive_run WHERE run_id = %s", (SMOKE_RUN_ID,))
    cur.execute(
        "SELECT (SELECT count(*) FROM bci.archive WHERE interview_id = %s), "
        "(SELECT count(*) FROM bci.archive_field WHERE archive_id = %s), "
        "(SELECT count(*) FROM bci.archive_run WHERE run_id = %s), "
        "(SELECT count(*) FROM bci.archive_run_item WHERE run_id = %s)",
        (SMOKE_INTERVIEW, archive_id, SMOKE_RUN_ID, SMOKE_RUN_ID),
    )
    leftovers = cur.fetchone()
    if any(leftovers):
        raise DdlError(f"冒烟清理失败：{leftovers}")
    lines.append(f"delete_ok=remaining:{leftovers}")
    return lines


def main() -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    cfg = load_env()
    lines: list[str] = [f"# BCI-004 D2 DDL apply @ {datetime.now().isoformat(timespec='seconds')}"]

    owner_sql = (OPS_DIR / "bci_archive_ddl_owner.sql").read_text(encoding="utf-8")
    table_sql = (OPS_DIR / "bci_archive_ddl.sql").read_text(encoding="utf-8")

    owner = connect(cfg, "NEW_CAR_PG_USER", "NEW_CAR_PG_PASSWORD")
    try:
        with owner.cursor() as cur:
            lines.append("[owner before] " + " | ".join(privilege_snapshot(cur, "bci")))
            exists = fetch(cur, "SELECT 1 FROM pg_namespace WHERE nspname = 'bci'")
            lines.append(f"bci_exists_before={bool(exists)}")
            db_create = fetch(
                cur,
                "SELECT has_database_privilege(current_user, current_database(), 'CREATE')",
            )[0][0]
            if not db_create:
                raise DdlError("owner 账号也没有 database CREATE 权限，停止（不提权）")
            cur.execute(owner_sql)
        owner.commit()
        with owner.cursor() as cur:
            lines.append("[owner after] " + " | ".join(privilege_snapshot(cur, "bci")))
            owner_name = fetch(
                cur,
                "SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname = 'bci'",
            )[0][0]
            lines.append(f"bci_owner={owner_name}")
            if owner_name not in ("user_insight_loader", "vectordb"):
                raise DdlError(f"bci schema 属主异常：{owner_name}")
            if owner_name == "vectordb":
                lines.append(
                    "note=owner 不是 loader 成员，未能 AUTHORIZATION；已改为建 schema + 最小 GRANT，"
                    "表由 loader 创建并持有"
                )
    finally:
        owner.close()

    loader = connect(cfg, "USER_INSIGHT_LOADER_USER", "USER_INSIGHT_LOADER_PASSWORD")
    try:
        with loader.cursor() as cur:
            lines.append("[loader before] " + " | ".join(privilege_snapshot(cur, "bci")))
            cur.execute(table_sql)
            loader.commit()
            lines.append("[loader after] " + " | ".join(privilege_snapshot(cur, "bci")))
            for line in verify_structure(cur):
                lines.append(line)
            for line in smoke_test(cur):
                lines.append(line)
            loader.commit()
    finally:
        loader.close()

    LOG_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - 运维脚本需如实落日志后退出
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        LOG_PATH.write_text(f"FAILED: {type(exc).__name__}: {exc}\n", encoding="utf-8")
        print(f"FAILED: {type(exc).__name__}: {exc}")
        sys.exit(1)
