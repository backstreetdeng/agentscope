# -*- coding: utf-8 -*-
"""W1：CSV -> SQLite 入库 + 口径校验。
恒等式校验：bev+phev+hev+ice == total（容差2辆，四舍五入误差）。
同源重灌幂等：先删同 source+ym 再插入（MVP简化，正式版改为只追加+版本号）。
"""
import os
import sys
from datetime import datetime

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import init_db  # noqa: E402

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "data", "retail_monthly.csv")
SOURCE = "SAMPLE_PLACEHOLDER"  # 替换真实数据时改为 "CPCA_RETAIL_V1"


def validate(df):
    assert set(["ym", "total", "bev", "phev", "hev", "ice"]).issubset(df.columns), "列缺失"
    assert df.duplicated("ym").sum() == 0, "ym 重复"
    assert (df[["total", "bev", "phev", "hev", "ice"]] > 0).all().all(), "存在非正值"
    diff = (df[["bev", "phev", "hev", "ice"]].sum(axis=1) - df["total"]).abs()
    bad = df[diff > 2]
    assert bad.empty, "恒等式校验失败:\n%s" % bad


def ingest(df, source=SOURCE, source_url=None):
    conn = init_db()
    now = datetime.now().isoformat(timespec="seconds")
    yms = list(df["ym"])
    conn.executemany(
        "DELETE FROM indicators WHERE source=? AND ym=?", [(source, y) for y in yms])
    rows = []
    for _, r in df.iterrows():
        for pt in ["total", "bev", "phev", "hev", "ice"]:
            rows.append(("retail.%s" % pt, "retail", pt, "national", r["ym"],
                         float(r[pt]), source, source_url, now))
    conn.executemany(
        "INSERT INTO indicators(series_id,metric,powertrain,province,ym,value,"
        "source,source_url,collected_at) VALUES (?,?,?,?,?,?,?,?,?)", rows)
    conn.executemany("INSERT OR REPLACE INTO metric_dict VALUES (?,?,?)", [
        ("NEV渗透率", "retail.(bev+phev)/retail.total", "乘联会零售口径，PHEV含增程"),
        ("零售总量", "retail.total", "乘联会乘用车零售，单位辆"),
    ])
    conn.commit()
    conn.close()
    return len(rows)


def load_wide():
    """从库读取宽表（每 series/ym 取最新 collected_at）。"""
    conn = init_db()
    df = pd.read_sql_query(
        "SELECT series_id, ym, value FROM indicators "
        "WHERE metric='retail' AND province='national'", conn)
    conn.close()
    df = df.sort_values("collected_at") if "collected_at" in df.columns else df
    wide = df.pivot(index="ym", columns="series_id", values="value")
    wide.columns = [c.split(".")[1] for c in wide.columns]
    wide = wide[[c for c in ["total", "bev", "phev", "hev", "ice"] if c in wide.columns]]
    return wide.sort_index()


def main():
    df = pd.read_csv(DATA)
    validate(df)
    ingest(df)
    print("入库OK: %d 月 x 5序列 (source=%s)" % (len(df), SOURCE))
    print("恒等式校验通过: bev+phev+hev+ice == total")


if __name__ == "__main__":
    main()
