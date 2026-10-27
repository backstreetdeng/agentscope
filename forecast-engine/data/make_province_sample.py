# -*- coding: utf-8 -*-
"""生成分省×动力月度模拟数据（占位）：province_monthly.csv
结构：31省 × 69月 × 5序列，与全国数据恒等（分省加总=全国）。
省份份额与NEV渗透系数按真实市场特征设置（数值为模拟占位）。
"""
import os

import numpy as np
import pandas as pd

RNG = np.random.default_rng(7)

# 省份零售份额（近似2025，生成器内部归一化）
SHARE = {
    "广东": 0.105, "浙江": 0.075, "江苏": 0.075, "山东": 0.065, "河南": 0.055,
    "四川": 0.050, "上海": 0.038, "河北": 0.040, "安徽": 0.035, "湖南": 0.035,
    "湖北": 0.035, "福建": 0.030, "北京": 0.028, "陕西": 0.025, "广西": 0.025,
    "重庆": 0.025, "江西": 0.025, "辽宁": 0.023, "云南": 0.020, "山西": 0.018,
    "贵州": 0.016, "吉林": 0.015, "天津": 0.015, "内蒙古": 0.014, "黑龙江": 0.012,
    "新疆": 0.012, "甘肃": 0.008, "海南": 0.007, "宁夏": 0.004, "青海": 0.003,
    "西藏": 0.001,
}

# NEV渗透相对系数（南方沿海/限购城市高，东北西北低）
NEV_ADJ = {
    "上海": 1.25, "海南": 1.20, "广东": 1.15, "浙江": 1.12, "江苏": 1.10,
    "安徽": 1.08, "北京": 1.05, "广西": 1.05, "天津": 1.02, "福建": 1.00,
    "河南": 1.00, "江西": 0.98, "山东": 0.98, "四川": 0.97, "湖南": 0.97,
    "贵州": 0.88, "云南": 0.85, "湖北": 0.95, "河北": 0.95, "重庆": 0.95,
    "山西": 0.90, "陕西": 0.92, "宁夏": 0.85, "甘肃": 0.80, "青海": 0.75,
    "内蒙古": 0.75, "辽宁": 0.75, "吉林": 0.72, "黑龙江": 0.68, "新疆": 0.70,
    "西藏": 0.50,
}


def main():
    base = os.path.dirname(os.path.abspath(__file__))
    nat = pd.read_csv(os.path.join(base, "retail_monthly.csv"))
    provs = list(SHARE.keys())
    rows = []
    for _, r in nat.iterrows():
        raw = {}
        for p in provs:
            s = SHARE[p] * (1 + RNG.normal(0, 0.04))
            bev = r.bev * s * NEV_ADJ[p]
            phev = r.phev * s * NEV_ADJ[p]
            hev = r.hev * s * (2 - NEV_ADJ[p])
            ice = r.ice * s * (2 - NEV_ADJ[p])
            raw[p] = [bev, phev, hev, ice]
        for k, col in enumerate(["bev", "phev", "hev", "ice"]):
            tot = sum(raw[p][k] for p in provs)
            for p in provs:
                raw[p][k] *= r[col] / tot
        for p in provs:
            bev, phev, hev, ice = raw[p]
            rows.append({"ym": r.ym, "province": p,
                         "bev": int(round(bev)), "phev": int(round(phev)),
                         "hev": int(round(hev)), "ice": int(round(ice))})

    df = pd.DataFrame(rows)
    out = os.path.join(base, "province_monthly.csv")
    df.to_csv(out, index=False, encoding="utf-8")
    print("OK: %d rows (%d省 x %d月) -> %s" % (len(df), len(provs), len(nat), out))
    chk = df.groupby("ym")[["bev", "phev", "hev", "ice"]].sum()
    nat_i = nat.set_index("ym")
    diff = (chk - nat_i[["bev", "phev", "hev", "ice"]]).abs().max().max()
    print("分省加总与全国最大偏差: %d 辆（取整误差级）" % diff)


if __name__ == "__main__":
    main()
