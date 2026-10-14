"""New-car model, launch plan and sales MCP server."""

from __future__ import annotations

import asyncio
import os
from datetime import date

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from .shared import (
    READ_ONLY_ANNOTATIONS,
    PageInput,
    ResponseFormat,
    paginated,
    query_rows,
    query_scalar,
    render_response,
    run_server,
    single,
)


class NewCarSearchInput(PageInput):
    brand: str = Field(default="", max_length=80)
    model: str = Field(default="", max_length=100)
    enterprise: str = Field(default="", max_length=100)
    energy_type: str = Field(default="", max_length=50)
    vehicle_type: str = Field(default="", max_length=50)
    launch_start: date | None = None
    launch_end: date | None = None


class PlannedCarSearchInput(PageInput):
    brand: str = Field(default="", max_length=80)
    model: str = Field(default="", max_length=100)
    market_status: str = Field(default="", max_length=50)
    energy_type: str = Field(default="", max_length=50)
    launch_year: int | None = Field(default=None, ge=2000, le=2100)
    launch_quarter: str = Field(default="", max_length=20)


class ModelInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    model: str = Field(min_length=1, max_length=100)
    brand: str = Field(default="", max_length=100)
    energy_type: str = Field(default="", max_length=100)
    response_format: ResponseFormat = ResponseFormat.JSON


class ModelDetailInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    model_style_id: str = Field(default="", max_length=100)
    model: str = Field(default="", max_length=100)
    response_format: ResponseFormat = ResponseFormat.JSON


class LaunchCalendarInput(PageInput):
    start_date: date
    end_date: date
    energy_type: str = Field(default="", max_length=50)
    brand: str = Field(default="", max_length=80)


class CompareModelsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    models: list[str] = Field(min_length=2, max_length=10)
    response_format: ResponseFormat = ResponseFormat.JSON


def _like(value: str) -> str:
    return f"%{value}%"


def _search_models(params: NewCarSearchInput) -> list[dict]:
    clauses = ["TRUE"]
    values: list[object] = []
    for column, value in (
        ("brand", params.brand), ("model", params.model), ("enterprise", params.enterprise),
        ("energy_type", params.energy_type), ("vehicle_type", params.vehicle_type),
    ):
        if value:
            clauses.append(f"{column} ILIKE %s")
            values.append(_like(value))
    if params.launch_start:
        clauses.append("launch_date >= %s")
        values.append(params.launch_start)
    if params.launch_end:
        clauses.append("launch_date <= %s")
        values.append(params.launch_end)
    sql = f"""
        SELECT model_style_id AS id, launch_year, launch_month, launch_date, region,
               brand, model, attr, vehicle_type, vehicle_level, series, enterprise,
               energy_type, import_batch, style_name
        FROM new_car_model
        WHERE {' AND '.join(clauses)}
        ORDER BY launch_date DESC NULLS LAST, model_style_id
    """
    return query_rows(sql, tuple(values))


def _search_planned(params: PlannedCarSearchInput) -> list[dict]:
    clauses = ["TRUE"]
    values: list[object] = []
    for column, value in (
        ("brand", params.brand), ("model_code", params.model), ("market_status", params.market_status),
        ("energy_type", params.energy_type), ("launch_quarter", params.launch_quarter),
    ):
        if value:
            clauses.append(f"{column} ILIKE %s")
            values.append(_like(value))
    if params.launch_year:
        clauses.append("launch_year = %s")
        values.append(params.launch_year)
    sql = f"""
        SELECT source_batch AS batch, source_row, origin_series AS series, enterprise,
               brand, model_code AS model, attr, vehicle_level, vehicle_type, energy_type,
               msrp, price_band, market_status, launch_year, launch_month, launch_quarter,
               selling_points, competitor, notes
        FROM planned_new_car
        WHERE {' AND '.join(clauses)}
        ORDER BY source_batch DESC, source_row
    """
    return query_rows(sql, tuple(values))


