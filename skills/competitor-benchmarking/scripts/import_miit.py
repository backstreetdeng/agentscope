"""款型配置信息导入 + 对账（MKT-001 / S4 交付）。

输入契约（CSV，UTF-8，含表头）：
  base 表文件列：model_name, type_name, car_id, file_name, create_time（YYYY-MM-DD 或含时间）
  detail 表文件列：model_name, type_name, car_id, pz_name, pz_value, create_time

输出：
  写入 miit.ods_pz_base_info / miit.ods_pz_detail_info（目标库，写账户由调用方持有）
  返回对账报告 dict

副作用：
  幂等写入：base 按 car_id、detail 按 (car_id, pz_name) 跳过库内已存在记录并计数
  对账：base 与 detail 的 car_id 一致性校验（EXCEPT），不一致返回差值计数（不中断导入）

安全：
  本脚本不读项目 .env 凭据；dsn 由调用方显式传入（连接串或含 host/port/dbname/user/password 的 dict）。
  采集文件列映射如有出入，调整本文件顶部的列名常量即可，不修改库表结构。
"""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras

SCHEMA = "miit"
BASE_COLS = ("model_name", "type_name", "car_id", "file_name", "create_time")
DETAIL_COLS = ("model_name", "type_name", "car_id", "pz_name", "pz_value", "create_time")


def _connect(dsn: Any) -> psycopg2.extensions.connection:
    if isinstance(dsn, dict):
        return psycopg2.connect(connect_timeout=15, **dsn)
    return psycopg2.connect(dsn, connect_timeout=15)


def _read_rows(path: str, cols: tuple[str, ...]) -> list[dict[str, str]]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        missing = [c for c in cols if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{Path(path).name} 缺少列：{missing}")
        return [dict(row) for row in reader]


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _reconcile(conn: psycopg2.extensions.connection) -> dict[str, Any]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(f'SELECT count(DISTINCT car_id) AS n FROM "{SCHEMA}".ods_pz_base_info')
        base_count = cur.fetchone()["n"]
        cur.execute(f'SELECT count(DISTINCT car_id) AS n FROM "{SCHEMA}".ods_pz_detail_info')
        detail_count = cur.fetchone()["n"]
        cur.execute(
            f'SELECT count(*) AS n FROM ('
            f'SELECT car_id FROM "{SCHEMA}".ods_pz_base_info '
            f'EXCEPT SELECT car_id FROM "{SCHEMA}".ods_pz_detail_info) t'
        )
        missing_detail = cur.fetchone()["n"]
        cur.execute(
            f'SELECT count(*) AS n FROM ('
            f'SELECT car_id FROM "{SCHEMA}".ods_pz_detail_info '
            f'EXCEPT SELECT car_id FROM "{SCHEMA}".ods_pz_base_info) t'
        )
        missing_base = cur.fetchone()["n"]
    return {
        "base_car_count": base_count,
        "detail_car_count": detail_count,
        "missing_in_detail": missing_detail,
        "missing_in_base": missing_base,
        "consistent": missing_detail == 0 and missing_base == 0,
    }


def import_files(base_path: str, detail_path: str, dsn: Any) -> dict:
    """导入款型基础信息与明细信息，幂等写入并对账。

    dsn：psycopg2 连接串，或 {"host","port","dbname","user","password"} dict（写账户）。
    """
    base_rows = _read_rows(base_path, BASE_COLS)
    detail_rows = _read_rows(detail_path, DETAIL_COLS)

    conn = _connect(dsn)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # 幂等：查库内已存在的 car_id（base）与 (car_id, pz_name)（detail）
            cur.execute(f'SELECT car_id FROM "{SCHEMA}".ods_pz_base_info')
            existing_base = {r["car_id"] for r in cur.fetchall()}
            cur.execute(f'SELECT car_id, pz_name FROM "{SCHEMA}".ods_pz_detail_info')
            existing_detail = {(r["car_id"], r["pz_name"]) for r in cur.fetchall()}

            new_base = []
            seen_base: set[str] = set()
            for r in base_rows:
                car_id = (r.get("car_id") or "").strip()
                if not car_id or car_id in existing_base or car_id in seen_base:
                    continue
                seen_base.add(car_id)
                new_base.append((
                    r.get("model_name"), r.get("type_name"), car_id,
                    r.get("file_name"), r.get("create_time"),
                ))

            new_detail = []
            seen_detail: set[tuple[str, str]] = set()
            for r in detail_rows:
                car_id = (r.get("car_id") or "").strip()
                pz_name = (r.get("pz_name") or "").strip()
                if not car_id or not pz_name:
                    continue
                key = (car_id, pz_name)
                if key in existing_detail or key in seen_detail:
                    continue
                seen_detail.add(key)
                new_detail.append((
                    r.get("model_name"), r.get("type_name"), car_id,
                    pz_name, r.get("pz_value"), r.get("create_time"),
                ))

            if new_base:
                psycopg2.extras.execute_values(
                    cur,
                    f'INSERT INTO "{SCHEMA}".ods_pz_base_info '
                    f'(model_name, type_name, car_id, file_name, create_time) VALUES %s',
                    new_base,
                )
            if new_detail:
                psycopg2.extras.execute_values(
                    cur,
                    f'INSERT INTO "{SCHEMA}".ods_pz_detail_info '
                    f'(model_name, type_name, car_id, pz_name, pz_value, create_time) VALUES %s',
                    new_detail,
                )
            conn.commit()

        report = _reconcile(conn)
        report.update({
            "success": True,
            "base_file_sha256": _sha256_file(base_path),
            "detail_file_sha256": _sha256_file(detail_path),
            "inserted_base": len(new_base),
            "inserted_detail": len(new_detail),
            "skipped_base_duplicates": len(base_rows) - len(new_base),
            "skipped_detail_duplicates": len(detail_rows) - len(new_detail),
        })
        return report
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit("本脚本作为库使用：import_files(base_path, detail_path, dsn)。")
