"""Policy data MCP server（只做协议适配，不直连数据库）。

数据访问统一走 data-api。本文件只保留 FastMCP 工具注册、参数校验、data-api 调用、
字段归一化与渲染。
"""
from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from .protocol import READ_ONLY_ANNOTATIONS, render_response, run_server, single
from .data_api_client import DataApiClient, DataApiError
from .contracts.common import ResponseFormat
from .contracts.policy import (
    PolicyChangeInput,
    PolicyCompareInput,
    PolicyExportInput,
    PolicyIdInput,
    PolicySearchInput,
)


def _as_mcp(payload: dict, data_source: str) -> dict:
    out = dict(payload)
    out.pop("source", None)
    out.setdefault("success", True)
    out["data_source"] = data_source
    return out


def _error_payload(exc: Exception) -> dict:
    if isinstance(exc, DataApiError):
        return {"success": False, "data_source": "policy", "error": str(exc)}
    return {"success": False, "data_source": "policy", "error": f"政策数据暂不可用：{type(exc).__name__}"}


def build_server() -> FastMCP:
    mcp = FastMCP(
        "policy_mcp",
        instructions="只读查询中国汽车促消费政策、政策变化和结构化政策明细。",
        host=os.getenv("MCP_HOST", "0.0.0.0"),
        port=int(os.getenv("MCP_PORT", "8811")),
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
    )

    @mcp.tool(name="policy_get_status", annotations=READ_ONLY_ANNOTATIONS)
    async def policy_get_status(response_format: ResponseFormat = ResponseFormat.JSON) -> str:
        """Return policy source status, effective storage backend, count and version."""
        api = DataApiClient()
        try:
            raw = await api.get("policies/status")
            payload = _as_mcp(raw, "policy")
            payload["source"] = raw.get("source_name", "")
            payload.pop("source_name", None)
        except Exception as exc:
            payload = _error_payload(exc)
        finally:
            await api.close()
        return render_response(payload, response_format)

    @mcp.tool(name="policy_search_policies", annotations=READ_ONLY_ANNOTATIONS)
    async def policy_search_policies(params: PolicySearchInput) -> str:
        """Search policy records by region, dates, type and free-text keyword with pagination."""
        api = DataApiClient()
        try:
            query = {k: v for k, v in params.model_dump().items()
                     if k not in ("response_format", "limit", "offset") and v not in (None, "")}
            query["limit"] = params.limit
            query["offset"] = params.offset
            payload = await api.get("policies", params=query)
            payload = _as_mcp(payload, "policy")
        except Exception as exc:
            payload = _error_payload(exc)
        finally:
            await api.close()
        return render_response(payload, params.response_format)

    @mcp.tool(name="policy_get_policy_detail", annotations=READ_ONLY_ANNOTATIONS)
    async def policy_get_policy_detail(params: PolicyIdInput) -> str:
        """Return the complete structured policy record for one policy record ID."""
        api = DataApiClient()
        try:
            raw = await api.get("policies/detail", params={"record_id": params.record_id})
            item = raw.get("item")
            payload = single(item, source="policy", version=raw.get("data_version", ""))
        except Exception as exc:
            payload = _error_payload(exc)
        finally:
            await api.close()
        return render_response(payload, params.response_format)

    @mcp.tool(name="policy_get_policy_changes", annotations=READ_ONLY_ANNOTATIONS)
    async def policy_get_policy_changes(params: PolicyChangeInput) -> str:
        """List policies whose structured change type/detail match the requested filters."""
        api = DataApiClient()
        try:
            query = {k: v for k, v in params.model_dump().items()
                     if k not in ("response_format", "limit", "offset") and v not in (None, "")}
            query["limit"] = params.limit
            query["offset"] = params.offset
            payload = await api.get("policies/changes", params=query)
            payload = _as_mcp(payload, "policy")
        except Exception as exc:
            payload = _error_payload(exc)
        finally:
            await api.close()
        return render_response(payload, params.response_format)

    @mcp.tool(name="policy_compare_regions", annotations=READ_ONLY_ANNOTATIONS)
    async def policy_compare_regions(params: PolicyCompareInput) -> str:
        """Compare matching policy records across two to ten provinces or cities."""
        api = DataApiClient()
        try:
            query = {k: v for k, v in params.model_dump().items()
                     if k != "response_format" and v not in (None, "")}
            payload = await api.get("policies/compare", params=query)
            payload = _as_mcp(payload, "policy")
        except Exception as exc:
            payload = _error_payload(exc)
        finally:
            await api.close()
        return render_response(payload, params.response_format)

    @mcp.tool(name="policy_export_policies", annotations=READ_ONLY_ANNOTATIONS)
    async def policy_export_policies(params: PolicyExportInput) -> str:
        """Export matching policies to Excel using the approved policy header order."""
        api = DataApiClient()
        try:
            body = params.model_dump(mode="json", exclude={"response_format", "offset"})
            payload = await api.post("policies/export", payload=body)
            payload = _as_mcp(payload, "policy")
        except Exception as exc:
            payload = _error_payload(exc)
        finally:
            await api.close()
        return render_response(payload, params.response_format)

    return mcp


mcp = build_server()


if __name__ == "__main__":
    run_server(mcp, 8811)