# -*- coding: utf-8 -*-
"""分省数据入库：province_monthly.csv -> indicators（province=省名）。
校验1：省内 bev+phev+hev+ice 自洽（total为计算列）。
校验2：分省加总 == 全国（容差：省数x取整误差）。
"""
import os
import sys
from datetime import datetime

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import init_db  # noqa: E402

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "data", "province_monthly.csv")
SOURCE = "SAMPLE_PROVINCE_PLACEHOLDER"


def ingest_province(df, source=SOURCE):
    conn = init_db()
    now = datetime.now().isoformat(timespec="seconds")
    conn.executemany("DELETE FROM indicators WHERE source=?", [(source,)])
    rows = []
    for _, r in df.iterrows():
        total = r["bev"] + r["phev"] + r["hev"] + r["ice"]
        for pt in ["total", "bev", "phev", "hev", "ice"]:
            sid = "retail.%s" % pt if pt != "total" else "retail.total"
            if pt != "total":
                sid = "retail.%s.%s" % (pt, r["province"])
            else:
                sid = "retail.total.%s" % r["province"]
            val = total if pt == "total" else r[pt]
            rows.append((sid, "retail", pt, r["province"], r["ym"], float(val),
                         source, None, now))
    conn.executemany(
        "INSERT OR REPLACE INTO indicators(series_id,metric,powertrain,province,"
        "ym,value,source,source_url,collected_at) VALUES (?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()
    return len(rows)


def validate_vs_national(df):
    conn = init_db()
    nat = pd.read_sql_query(
        "SELECT ym, value FROM indicators WHERE series_id='retail.total' "
        "AND province='national'", conn)
    conn.close()
    nat = nat.set_index("ym")["value"]
    psum = df.groupby("ym")[["bev", "phev", "hev", "ice"]].sum().sum(axis=1)
    merged = pd.DataFrame({"prov": psum, "nat": nat}).dropna()
    bad = merged[(merged.prov - merged.nat).abs() > 40 * len(df.province.unique())]
    assert bad.empty, "分省加总与全国不符:\n%s" % bad


def load_province_wide(powertrain="total"):
    """返回 DataFrame(index=ym, columns=province)。"""
    conn = init_db()
    df = pd.read_sql_query(
        "SELECT ym, province, value FROM indicators WHERE powertrain=? AND "
        "metric='retail' AND province != 'national' AND source LIKE 'SAMPLE_PROVINCE%'",
        conn, params=(powertrain,))
    conn.close()
    return df.pivot(index="ym", columns="province", values="value").sort_index()


def main():
    df = pd.read_csv(DATA)
    assert (df[["bev", "phev", "hev", "ice"]] > 0).all().all()
    validate_vs_national(df)
    n = ingest_province(df)
    print("分省入库OK: %d省 x %d月 x 5序列 = %d行" % (
        df.province.nunique(), df.ym.nunique(), n // 5))
    print("校验通过: 分省加总 == 全国")


if __name__ == "__main__":
    main()
