"""New-car presentation uses the agent's remote MCP catalog, never local PG/8776."""
from __future__ import annotations

import asyncio
import json


def decode(result) -> dict:
    if result.isError:
        raise ValueError("新车 MCP 工具查询失败")
    for block in result.content:
        if getattr(block, "type", "") == "text":
            data = json.loads(block.text)
            if data.get("success") is True:
                return data
    raise ValueError("新车 MCP 未返回成功数据")


def map_model(row: dict) -> dict:
    return {"id": row.get("id", row.get("model_style_id")),
            "style_name": row.get("style_name") or row.get("model_style_name"),
            "year": row.get("launch_year"), "month": row.get("launch_month"),
            "launch_date": row.get("launch_date"),
            **{key: row.get(key) for key in ("region", "brand", "model", "attr", "series")},
            "cat": row.get("vehicle_type"), "level": row.get("vehicle_level"),
            "corp": row.get("enterprise"), "energy": row.get("energy_type"),
            "batch": row.get("import_batch")}


def map_planned(row: dict) -> dict:
    aliases = {"level": "vehicle_level", "cat": "vehicle_type", "energy": "energy_type",
               "status": "market_status", "year": "launch_year", "month": "launch_month",
               "quarter": "launch_quarter"}
    return {**row, **{key: row.get(value) for key, value in aliases.items()}}


async def read_pages(session, tool: str, expected: int, planned: bool = False) -> list[dict]:
    rows, seen, offset = [], set(), 0
    while True:
        page = decode(await session.call_tool(tool, {"params": {
            "limit": 100, "offset": offset, "response_format": "json"}}))
        if page.get("total_count") != expected:
            raise ValueError("正式库在读取期间发生变化，请刷新重试")
        items = page.get("items", [])
        for row in items:
            key = (row.get("batch"), row.get("source_row")) if planned else row.get("id")
            if key is None or key in seen:
                raise ValueError("新车 MCP 返回缺失或重复的记录标识")
            seen.add(key)
        rows.extend(items)
        if not page.get("has_more"):
            break
        next_offset = page.get("next_offset")
        if not items or not isinstance(next_offset, int) or next_offset <= offset or next_offset > 100000:
            raise ValueError("新车 MCP 分页进度异常")
        offset = next_offset
    if len(rows) != expected:
        raise ValueError("新车 MCP 分页数量不一致")
    return rows


def summarize(rows: list[dict], status: dict) -> dict:
    periods = sorted({f"{r['year']:04d}-{r['month']:02d}" for r in rows if r.get("year") and r.get("month")})
    latest_month = periods[-1] if periods else None
    return {"spec_total": len(rows),
            "series_total": len({(r.get("brand"), r["model"]) for r in rows if r.get("model")}),
            "recent_total": sum(f"{r['year']:04d}-{r['month']:02d}" == latest_month for r in rows if r.get("year") and r.get("month")),
            "latest_launch_date": latest_month, "latest_month": latest_month,
            "brand_total": len({r["brand"] for r in rows if r.get("brand")}),
            "planned_total": status.get("planned_count"), "field_count": 15,
            "latest_batch": status.get("latest_batch"),
            "last_successful_import": status.get("last_successful_import"),
            "storage_table": "new_car_model", "storage_backend": "postgres",
            "date_precision": "month", "source": "正式发布库 new_car_model（基础款型）"}


async def fetch_new_car(config: dict, operation: str = "list", model: str = "", brand: str = "", energy_type: str = "") -> dict:
    from .market_data_api import get_data, get_snapshot
    if operation == "dashboard":
        return await get_data(config, "new-cars/dashboard", plugin_id="new-car")
    if operation == "sales":
        data = await get_data(config, "new-cars/sales", params={"model": model,"brand":brand,"energy_type":energy_type}, plugin_id="new-car")
        rows = [{"month": row["month"], "index": row.get("month_index"), "sales": row["sales"]} for row in data["items"]]
        return {"success": True, "source": "api", "model": model, "available": bool(rows), "rows": rows, "total": data["total_sales"], "peak": data["peak_sales"],
                **{k:data.get(k) for k in ('energy_types','series','batch','matched_model','legacy_months_retained','revisions')}}
    resource = "new-cars/planned" if operation == "planned" else "new-cars/detail" if operation == "detail" else "new-cars"
    params = {key: value for key, value in {"model": model, "brand": brand}.items() if value}
    data = await get_snapshot(config, resource, params=params, plugin_id="new-car")
    rows = data.get("rows", data.get("items", []))
    mapped = [map_planned(row) if operation == "planned" else map_model(row) for row in rows]
    return {"success": True, "source": "api", "storage": "postgres", "total": len(mapped), "rows": mapped, "batch": max((str(row.get('batch') or '') for row in mapped),default=''), "data_version": data.get("data_version", "")}


async def load_new_car(config: dict, operation: str = "list", model: str = "", brand: str = "", energy_type: str = "") -> dict:
    return await asyncio.wait_for(fetch_new_car(config, operation, model, brand,energy_type), timeout=90)
