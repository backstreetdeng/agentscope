# -*- coding: utf-8 -*-
"""M1 基线：季节naive + 年化漂移。
pred(t) = y(t-12) * (y(last)/y(last-12))^(1/12)  —— 每列独立、递归多步。
"""
import numpy as np


def m1_forecast(hist, horizon_yms, col):
    """hist: 宽表(index=ym升序)；col: 目标列；返回 ndarray。"""
    vals = list(hist[col].values)
    if len(vals) >= 13 and vals[-13] > 0:
        drift = (vals[-1] / vals[-13]) ** (1.0 / 12.0)
    else:
        drift = 1.0
    out = []
    for _ in horizon_yms:
        base = vals[-12] if len(vals) >= 12 else vals[-1]
        pred = max(base * drift, 1.0)
        out.append(pred)
        vals.append(pred)
    return np.array(out)
