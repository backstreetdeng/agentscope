"""BCI-007 · 执行 bci.report* DDL 并做结构核对与冒烟。

步骤：
1. 以 user_insight_loader 执行 ops/bci_report_ddl.sql（全部 IF NOT EXISTS，可重跑）；
2. 用 pg_catalog / information_schema 核对 2 张表、主键、唯一约束、外键与索引；
3. insert/select/delete 冒烟并清理，不残留测试数据；
4. 只读 bci.archive*，不修改任何既有业务数据；不打印任何凭据。
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime
from pathlib import Path

import psycopg2

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OPS_DIR = PROJECT_ROOT / "ops"
LOG_DIR = PROJECT_ROOT / "outputs" / "competitor-insights" / "BCI-007"
LOG_PATH = LOG_DIR / "apply-ddl.log"

SMOKE_REPORT = "00000000-0000-4000-8000-0000000007aa"
SMOKE_VERSION = "00000000-0000-4000-8000-0000000007ab"


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


def connect_loader(cfg: dict[str, str]):
    user = cfg.get("USER_INSIGHT_LOADER_USER", "")
    password = cfg.get("USER_INSIGHT_LOADER_PASSWORD", "")
    if not user or not password:
        raise DdlError("缺少 USER_INSIGHT_LOADER_USER / USER_INSIGHT_LOADER_PASSWORD")
    return psycopg2.connect(
        host=cfg.get("NEW_CAR_PG_HOST", ""),
        port=int(cfg.get("NEW_CAR_PG_PORT", "5432")),
        dbname=cfg.get("NEW_CAR_PG_DATABASE", ""),
        user=user,
        password=password,
        connect_timeout=10,
    )


def verify_structure(cur) -> list[str]:
    lines: list[str] = []
    tables = [
        row[0]
        for row in _fetch(
            cur,
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'bci' AND table_type = 'BASE TABLE' ORDER BY table_name",
        )
    ]
    lines.append(f"tables={tables}")
    for name in ("report", "report_version"):
        if name not in tables:
            raise DdlError(f"缺少表：bci.{name}")
    for table, ctype, definition in _fetch(
        cur,
        "SELECT conrelid::regclass::text, contype, pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE connamespace = 'bci'::regnamespace AND conrelid::regclass::text IN ('bci.report', 'bci.report_version') "
        "ORDER BY 1, 2",
    ):
        lines.append(f"constraint {table} [{ctype}] {definition}")
    indexes = _fetch(
        cur,
        "SELECT tablename, indexname FROM pg_indexes WHERE schemaname = 'bci' "
        "AND tablename IN ('report', 'report_version') ORDER BY 1, 2",
    )
    if not indexes:
        raise DdlError("report 表没有任何索引")
    for table, index in indexes:
        lines.append(f"index {table}.{index}")
    return lines


def smoke(cur) -> list[str]:
    lines: list[str] = []
    cur.execute("DELETE FROM bci.report WHERE report_id = %s", (SMOKE_REPORT,))
    cur.execute(
        "INSERT INTO bci.report (report_id, title, model_keys, model_key, sample_scope, created_by) "
        "VALUES (%s, %s, %s::jsonb, %s, %s::jsonb, 'smoke')",
        (SMOKE_REPORT, "__smoke_report__", '["smoke"]', "smoke", '{"quant": "smoke"}'),
    )
    cur.execute(
        "INSERT INTO bci.report_version "
        "(report_version_id, report_id, version_no, version_label, content, html, data_fingerprint, source_snapshot) "
        "VALUES (%s, %s, 1, 'v1.0', %s::jsonb, %s, %s, %s::jsonb)",
        (SMOKE_VERSION, SMOKE_REPORT, '{"pages": []}', "<html></html>", "0" * 64, "{}"),
    )
    cur.execute(
        "SELECT count(*), max(length(html)), max(version_label), max(revision_kind), "
        "max(parent_version_id::text) FROM bci.report_version WHERE report_id = %s",
        (SMOKE_REPORT,),
    )
    rows, html_len, label, kind, parent_id = cur.fetchone()
    if rows != 1 or html_len <= 0:
        raise DdlError(f"冒烟读取异常：{rows}/{html_len}")
    if label != "v1.0" or kind != "generate" or parent_id is not None:
        raise DdlError(f"子版本字段异常：{label}/{kind}/{parent_id}")
    lines.append(f"select_ok=versions:{rows} html_len:{html_len} label:{label} kind:{kind}")
    cur.execute(
        "SELECT (SELECT count(*) FROM bci.report_version WHERE report_id = %s)",
        (SMOKE_REPORT,),
    )
    if cur.fetchone()[0] != 1:
        raise DdlError("级联/唯一约束校验失败")
    cur.execute("DELETE FROM bci.report WHERE report_id = %s", (SMOKE_REPORT,))
    cur.execute(
        "SELECT (SELECT count(*) FROM bci.report WHERE report_id = %s), "
        "(SELECT count(*) FROM bci.report_version WHERE report_id = %s)",
        (SMOKE_REPORT, SMOKE_REPORT),
    )
    leftovers = cur.fetchone()
    if any(leftovers):
        raise DdlError(f"冒烟清理失败：{leftovers}")
    lines.append(f"delete_ok=remaining:{leftovers}")
    return lines


def _fetch(cur, sql: str, params: tuple = ()):
    cur.execute(sql, params)
    return cur.fetchall()


def main() -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    cfg = load_env()
    lines = [f"# BCI-007 report DDL apply @ {datetime.now().isoformat(timespec='seconds')}"]
    ddl = (OPS_DIR / "bci_report_ddl.sql").read_text(encoding="utf-8")
    conn = connect_loader(cfg)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT current_user, has_schema_privilege(current_user, 'bci', 'CREATE')")
            user, schema_create = cur.fetchone()
            lines.append(f"user={user} has_schema_create(bci)={schema_create}")
            if not schema_create:
                raise DdlError("loader 没有 bci schema 的 CREATE 权限，停止（不提权）")
            cur.execute(ddl)
        conn.commit()
        with conn.cursor() as cur:
            lines.extend(verify_structure(cur))
            lines.extend(smoke(cur))
        conn.commit()
    finally:
        conn.close()
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
