# -*- coding: utf-8 -*-
"""W4：L2 事件修正引擎（机械聚合，可审计）。
规则：事件系数只作用于动力分量，随后 total = 各分量之和（保持恒等式）。
每个修正记录 (ym, powertrain, event_id, factor)，供 explain 输出修正链。
"""
import pandas as pd

COMPONENTS = ["bev", "phev", "hev", "ice"]
SCOPE_MAP = {
    "all": ["bev", "phev", "hev", "ice"],
    "nev": ["bev", "phev"],
    "bev": ["bev"], "phev": ["phev"], "hev": ["hev"], "ice": ["ice"],
}


def load_events(path):
    return pd.read_csv(path)


def apply_events(forecast, events, scenario="base"):
    """forecast: DataFrame(index=ym, MultiIndex[col,q])；返回(修正后, 修正链)。"""
    out = forecast.copy()
    log = []
    col_key = "mult_%s" % scenario
    for _, ev in events.iterrows():
        factor = float(ev[col_key])
        scope = SCOPE_MAP.get(ev["scope"], [])
        for ym in out.index:
            if ev["date_start"] <= ym <= ev["date_end"]:
                for c in scope:
                    for q in out.columns.get_level_values(1).unique():
                        out.loc[ym, (c, q)] *= factor
                    log.append({"ym": ym, "powertrain": c,
                                "event_id": ev["event_id"], "factor": factor})
    for ym in out.index:
        for q in out.columns.get_level_values(1).unique():
            out.loc[ym, ("total", q)] = sum(out.loc[ym, (c, q)] for c in COMPONENTS)
    return out, pd.DataFrame(log)
