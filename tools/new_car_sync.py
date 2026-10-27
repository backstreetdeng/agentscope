#!/usr/bin/env python
"""新车款型数据同步：Excel -> PostgreSQL (192.168.3.146 vectordb.new_car_model)"""
import re
import sys
import os
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
DEFAULT_XLSX = Path(r"E:/AI/migration-backup/5.4 晓亚/乘用车新车监测板块-0921/2026.1-8新车数据TO晓亚冰雨_202609.xlsx")

DDL = """
CREATE TABLE IF NOT EXISTS new_car_model (
    model_style_id  BIGINT PRIMARY KEY,
    launch_year     INT,
    launch_month    INT,
    launch_date     DATE,
    region          TEXT,
    brand           TEXT,
    model           TEXT,
    attr            TEXT,
    vehicle_type    TEXT,
    vehicle_level   TEXT,
    series          TEXT,
    enterprise      TEXT,
    energy_type     TEXT,
    import_batch    TEXT
);
CREATE INDEX IF NOT EXISTS idx_ncm_launch ON new_car_model (launch_year, launch_month);
CREATE INDEX IF NOT EXISTS idx_ncm_attr   ON new_car_model (attr);
CREATE INDEX IF NOT EXISTS idx_ncm_model  ON new_car_model (model);
"""

def parse_year(v):
    m = re.search(r"(\d{4})", str(v or ""))
    return int(m.group(1)) if m else None

def parse_month(v):
    m = re.search(r"(\d{1,2})", str(v or ""))
    n = int(m.group(1)) if m else None
    return n if n and 1 <= n <= 12 else None

def main(xlsx_path: Path, batch: str):
    wb = openpyxl.load_workbook(xlsx_path, read_only=True)
    ws = wb.worksheets[0]
    rows, seen = [], set()
    for r in ws.iter_rows(min_row=2, values_only=True):
        if r[0] is None:
            continue
        sid = int(r[0])
        if sid in seen:
            continue
        seen.add(sid)
        y, m = parse_year(r[1]), parse_month(r[2])
        date = None
        if y and m:
            date = f"{y:04d}-{m:02d}-01"
        rows.append((sid, y, m, date, str(r[3] or ""), str(r[4] or ""), str(r[5] or ""),
                     str(r[6] or ""), str(r[7] or ""), str(r[8] or ""), str(r[9] or ""),
                     str(r[10] or ""), str(r[11] or ""), batch))
    conn = psycopg2.connect(**PG)
    cur = conn.cursor()
    cur.execute(DDL)
    cur.executemany("""
        INSERT INTO new_car_model (model_style_id, launch_year, launch_month, launch_date,
            region, brand, model, attr, vehicle_type, vehicle_level, series, enterprise,
            energy_type, import_batch) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (model_style_id) DO UPDATE SET
            launch_year=EXCLUDED.launch_year, launch_month=EXCLUDED.launch_month,
            launch_date=EXCLUDED.launch_date, region=EXCLUDED.region, brand=EXCLUDED.brand,
            model=EXCLUDED.model, attr=EXCLUDED.attr, vehicle_type=EXCLUDED.vehicle_type,
            vehicle_level=EXCLUDED.vehicle_level, series=EXCLUDED.series,
            enterprise=EXCLUDED.enterprise, energy_type=EXCLUDED.energy_type,
            import_batch=EXCLUDED.import_batch
    """, rows)
    conn.commit()
    cur.execute("SELECT count(*) FROM new_car_model")
    total = cur.fetchone()[0]
    cur.close(); conn.close()
    print(f"imported={len(rows)} dedup_src={len(seen)} total_in_db={total} batch={batch}")

if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_XLSX
    batch = sys.argv[2] if len(sys.argv) > 2 else "202609"
    main(path, batch)
