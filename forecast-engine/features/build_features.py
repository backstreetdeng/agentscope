# -*- coding: utf-8 -*-
"""特征工厂：滞后/滚动/日历/春节。
设计要点：feature_row(hist, ym) 可在递归预测时用"历史+已预测值"构造特征。
"""
import numpy as np

COLS = ["total", "bev", "phev", "hev", "ice"]

# 春节所在月（农历）：预测期也需维护此表
CNY = {2021: 2, 2022: 2, 2023: 1, 2024: 2, 2025: 1, 2026: 2, 2027: 2, 2028: 1}


def ym_index(ym):
    y, m = ym.split("-")
    return int(y) * 12 + int(m)


def next_ym(ym):
    y, m = map(int, ym.split("-"))
    return f"{y + (m // 12)}-{(m % 12) + 1:02d}"


def feature_row(hist, ym, t0):
    """hist: DataFrame(index=ym升序, columns=COLS)。ym: 待预测月。t0: 时间原点。"""
    y, m = int(ym[:4]), int(ym[5:7])
    f = {
        "month": m,
        "month_sin": np.sin(2 * np.pi * m / 12),
        "month_cos": np.cos(2 * np.pi * m / 12),
        "cny": 1 if CNY.get(y) == m else 0,
        "t": ym_index(ym) - t0,
    }
    for c in COLS:
        s = hist[c].values
        for k in (1, 2, 3, 6, 12):
            f["%s_lag%d" % (c, k)] = s[-k] if len(s) >= k else np.nan
        f["%s_roll3" % c] = float(np.mean(s[-3:]))
        f["%s_roll12" % c] = float(np.mean(s[-12:])) if len(s) >= 12 else np.nan
    return f


def build_training(df, min_hist=12):
    """df: 宽表(index=ym, columns=COLS)。返回 (X, {col: y})。"""
    import pandas as pd
    t0 = ym_index(df.index[0])
    rows, ys = [], {c: [] for c in COLS}
    for i in range(min_hist, len(df)):
        hist = df.iloc[:i]
        ym = df.index[i]
        rows.append(feature_row(hist, ym, t0))
        for c in COLS:
            ys[c].append(df[c].iloc[i])
    return pd.DataFrame(rows), {c: pd.Series(v) for c, v in ys.items()}
