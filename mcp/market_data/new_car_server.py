"""New-car model, launch plan and sales MCP server（只做协议适配，不直连数据库）。

数据访问统一走 data-api（唯一持有数据库凭据的服务）。本文件只保留：
- FastMCP 工具注册；
- Pydantic 参数校验（contracts）；
- data-api 调用与字段归一化；
- JSON/Markdown 渲染与错误映射。
"""
from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from .protocol import READ_ONLY_ANNOTATIONS, render_response, run_server, single
from .data_api_client import DataApiClient, DataApiError
from .contracts.common import ResponseFormat
from .contracts.new_car import (
    CompareModelsInput,
    LaunchCalendarInput,
    ModelDetailInput,
    ModelInput,
    NewCarSearchInput,
    PlannedCarSearchInput,
)


def _as_mcp(payload: dict, data_source: str) -> dict:
    out = dict(payload)
    out.pop("source", None)
    out.setdefault("success", True)
    out["data_source"] = data_source
    return out


def _error_payload(exc: Exception) -> dict:
    if isinstance(exc, DataApiError):
        return {"success": False, "data_source": "new_car", "error": str(exc)}
    return {"success": False, "data_source": "new_car", "error": f"新车数据暂不可用：{type(exc).__name__}"}


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
        """Return new-car table counts and latest import batches."""
        api = DataApiClient()
        try:
            payload = await api.get("new-cars/status")
            payload = _as_mcp(payload, "new_car")
        except Exception as exc:
            payload = _error_payload(exc)
        finally:
            await api.close()
        return render_response(payload, response_format)

    @mcp.tool(name="new_car_search_models", annotations=READ_ONLY_ANNOTATIONS)
    async def new_car_search_models(params: NewCarSearchInput) -> str:
        """Search launched models by brand, model, enterprise, energy, type and launch dates."""
        api = DataApiClient()
        try:
            query = {k: v for k, v in params.model_dump().items()
                     if k not in ("response_format", "limit", "offset") and v not in (None, "")}
            query["limit"] = params.limit
            query["offset"] = params.offset
            payload = await api.get("new-cars", params=query)
            payload = _as_mcp(payload, "new_car")
        except Exception as exc:
            payload = _error_payload(exc)
        finally:
            await api.close()
        return render_response(payload, params.response_format)

    @mcp.tool(name="new_car_search_planned_models", annotations=READ_ONLY_ANNOTATIONS)
    async def new_car_search_planned_models(params: PlannedCarSearchInput) -> str:
        """Search planned or upcoming models by brand, status, energy and launch period."""
        api = DataApiClient()
        try:
            query = {k: v for k, v in params.model_dump().items()
                     if k not in ("response_format", "limit", "offset") and v not in (None, "")}
            query["limit"] = params.limit
            query["offset"] = params.offset
            payload = await api.get("new-cars/planned", params=query)
            payload = _as_mcp(payload, "new_car_planned")
        except Exception as exc:
            payload = _error_payload(exc)
        finally:
            await api.close()
        return render_response(payload, params.response_format)

    @mcp.tool(name="new_car_get_model_detail", annotations=READ_ONLY_ANNOTATIONS)
    async def new_car_get_model_detail(params: ModelDetailInput) -> str:
        """Return complete structured fields for one model style ID or exact model name."""
        if not params.model_style_id and not params.model:
            return render_response({"success": False, "data_source": "new_car", "error": "model_style_id 和 model 至少提供一个。"}, params.response_format)
        api = DataApiClient()
        try:
            query = {}
            if params.model_style_id:
                query["model_style_id"] = params.model_style_id
            if params.model:
                query["model"] = params.model
            payload = await api.get("new-cars/detail", params=query)
            item = payload.get("item")
            payload = single(item, source="new_car", version=payload.get("data_version", ""))
        except Exception as exc:
            payload = _error_payload(exc)
        finally:
            await api.close()
        return render_response(payload, params.response_format)

    @mcp.tool(name="new_car_get_launch_calendar", annotations=READ_ONLY_ANNOTATIONS)
    async def new_car_get_launch_calendar(params: LaunchCalendarInput) -> str:
        """Return launched models in a date range for an AI-generated launch calendar."""
        api = DataApiClient()
        try:
            query = {"launch_start": params.start_date, "launch_end": params.end_date}
            if params.brand:
                query["brand"] = params.brand
            if params.energy_type:
                query["energy_type"] = params.energy_type
            query["limit"] = params.limit
            query["offset"] = params.offset
            payload = await api.get("new-cars", params=query)
            payload = _as_mcp(payload, "new_car_calendar")
        except Exception as exc:
            payload = _error_payload(exc)
        finally:
            await api.close()
        return render_response(payload, params.response_format)

    @mcp.tool(name="new_car_get_monthly_sales", annotations=READ_ONLY_ANNOTATIONS)
    async def new_car_get_monthly_sales(params: ModelInput) -> str:
        """Return actual monthly sales for one model, including total and peak sales."""
        api = DataApiClient()
        try:
            query = {k: v for k, v in params.model_dump().items()
                     if k != "response_format" and v not in (None, "")}
            payload = await api.get("new-cars/sales", params=query)
            payload = _as_mcp(payload, "new_car_sales")
            payload["total_count"] = len(payload.get("items", []))
        except Exception as exc:
            payload = _error_payload(exc)
        finally:
            await api.close()
        return render_response(payload, params.response_format)

    @mcp.tool(name="new_car_compare_models", annotations=READ_ONLY_ANNOTATIONS)
    async def new_car_compare_models(params: CompareModelsInput) -> str:
        """Compare core model fields and available sales summaries for two to ten models."""
        api = DataApiClient()
        try:
            payload = await api.get("new-cars/compare", params={"models": params.models})
            payload = _as_mcp(payload, "new_car")
        except Exception as exc:
            payload = _error_payload(exc)
        finally:
            await api.close()
        return render_response(payload, params.response_format)

    return mcp


mcp = build_server()


if __name__ == "__main__":
    run_server(mcp, 8813)