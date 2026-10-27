# -*- coding: utf-8 -*-
"""生成模拟占位数据：retail_monthly.csv

结构按真实市场特征构造（趋势/季节/春节/政策冲击），数值为模拟，
替换乘联会真实数据时保持相同列结构即可。
列：ym,total,bev,phev,hev,ice （单位：辆）
"""
import os

import numpy as np
import pandas as pd

RNG = np.random.default_rng(42)

# 年度锚点：月均零售总量(辆)、NEV渗透率、NEV中BEV占比、HEV占总比
ANCHORS = {
    2021: (1_670_000, 0.150, 0.82, 0.025),
    2022: (1_710_000, 0.280, 0.77, 0.030),
    2023: (1_810_000, 0.360, 0.69, 0.035),
    2024: (1_910_000, 0.480, 0.64, 0.040),
    2025: (1_920_000, 0.535, 0.61, 0.040),
    2026: (1_770_000, 0.580, 0.59, 0.038),
    2027: (1_730_000, 0.615, 0.58, 0.036),
}

# 月度季节系数（零售口径，近似）
SEASON = {1: 0.80, 2: 0.74, 3: 1.09, 4: 1.02, 5: 1.00, 6: 0.97,
          7: 0.92, 8: 0.95, 9: 1.05, 10: 1.03, 11: 1.08, 12: 1.22}

# 春节所在月（额外-6%）与次月（+3%回补）
CNY = {2021: 2, 2022: 2, 2023: 1, 2024: 2, 2025: 1, 2026: 2}


def year_interp(year, month):
    """年度锚点线性插值到月。"""
    y0, y1 = ANCHORS[year], ANCHORS[year + 1]
    t = (month - 1) / 12.0
    return tuple(a + (b - a) * t for a, b in zip(y0, y1))


def main():
    rows = []
    for year in range(2021, 2027):
        months = range(1, 13) if year < 2026 else range(1, 10)  # 2026截至9月
        for m in months:
            avg_total, nev_pen, bev_share, hev_share = year_interp(year, m)
            total = avg_total * SEASON[m]

            if CNY.get(year) == m:
                total *= 0.94
            elif CNY.get(year, 0) == m - 1:
                total *= 1.03

            # NEV渗透率月度爬升 + 政策事件
            nev_pen += 0.003 * (m - 6.5) / 6.0
            if (year, m) in [(2022, 12), (2025, 12)]:
                nev_pen += 0.06   # 免税末班车冲量
            if (year, m) in [(2023, 1), (2026, 1)]:
                nev_pen -= 0.04   # 退坡后首月坑
            if (year, m) == (2026, 2):
                nev_pen -= 0.02

            nev_pen = float(np.clip(nev_pen, 0.08, 0.72))
            nev = total * nev_pen
            bev = nev * bev_share
            phev = nev - bev
            hev = total * hev_share

            noise = 1 + RNG.normal(0, 0.03)
            bev, phev = bev * noise, phev * noise
            hev *= 1 + RNG.normal(0, 0.03)
            ice = total * noise - bev - phev - hev

            rows.append({
                "ym": f"{year}-{m:02d}",
                "total": int(round(total * noise)),
                "bev": int(round(bev)),
                "phev": int(round(phev)),
                "hev": int(round(hev)),
                "ice": int(round(ice)),
            })

    df = pd.DataFrame(rows)
    df["ice"] = df["total"] - df[["bev", "phev", "hev"]].sum(axis=1)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "retail_monthly.csv")
    df.to_csv(out, index=False, encoding="utf-8")
    print(f"OK: {len(df)} rows -> {out}")
    print(f"范围: {df.ym.iloc[0]} ~ {df.ym.iloc[-1]}")
    d25 = df.loc[df.ym == '2025-12'].iloc[0]
    d26 = df.loc[df.ym == '2026-09'].iloc[0]
    print("2025-12 NEV渗透率: %.1f%%" % (100 * (d25.bev + d25.phev) / d25.total))
    print("2026-09 NEV渗透率: %.1f%%" % (100 * (d26.bev + d26.phev) / d26.total))


if __name__ == "__main__":
    main()
