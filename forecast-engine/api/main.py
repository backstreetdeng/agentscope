# -*- coding: utf-8 -*-
"""FastAPI 服务（可选）。启动: python api/main.py
端点: GET /indicators  GET /forecast  POST /scenario  GET /explain
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from fastapi import FastAPI
    from pydantic import BaseModel
except ImportError:
    print("缺少 fastapi/pydantic: pip install fastapi uvicorn")
    sys.exit(1)

from agent.tools import (adjust_scenario, explain_forecast,  # noqa: E402
                         query_indicator, run_forecast_tool)

app = FastAPI(title="乘用车市场预测引擎", version="0.1")


@app.get("/indicators")
def indicators(powertrain="total", start=None, end=None):
    return query_indicator(powertrain, start, end)


@app.get("/forecast")
def forecast(scenario="base"):
    return run_forecast_tool(scenario)


class ScenarioReq(BaseModel):
    event_id: str
    mult: float


@app.post("/scenario")
def scenario(req: ScenarioReq):
    return adjust_scenario(req.event_id, req.mult)


@app.get("/explain")
def explain(ym: str, powertrain: str = "total", scenario: str = "base"):
    return explain_forecast(ym, powertrain, scenario)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8807)
