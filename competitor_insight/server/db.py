"""BCI-004 · 数据库连接工具。

只读取项目根的 `.env` 与 `.env.new-car`，不打印凭据。
业务查询使用 `USER_INSIGHT_LOADER_*`；DDL 使用 `NEW_CAR_PG_*`（仅 ops 脚本）。
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import psycopg2

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class DatabaseUnavailable(RuntimeError):
    """数据库不可连接或缺少凭据。"""


def load_env(project_root: Path | None = None) -> dict[str, str]:
    root = Path(project_root or PROJECT_ROOT)
    cfg: dict[str, str] = {}
    for name in (".env", ".env.new-car"):
        path = root / name
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            cfg[key.strip()] = value.strip().strip('"').strip("'")
    return cfg


def connect(cfg: dict[str, str] | None = None, *, timeout: int = 10):
    cfg = cfg or load_env()
    user = cfg.get("USER_INSIGHT_LOADER_USER", "")
    password = cfg.get("USER_INSIGHT_LOADER_PASSWORD", "")
    if not user or not password:
        raise DatabaseUnavailable("缺少 USER_INSIGHT_LOADER_USER / USER_INSIGHT_LOADER_PASSWORD")
    try:
        return psycopg2.connect(
            host=cfg.get("NEW_CAR_PG_HOST", ""),
            port=int(cfg.get("NEW_CAR_PG_PORT", "5432")),
            dbname=cfg.get("NEW_CAR_PG_DATABASE", ""),
            user=user,
            password=password,
            connect_timeout=timeout,
        )
    except psycopg2.Error as exc:
        raise DatabaseUnavailable(f"连接访谈库失败：{exc.__class__.__name__}") from exc


@contextmanager
def transaction(conn) -> Iterator:
    """提交或回滚整个事务；异常时不留半份数据。"""
    try:
        with conn.cursor() as cur:
            yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
