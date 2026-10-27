# -*- coding: utf-8 -*-
"""分省份额法回测：最近6个月，h=1。
对比：份额法(省份额x全国实际) vs 省级季节naive。按省规模分层报告MAPE。
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ingest.ingest import load_wide  # noqa: E402
from ingest.ingest_province import load_province_wide  # noqa: E402
from province.share_method import estimate_shares, share_history  # noqa: E402


def tier(share):
    if share >= 0.05:
        return "大省(>=5%)"
    if share >= 0.02:
        return "中部(2-5%)"
    return "小省(<2%)"


def evaluate(verbose=True):
    nat = load_wide()
    prov = load_province_wide("total")
    sh = share_history(prov, nat["total"])
    eval_months = list(sh.index[-6:])

    err_share = {p: [] for p in prov.columns}
    err_naive = {p: [] for p in prov.columns}
    for ym in eval_months:
        actual = prov.loc[ym]
        shares = estimate_shares(sh, ym)
        pred = shares * nat.loc[ym, "total"]
        hist = prov[prov.index < ym]
        naive = hist.iloc[-12] if len(hist) >= 12 else hist.iloc[-1]
        for p in prov.columns:
            err_share[p].append(abs(pred[p] - actual[p]) / actual[p])
            err_naive[p].append(abs(naive[p] - actual[p]) / actual[p])

    shares_mean = sh.tail(12).mean()
    rows = []
    for p in prov.columns:
        rows.append({"province": p, "tier": tier(shares_mean[p]),
                     "share_mape": 100 * pd.Series(err_share[p]).mean(),
                     "naive_mape": 100 * pd.Series(err_naive[p]).mean()})
    rdf = pd.DataFrame(rows)

    if verbose:
        print("=" * 66)
        print("分省份额法回测：最近%d月, h=1, %d省" % (
            len(eval_months), len(prov.columns)))
        print("=" * 66)
        print("%-12s %6s %14s %16s" % ("层级", "省数", "份额法MAPE", "省级naiveMAPE"))
        for t in ["大省(>=5%)", "中部(2-5%)", "小省(<2%)"]:
            g = rdf[rdf.tier == t]
            if len(g):
                print("%-12s %6d %13.2f%% %15.2f%%" % (
                    t, len(g), g.share_mape.mean(), g.naive_mape.mean()))
        print("-" * 66)
        print("全省平均: 份额法 %.2f%% vs 省级naive %.2f%%" % (
            rdf.share_mape.mean(), rdf.naive_mape.mean()))
        print("注: 模拟占位数据，验证管道；真实数据替换后重跑。")
    return rdf


if __name__ == "__main__":
    evaluate()
