# -*- coding: utf-8 -*-
"""分省份额法（精度路由核心）：
小省份绝对量噪声大 -> 不独立预测，预测"该省占全国份额"（平稳得多），
再乘以全国预测（总量层精度最高），分省加总恒等于全国。
份额估计 = 滚动12月均值 x (1 + 阻尼趋势)，趋势取近6月/前6月变化的一半。
"""
import pandas as pd


def share_history(prov_wide, nat_hist, powertrain="total"):
    """prov_wide: (ym x province) 绝对量；nat_hist: Series(index=ym)。
    返回份额表 (ym x province)。"""
    return prov_wide.div(nat_hist, axis=0)


def estimate_shares(sh, target_ym, damp=0.5, cap=0.10):
    """sh: 份额表(index=ym升序)。target_ym 之前的数据可用。
    返回 Series(province -> share)，和为1。"""
    hist = sh[sh.index < target_ym].tail(12)
    if len(hist) == 0:
        raise ValueError("无历史份额数据")
    shares = hist.mean()
    if len(hist) >= 12:
        recent, prev = hist.tail(6).mean(), hist.head(6).mean()
        trend = ((recent / prev) - 1) * damp
        shares = shares * (1 + trend.clip(-cap, cap))
    total = shares.sum()
    return shares / total


def forecast_provinces(nat_forecast, sh):
    """nat_forecast: DataFrame(index=ym, columns=[powertrain...])（全国P50）。
    sh: 份额表。返回 (ym x province x powertrain) 长表。"""
    out = []
    for ym in nat_forecast.index:
        shares = estimate_shares(sh, ym)
        for prov, s in shares.items():
            rec = {"ym": ym, "province": prov}
            for pt in nat_forecast.columns:
                rec[pt] = nat_forecast.loc[ym, pt] * s
            out.append(rec)
    df = pd.DataFrame(out)
    return df
