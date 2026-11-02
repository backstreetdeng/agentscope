"""Rights (权益) MCP server（只做协议适配，不直连 MySQL / PG）。

Phase 5（MCP→data-api 去数据库化 / 权益）：数据访问统一走 data-api 的
`/api/v1/rights/*`（data-api 再经 `cloud_rights.py` 读腾讯云 MySQL）。本文件
只保留 FastMCP 工具注册、Pydantic 参数校验、data-api 调用与字段归一化。
"""
from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from .protocol import READ_ONLY_ANNOTATIONS, render_response, run_server, single
from .data_api_client import DataApiClient, DataApiError
from .contracts.common import ResponseFormat
from .contracts.rights import Export, RightsChangeInput, RightsCompareInput, RightsIdInput, Search


def _as_mcp(payload: dict, data_source: str) -> dict:
    """把 data-api envelope 归一化为 MCP 兼容字段（data_source 而非 source）。"""
    out = dict(payload)
    out.pop("source", None)
    out.setdefault("success", True)
    out["data_source"] = data_source
    return out


def _error_payload(exc: Exception) -> dict:
    if isinstance(exc, DataApiError):
        return {"success": False, "data_source": "rights", "error": str(exc)}
    return {"success": False, "data_source": "rights", "error": f"权益数据暂不可用：{type(exc).__name__}"}


def build_server() -> FastMCP:
    mcp = FastMCP(
        "rights_mcp",
        instructions="只读查询腾讯云每日价格权益监测台账（车企/车型/活动类型/有效期），支持对比与 21 列导出。",
        host=os.getenv("MCP_HOST", "127.0.0.1"),
        port=int(os.getenv("MCP_PORT", "8812")),
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
    )

    @mcp.tool(name="rights_get_status", annotations=READ_ONLY_ANNOTATIONS)
    async def rights_get_status(response_format: ResponseFormat = ResponseFormat.JSON) -> str:
        """Return real MySQL storage, cumulative ledger metrics, batch status and filter options."""
        api = DataApiClient()
        try:
            raw = await api.get("rights/overview")
            status = dict(raw.get("status") or {})
            payload = _as_mcp(status, "rights")
            if status.get("source"):
                payload["source"] = status["source"]
        except Exception as exc:
            payload = _error_payload(exc)
        finally:
            await api.close()
        return render_response(payload, response_format)

    @mcp.tool(name="rights_search_offers", annotations=READ_ONLY_ANNOTATIONS)
    async def rights_search_offers(params: Search) -> str:
        """Search cumulative ledger with database pagination; activity types match any by default."""
        api = DataApiClient()
        try:
            query = {k: v for k, v in params.model_dump().items() if k != "response_format" and v not in (None, "", [])}
            payload = await api.get("rights", params=query)
            payload = _as_mcp(payload, "rights")
        except Exception as exc:
            payload = _error_payload(exc)
        finally:
            await api.close()
        return render_response(payload, params.response_format)

    @mcp.tool(name="rights_get_offer_detail", annotations=READ_ONLY_ANNOTATIONS)
    async def rights_get_offer_detail(params: RightsIdInput) -> str:
        """Get one row by stable MYSQL-primary-key ID; original record numbers may be duplicated."""
        api = DataApiClient()
        try:
            raw = await api.get("rights/detail", params={"record_id": params.record_id})
            payload = single(raw.get("item"), source="rights", version=raw.get("data_version", ""))
        except Exception as exc:
            payload = _error_payload(exc)
        finally:
            await api.close()
        return render_response(payload, params.response_format)

    @mcp.tool(name="rights_get_active_offers", annotations=READ_ONLY_ANNOTATIONS)
    async def rights_get_active_offers(params: Search) -> str:
        """Find offers active on a date (defaults to today); undated rows are unconfirmed."""
        api = DataApiClient()
        try:
            query = {k: v for k, v in params.model_dump().items() if k != "response_format" and v not in (None, "", [])}
            payload = await api.get("rights/active", params=query)
            payload = _as_mcp(payload, "rights")
        except Exception as exc:
            payload = _error_payload(exc)
        finally:
            await api.close()
        return render_response(payload, params.response_format)

    @mcp.tool(name="rights_compare_models", annotations=READ_ONLY_ANNOTATIONS)
    async def rights_compare_models(params: RightsCompareInput) -> str:
        """Compare stored cumulative ledger rows for two to ten model names."""
        api = DataApiClient()
        try:
            query = {"models": params.models}
            if params.active_on:
                query["active_on"] = params.active_on
            payload = await api.get("rights/compare", params=query)
            payload = _as_mcp(payload, "rights")
        except Exception as exc:
            payload = _error_payload(exc)
        finally:
            await api.close()
        return render_response(payload, params.response_format)

    @mcp.tool(name="rights_get_offer_changes", annotations=READ_ONLY_ANNOTATIONS)
    async def rights_get_offer_changes(params: RightsChangeInput) -> str:
        """List only explicit stored change fields, no inferred day-over-day changes."""
        api = DataApiClient()
        try:
            payload = await api.get("rights/changes", params={
                "brand": params.brand, "change_type": params.change_type,
                "limit": params.limit, "offset": params.offset,
            })
            payload = _as_mcp(payload, "rights")
        except Exception as exc:
            payload = _error_payload(exc)
        finally:
            await api.close()
        return render_response(payload, params.response_format)

    @mcp.tool(name="rights_export_offers", annotations=READ_ONLY_ANNOTATIONS)
    async def rights_export_offers(params: Export) -> str:
        """Export the identical query/version to approved 21-column Excel, base64 bytes; refuses truncation."""
        api = DataApiClient()
        try:
            payload = await api.post("rights/export", payload=params.model_dump(mode="json", exclude={"response_format", "offset"}))
            payload = _as_mcp(payload, "rights")
        except Exception as exc:
            payload = _error_payload(exc)
        finally:
            await api.close()
        return render_response(payload, params.response_format)

    return mcp


mcp = build_server()


if __name__ == "__main__":
    run_server(mcp, 8812)