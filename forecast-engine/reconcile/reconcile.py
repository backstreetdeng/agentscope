# -*- coding: utf-8 -*-
"""W5-lite：middle-out 对账。
总量预测精度通常最高 -> 分量按比例缩放，使 bev+phev+hev+ice == total(P50)。
量化区间(P10/P90)用相同缩放因子，保持一致性。
"""

COMPONENTS = ["bev", "phev", "hev", "ice"]


def reconcile(forecast):
    """forecast: DataFrame(index=ym, columns=MultiIndex[col,q])，含 total 与分量。"""
    out = forecast.copy()
    scales = {}
    for ym in out.index:
        comp_sum = sum(out.loc[ym, (c, 0.5)] for c in COMPONENTS)
        total_p50 = out.loc[ym, ("total", 0.5)]
        scale = float(total_p50 / comp_sum) if comp_sum > 0 else 1.0
        scales[ym] = scale
        for c in COMPONENTS:
            for q in out.columns.get_level_values(1).unique():
                out.loc[ym, (c, q)] = out.loc[ym, (c, q)] * scale
    return out, scales
