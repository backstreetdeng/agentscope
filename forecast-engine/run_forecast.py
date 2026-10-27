# -*- coding: utf-8 -*-
"""端到端预测入口：L1(M2模型) -> L3(对账) -> L2(事件修正) -> 档案落库。
输出：outputs/forecast_{scenario}.csv + forecast_runs 档案 + 控制台摘要。
"""
import json
import os
import sys
from datetime import datetime

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import init_db  # noqa: E402
from events.adjust import apply_events, load_events  # noqa: E402
from features.build_features import COLS, next_ym  # noqa: E402
from ingest.ingest import load_wide  # noqa: E402
from models.m2_lgbm_quantile import M2Quantile  # noqa: E402
from reconcile.reconcile import reconcile  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
EVENTS_PATH = os.path.join(BASE, "data", "events.csv")
OUT_DIR = os.path.join(BASE, "outputs")
MODEL_VERSION = "M2LGBM-Q-v0.1"
SCENARIOS = ("base", "bull", "bear")
USE_M3_ENSEMBLE = False  # True: M2+M3(Chronos)等权集成（见eval/backtest.py对比）


def horizon_months(df, end_ym):
    yms, ym = [], next_ym(df.index[-1])
    while ym <= end_ym:
        yms.append(ym)
        ym = next_ym(ym)
    return yms


def flatten(fc):
    out = pd.DataFrame(index=fc.index)
    for col in fc.columns.get_level_values(0).unique():
        for q, name in [(0.1, "p10"), (0.5, "p50"), (0.9, "p90")]:
            out["%s_%s" % (col, name)] = fc[(col, q)].round(0).astype(int)
    return out


def save_runs(conn, fc, log, scenario, data_cutoff):
    now = datetime.now().isoformat(timespec="seconds")
    run_id = "%s_%s_%s" % (MODEL_VERSION, scenario,
                           now.replace(":", "").replace("-", ""))
    log_rec = log.to_dict("records") if log is not None and len(log) else []
    rows = []
    for ym in fc.index:
        chain = [r for r in log_rec if r["ym"] == ym]
        for c in COLS:
            rows.append((run_id, MODEL_VERSION, data_cutoff, ym, c, scenario,
                         float(fc.loc[ym, (c, 0.1)]), float(fc.loc[ym, (c, 0.5)]),
                         float(fc.loc[ym, (c, 0.9)]),
                         json.dumps(chain, ensure_ascii=False), now))
    conn.executemany(
        "INSERT OR REPLACE INTO forecast_runs(run_id,model_version,data_cutoff,ym,"
        "powertrain,scenario,p10,p50,p90,assumptions,created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    return run_id


def run_pipeline(scenario="base", events_override=None, end_ym="2027-12", save=True):
    assert scenario in SCENARIOS, "scenario 必须是 %s" % str(SCENARIOS)
    df = load_wide()
    horizon = horizon_months(df, end_ym)
    fc = M2Quantile().fit(df).predict(df, horizon)
    if USE_M3_ENSEMBLE:
        from eval.backtest import m3_forecast_frame
        from models.m3_chronos import M3Chronos
        fc3 = m3_forecast_frame(M3Chronos(), df, horizon)
        fc = (fc + fc3) / 2.0
    fc, _ = reconcile(fc)
    events = events_override if events_override is not None else load_events(EVENTS_PATH)
    fc, log = apply_events(fc, events, scenario)

    if save:
        os.makedirs(OUT_DIR, exist_ok=True)
        flatten(fc).to_csv(os.path.join(OUT_DIR, "forecast_%s.csv" % scenario),
                           encoding="utf-8-sig")
        conn = init_db()
        save_runs(conn, fc, log, scenario, df.index[-1])
        conn.commit()
        conn.close()
    return fc, log, df.index[-1]


def summarize(fc, scenario):
    y27 = fc[fc.index >= "2027-01"]
    total = y27[("total", 0.5)].sum()
    nev = y27[("bev", 0.5)].sum() + y27[("phev", 0.5)].sum()
    pen = 100 * nev / total
    lo = y27[("total", 0.1)].sum()
    hi = y27[("total", 0.9)].sum()
    print("[%s情景] 2027年零售预测" % scenario)
    print("  总量 P50 = %.0f 辆 (P10-P90: %.0f ~ %.0f)" % (total, lo, hi))
    print("  NEV渗透率 P50 = %.1f%%" % pen)
    parts = "  ".join("%s=%.0f万" % (c, y27[(c, 0.5)].sum() / 1e4)
                      for c in ["bev", "phev", "hev", "ice"])
    print("  分动力: " + parts)
    return {"total": total, "lo": lo, "hi": hi, "nev_pen": pen}


def main():
    print("数据截止: %s" % load_wide().index[-1])
    for s in SCENARIOS:
        fc, log, cutoff = run_pipeline(s)
        summarize(fc, s)
        print("  事件修正条目: %d (已存预测档案可审计)" % len(log))
        print()
    print("输出: outputs/forecast_{base,bull,bear}.csv")


if __name__ == "__main__":
    main()