def build_server() -> FastMCP:
    mcp = FastMCP(
        "new_car_mcp",
        instructions="只读查询乘用车上市车型、规划车型、上市日历与上市后销量。",
        host=os.getenv("MCP_HOST", "0.0.0.0"),
        port=int(os.getenv("MCP_PORT", "8813")),
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
    )

    @mcp.tool(name="new_car_get_status", annotations=READ_ONLY_ANNOTATIONS)
    async def new_car_get_status(response_format: ResponseFormat = ResponseFormat.JSON) -> str:
        """Return new-car table counts and latest import batches from PostgreSQL."""
        try:
            model_count, planned_count, latest_batch = await asyncio.gather(
                asyncio.to_thread(query_scalar, "SELECT COUNT(*) FROM new_car_model"),
                asyncio.to_thread(query_scalar, "SELECT COUNT(*) FROM planned_new_car"),
                asyncio.to_thread(query_scalar, "SELECT MAX(import_batch) FROM new_car_model"),
            )
            payload = {"success": True, "data_source": "new_car", "status": "ready", "model_count": model_count, "planned_count": planned_count, "latest_batch": latest_batch}
        except Exception as exc:
            payload = {"success": False, "data_source": "new_car", "status": "unavailable", "error": f"新车数据库暂不可用：{type(exc).__name__}"}
        return render_response(payload, response_format)

    @mcp.tool(name="new_car_search_models", annotations=READ_ONLY_ANNOTATIONS)
    async def new_car_search_models(params: NewCarSearchInput) -> str:
        """Search launched models by brand, model, enterprise, energy, type and launch dates."""
        rows = await asyncio.to_thread(_search_models, params)
        return render_response(paginated(rows, params.limit, params.offset, source="new_car"), params.response_format)

    @mcp.tool(name="new_car_search_planned_models", annotations=READ_ONLY_ANNOTATIONS)
    async def new_car_search_planned_models(params: PlannedCarSearchInput) -> str:
        """Search planned or upcoming models by brand, status, energy and launch period."""
        rows = await asyncio.to_thread(_search_planned, params)
        return render_response(paginated(rows, params.limit, params.offset, source="new_car_planned"), params.response_format)

    @mcp.tool(name="new_car_get_model_detail", annotations=READ_ONLY_ANNOTATIONS)
    async def new_car_get_model_detail(params: ModelDetailInput) -> str:
        """Return complete structured fields for one model style ID or exact model name."""
        if not params.model_style_id and not params.model:
            return render_response({"success": False, "data_source": "new_car", "error": "model_style_id 和 model 至少提供一个。"}, params.response_format)
        if params.model_style_id:
            rows = await asyncio.to_thread(query_rows, "SELECT * FROM new_car_model WHERE model_style_id=%s LIMIT 1", (params.model_style_id,))
        else:
            rows = await asyncio.to_thread(query_rows, "SELECT * FROM new_car_model WHERE model=%s ORDER BY launch_date DESC NULLS LAST LIMIT 1", (params.model,))
        return render_response(single(rows[0] if rows else None, source="new_car"), params.response_format)

    @mcp.tool(name="new_car_get_launch_calendar", annotations=READ_ONLY_ANNOTATIONS)
    async def new_car_get_launch_calendar(params: LaunchCalendarInput) -> str:
        """Return launched models in a date range for an AI-generated launch calendar."""
        search = NewCarSearchInput(
            brand=params.brand, energy_type=params.energy_type, launch_start=params.start_date,
            launch_end=params.end_date, limit=100, offset=0, response_format=params.response_format,
        )
        rows = await asyncio.to_thread(_search_models, search)
        return render_response(paginated(rows, params.limit, params.offset, source="new_car_calendar"), params.response_format)

    @mcp.tool(name="new_car_get_monthly_sales", annotations=READ_ONLY_ANNOTATIONS)
    async def new_car_get_monthly_sales(params: ModelInput) -> str:
        """Return actual monthly sales for one model, including total and peak sales."""
        from .api_read_models import new_car_sales
        payload=await asyncio.to_thread(new_car_sales,params.model_dump(exclude={'response_format'}))
        payload.update(data_source='new_car_sales',total_count=len(payload['items']))
        return render_response(payload, params.response_format)

    @mcp.tool(name="new_car_compare_models", annotations=READ_ONLY_ANNOTATIONS)
    async def new_car_compare_models(params: CompareModelsInput) -> str:
        """Compare core model fields and available sales summaries for two to ten models."""
        comparisons = []
        for model_name in params.models:
            from .api_read_models import new_car_sales
            model_rows, sales_data = await asyncio.gather(
                asyncio.to_thread(query_rows, "SELECT * FROM new_car_model WHERE model=%s ORDER BY launch_date DESC NULLS LAST LIMIT 1", (model_name,)),
                asyncio.to_thread(new_car_sales, {'model':model_name}),
            )
            comparisons.append({"model": model_name, "detail": model_rows[0] if model_rows else None, "sales_total": sales_data['total_sales'], "sales_months": len(sales_data['items'])})
        return render_response({"success": True, "data_source": "new_car", "comparisons": comparisons}, params.response_format)

    return mcp


mcp = build_server()


if __name__ == "__main__":
    run_server(mcp, 8813)

