# -*- coding: utf-8 -*-
"""分省预测入口：读取 outputs/forecast_{scenario}.csv（全国P50），
份额法下钻到31省，输出 outputs/province_forecast_{scenario}.csv。
两层保证：分省加总==全国（总量）；省内动力和==省总量（结构）。
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ingest.ingest import load_wide  # noqa: E402
from ingest.ingest_province import load_province_wide  # noqa: E402
from province.share_method import forecast_provinces, share_history  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "outputs")
PTS = ["bev", "phev", "hev", "ice"]


def province_structure(window=12):
    """各省动力结构（近window月均值，归一化到和=1）。"""
    nat = load_wide()
    prov_total = load_province_wide("total")
    struct = pd.DataFrame(index=prov_total.columns)
    for pt in PTS:
        prov_pt = load_province_wide(pt)
        struct[pt] = prov_pt.tail(window).mean() / prov_total.tail(window).mean()
    return struct.div(struct.sum(axis=1), axis=0)


def run(scenario="base"):
    fc = pd.read_csv(os.path.join(OUT, "forecast_%s.csv" % scenario), index_col=0)
    nat_fc = fc[["total_p50"]].rename(columns={"total_p50": "total"})

    nat_hist = load_wide()["total"]
    sh = share_history(load_province_wide("total"), nat_hist)
    result = forecast_provinces(nat_fc, sh)  # ym, province, total

    struct = province_structure()
    for pt in PTS:
        result[pt] = [t * struct.loc[p, pt]
                      for t, p in zip(result["total"], result["province"])]
    result = result[["ym", "province", "total"] + PTS]

    # 校验：分省加总 == 全国
    chk = result.groupby("ym")["total"].sum()
    ok = (chk - nat_fc["total"]).abs().max() < 1.0
    out_path = os.path.join(OUT, "province_forecast_%s.csv" % scenario)
    result.to_csv(out_path, index=False, encoding="utf-8-sig")

    y27 = result[result.ym >= "2027-01"]
    top = y27.groupby("province")["total"].sum().sort_values(ascending=False).head(5)
    print("[%s] 2027分省预测 -> %s (加总恒等: %s)" % (scenario, out_path, ok))
    for p, v in top.items():
        print("  %s: %.1f万辆" % (p, v / 1e4))
    return result


if __name__ == "__main__":
    for s in ["base", "bull", "bear"]:
        run(s)
