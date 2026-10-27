# -*- coding: utf-8 -*-
"""暴露给网页智能体的4个工具。
网页智能体通过 function calling / MCP 调用；数值计算全部在本引擎内完成，
LLM 只做编排与解释（防幻觉硬边界）。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import init_db  # noqa: E402
from events.adjust import load_events  # noqa: E402
from ingest.ingest import load_wide  # noqa: E402
from run_forecast import EVENTS_PATH, run_pipeline  # noqa: E402


def query_indicator(powertrain="total", start=None, end=None):
    """工具1：指标查询（带来源与采集时间）。"""
    df = load_wide()
    if powertrain not in df.columns:
        return {"error": "未知序列: %s" % powertrain}
    s = df[powertrain]
    if start:
        s = s[s.index >= start]
    if end:
        s = s[s.index <= end]
    conn = init_db()
    meta = conn.execute(
        "SELECT source, collected_at FROM indicators WHERE series_id=? "
        "ORDER BY collected_at DESC LIMIT 1", ("retail.%s" % powertrain,)).fetchone()
    conn.close()
    return {"series": "retail.%s" % powertrain, "unit": "辆",
            "source": meta["source"] if meta else None,
            "collected_at": meta["collected_at"] if meta else None,
            "data": {ym: float(v) for ym, v in s.items()}}


def run_forecast_tool(scenario="base"):
    """工具2：运行预测，返回摘要。"""
    fc, log, cutoff = run_pipeline(scenario)
    y27 = fc[fc.index >= "2027-01"]
    total = y27[("total", 0.5)].sum()
    nev = y27[("bev", 0.5)].sum() + y27[("phev", 0.5)].sum()
    return {
        "model_version": "M2LGBM-Q-v0.1", "data_cutoff": cutoff, "scenario": scenario,
        "y2027_total_p50": round(total), "y2027_total_p10": round(y27[("total", 0.1)].sum()),
        "y2027_total_p90": round(y27[("total", 0.9)].sum()),
        "y2027_nev_penetration_pct": round(100 * nev / total, 1),
        "adjustments": len(log)}


def adjust_scenario(event_id, mult):
    """工具3：情景重算——修改某事件系数后重跑基准情景，返回delta。"""
    events = load_events(EVENTS_PATH)
    idx = events.index[events.event_id == event_id]
    if len(idx) == 0:
        return {"error": "未知事件: %s" % event_id}
    before, _, _ = run_pipeline("base", save=False)
    events.loc[idx, "mult_base"] = mult
    after, _, _ = run_pipeline("base", events_override=events, save=False)

    def y27_total(fc):
        return fc[fc.index >= "2027-01"][("total", 0.5)].sum()

    return {"event_id": event_id, "new_mult_base": mult,
            "y2027_total_before": round(y27_total(before)),
            "y2027_total_after": round(y27_total(after)),
            "delta": round(y27_total(after) - y27_total(before))}


def explain_forecast(ym, powertrain="total", scenario="base"):
    """工具4：预测下钻——数据截止/模型版本/事件修正链。"""
    conn = init_db()
    rows = conn.execute(
        "SELECT model_version, data_cutoff, p10, p50, p90, assumptions "
        "FROM forecast_runs WHERE ym=? AND powertrain=? AND scenario=? "
        "ORDER BY created_at DESC LIMIT 1", (ym, powertrain, scenario)).fetchone()
    conn.close()
    if rows is None:
        return {"error": "无预测档案，请先运行 run_forecast"}
    return {"ym": ym, "powertrain": powertrain, "scenario": scenario,
            "model_version": rows["model_version"], "data_cutoff": rows["data_cutoff"],
            "p10": rows["p10"], "p50": rows["p50"], "p90": rows["p90"],
            "adjustment_chain": json.loads(rows["assumptions"] or "[]")}


def demo():
    print("=" * 60)
    print("【工具1】query_indicator: 2026-07~09 纯电零售")
    print(json.dumps(query_indicator("bev", "2026-07", "2026-09"),
                     ensure_ascii=False, indent=2))
    print()
    print("【工具2】run_forecast(base)")
    print(json.dumps(run_forecast_tool("base"), ensure_ascii=False, indent=2))
    print()
    print("【工具3】adjust_scenario: 末班车效应 1.04 -> 1.10")
    print(json.dumps(adjust_scenario("tax_last_train_2027h2", 1.10),
                     ensure_ascii=False, indent=2))
    print()
    print("【工具4】explain_forecast: 2027-12 total")
    print(json.dumps(explain_forecast("2027-12", "total"),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "demo":
        demo()
    else:
        print("用法: python agent/tools.py demo")
