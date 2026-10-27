#!/usr/bin/env python
"""规划新车数据同步：Excel -> PostgreSQL planned_new_car。"""

import os
import sys
from pathlib import Path

import openpyxl
import psycopg2
from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_DIR / ".env", override=False)
load_dotenv(PROJECT_DIR / ".env.new-car", override=False)

PG = dict(
    host=os.getenv("NEW_CAR_PG_HOST", "192.168.3.146"),
    port=int(os.getenv("NEW_CAR_PG_PORT", "5432")),
    dbname=os.getenv("NEW_CAR_PG_DATABASE", "vectordb"),
    user=os.getenv("NEW_CAR_PG_USER", "vectordb"),
    password=os.getenv("NEW_CAR_PG_PASSWORD", ""),
)
DEFAULT_XLSX = Path(
    r"E:/AI/migration-backup/5.4 晓亚/"
    r"乘用车新车监测板块-0921/！0716结果更新版本-2026新车跟踪（含已上市+未上市）.xlsx"
)

DDL = """
CREATE TABLE IF NOT EXISTS planned_new_car (
    source_batch     TEXT NOT NULL,
    source_row       INT NOT NULL,
    origin_series    TEXT,
    enterprise       TEXT,
    brand            TEXT,
    model_code       TEXT,
    attr             TEXT,
    vehicle_level    TEXT,
    vehicle_type     TEXT,
    energy_type      TEXT,
    msrp             TEXT,
    price_band       TEXT,
    market_status    TEXT,
    launch_year      TEXT,
    launch_month     TEXT,
    launch_quarter   TEXT,
    selling_points   TEXT,
    competitor       TEXT,
    notes            TEXT,
    PRIMARY KEY (source_batch, source_row)
);
CREATE INDEX IF NOT EXISTS idx_pnc_brand_model ON planned_new_car (brand, model_code);
CREATE INDEX IF NOT EXISTS idx_pnc_launch ON planned_new_car (launch_year, launch_quarter);
CREATE INDEX IF NOT EXISTS idx_pnc_status ON planned_new_car (market_status);
"""


def text(value):
    return str(value or "").strip()


def main(xlsx_path: Path, batch: str) -> None:
    workbook = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    sheet = workbook["规划新车-0716"]
    rows = []
    for source_row, values in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
        if not values[3]:
            continue
        rows.append((batch, source_row, *(text(value) for value in values[:17])))

    connection = psycopg2.connect(**PG)
    try:
        with connection, connection.cursor() as cursor:
            cursor.execute(DDL)
            cursor.execute("DELETE FROM planned_new_car WHERE source_batch = %s", (batch,))
            cursor.executemany(
                """
                INSERT INTO planned_new_car VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                )
                """,
                rows,
            )
            cursor.execute("SELECT count(*) FROM planned_new_car WHERE source_batch = %s", (batch,))
            total = cursor.fetchone()[0]
    finally:
        connection.close()
    print(f"imported={len(rows)} total_in_batch={total} batch={batch}")


if __name__ == "__main__":
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_XLSX
    source_batch = sys.argv[2] if len(sys.argv) > 2 else "20260716"
    main(source, source_batch)
