# -*- coding: utf-8 -*-
"""W2+W5：滚动起点回测。
协议：最近12个origin，horizon=1..6月，逐月评估。
模型：M1(季节naive) / M2(LightGBM分位数) / M3(Chronos基础模型,零样本)
      / ENS(M2+M3等权集成, 对账后)。
指标：MAPE + P10-P90区间覆盖率。
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from features.build_features import COLS  # noqa: E402
from ingest.ingest import load_wide  # noqa: E402
from models.m1_baseline import m1_forecast  # noqa: E402
from models.m2_lgbm_quantile import M2Quantile  # noqa: E402
from reconcile.reconcile import reconcile  # noqa: E402

H = 6
N_ORIGINS = 12


def try_load_m3():
    try:
        from models.m3_chronos import M3Chronos
        return M3Chronos()
    except Exception as e:  # noqa: BLE001
        print("[M3跳过] %s" % e)
        return None


def m3_forecast_frame(m3, train, horizon):
    recs = {}
    for c in COLS:
        pred = m3.predict(train[c].values, H)
        for q in (0.1, 0.5, 0.9):
            recs[(c, q)] = pred[q]
    fc = pd.DataFrame(recs, index=horizon)
    fc.columns = pd.MultiIndex.from_tuples(fc.columns)
    return fc


def evaluate(verbose=True):
    df = load_wide()
    n = len(df)
    start = max(24, n - N_ORIGINS - H + 1)
    origins = [i for i in range(start, n - H + 1)]
    models = ["m1", "m2", "m3", "ens"]
    m3 = try_load_m3()
    if m3 is None:
        models = ["m1", "m2"]
    err = {(m, c): [] for m in models for c in COLS}
    cover = {(m, c): [] for m in models if m != "m1" for c in COLS}

    for i in origins:
        train, horizon = df.iloc[:i], list(df.index[i:i + H])
        actual = df.loc[horizon]
        for c in COLS:
            pred = m1_forecast(train, horizon, c)
            err[("m1", c)] += list(np.abs(pred - actual[c].values) / actual[c].values)
        fc2 = M2Quantile().fit(train).predict(train, horizon)
        fc2, _ = reconcile(fc2)
        for c in COLS:
            err[("m2", c)] += list(np.abs(fc2[(c, 0.5)].values - actual[c].values)
                                   / actual[c].values)
            cover[("m2", c)] += list(
                (actual[c].values >= fc2[(c, 0.1)].values)
                & (actual[c].values <= fc2[(c, 0.9)].values))
        if m3 is not None:
            fc3 = m3_forecast_frame(m3, train, horizon)
            fc3, _ = reconcile(fc3)
            fce = (fc2 + fc3) / 2.0
            fce, _ = reconcile(fce)
            for c in COLS:
                err[("m3", c)] += list(np.abs(fc3[(c, 0.5)].values - actual[c].values)
                                       / actual[c].values)
                cover[("m3", c)] += list(
                    (actual[c].values >= fc3[(c, 0.1)].values)
                    & (actual[c].values <= fc3[(c, 0.9)].values))
                err[("ens", c)] += list(np.abs(fce[(c, 0.5)].values - actual[c].values)
                                        / actual[c].values)
                cover[("ens", c)] += list(
                    (actual[c].values >= fce[(c, 0.1)].values)
                    & (actual[c].values <= fce[(c, 0.9)].values))

    if verbose:
        name = {"m1": "M1季节naive", "m2": "M2 LightGBM", "m3": "M3 Chronos",
                "ens": "M2+M3集成"}
        print("=" * 82)
        print("滚动起点回测：origins=%d, horizon=%d月, 逐月评估" % (len(origins), H))
        if m3 is not None:
            print("M3模型: %s" % m3.model_name)
        print("=" * 82)
        head = "%-10s" % "序列" + "".join("%16s" % name[m] for m in models)
        print(head)
        for c in COLS:
            line = "%-10s" % c
            for m in models:
                line += "%15.2f%%" % (100 * np.mean(err[(m, c)]))
            print(line)
        print("-" * 82)
        line = "%-10s" % "区间覆盖"
        for m in models:
            if m != "m1":
                line += "%15.1f%%" % (100 * np.mean(cover[(m, "total")]))
        print(line + "   (total序列, 目标80%±10)")
        best = min(models, key=lambda m: np.mean(err[(m, "total")]))
        print("总量最优: %s (MAPE=%.2f%%)" % (
            name[best], 100 * np.mean(err[(best, "total")])))
        print("注: 模拟占位数据，验证管道；真实数据替换后重跑。")
    return err, cover


if __name__ == "__main__":
    evaluate()
