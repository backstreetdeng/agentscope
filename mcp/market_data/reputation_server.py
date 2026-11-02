"""Vehicle reputation and evidence MCP server（只做协议适配，不直连数据库）。

数据访问统一走 data-api（唯一持有数据库凭据的服务）。本文件只保留：
- FastMCP 工具注册；
- Pydantic 参数校验；
- data-api 调用与字段归一化；
- JSON/Markdown 渲染与错误映射。
"""
from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from .protocol import READ_ONLY_ANNOTATIONS, render_response, run_server
from .data_api_client import DataApiClient, DataApiError
from .contracts.common import PageInput, ResponseFormat
from .contracts.reputation import (
    EvidenceInput,
    ReputationCompareInput,
    ReputationModelInput,
    ReputationSearchInput,
    SourceReviewInput,
)


def _as_mcp(payload: dict, data_source: str) -> dict:
    """把 data-api envelope 归一化为 MCP 兼容字段（data_source 而非 source）。"""
    out = dict(payload)
    out.pop("source", None)
    out.setdefault("success", True)
    out["data_source"] = data_source
    return out


def _error_payload(exc: Exception) -> dict:
    if isinstance(exc, DataApiError):
        return {"success": False, "data_source": "reputation", "error": str(exc)}
    return {"success": False, "data_source": "reputation", "error": f"口碑数据暂不可用：{type(exc).__name__}"}


def build_server() -> FastMCP:
    mcp = FastMCP(
        "reputation_mcp",
        instructions="只读查询车型正负面口碑、标签树、评论原文证据和车型对比。",
        host=os.getenv("MCP_HOST", "0.0.0.0"),
        port=int(os.getenv("MCP_PORT", "8814")),
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
    )

    @mcp.tool(name="reputation_get_status", annotations=READ_ONLY_ANNOTATIONS)
    async def reputation_get_status(response_format: ResponseFormat = ResponseFormat.JSON) -> str:
        """Return reputation model count, tagged review count, latest batch and taxonomy version."""
        api = DataApiClient()
        try:
            payload = await api.get("reputation/overview")
            status = payload.get("status", {})
            payload = _as_mcp(status, "reputation")
            payload.update(analysis_storage_tables=["new_car_reputation_taxonomy_summary", "new_car_reputation_review_tag"])
        except Exception as exc:
            payload = _error_payload(exc)
        finally:
            await api.close()
        return render_response(payload, response_format)

    @mcp.tool(name="reputation_search_source_reviews", annotations=READ_ONLY_ANNOTATIONS)
    async def reputation_search_source_reviews(params: SourceReviewInput) -> str:
        """Page current original Autohome and Dongchedi reviews via data-api.

        Exact source model matching; this does not assign reviews based on mentions
        of competitors in text. Returns unique source+review_key records, source counts,
        published/record update dates and platform-native scores, not inferred sentiment.
        """
        api = DataApiClient()
        try:
            query = {k: v for k, v in params.model_dump().items() if k != "response_format" and v not in (None, "")}
            if params.source:
                query["source"] = params.source.value
            payload = await api.get("reputation/reviews", params=query)
            payload = _as_mcp(payload, "reputation_raw")
        except Exception as exc:
            payload = _error_payload(exc)
        finally:
            await api.close()
        return render_response(payload, params.response_format)

    @mcp.tool(name="reputation_search_models", annotations=READ_ONLY_ANNOTATIONS)
    async def reputation_search_models(params: PageInput) -> str:
        """List vehicle models that currently have tagged reputation evidence."""
        api = DataApiClient()
        try:
            payload = await api.get("reputation/models", params={"limit": params.limit, "offset": params.offset})
            payload = _as_mcp(payload, "reputation_models")
        except Exception as exc:
            payload = _error_payload(exc)
        finally:
            await api.close()
        return render_response(payload, params.response_format)

    @mcp.tool(name="reputation_get_model_summary", annotations=READ_ONLY_ANNOTATIONS)
    async def reputation_get_model_summary(params: ReputationModelInput) -> str:
        """Return positive and negative top-level reputation summaries for one model."""
        api = DataApiClient()
        try:
            payload = await api.get("reputation/summary", params={"model": params.model})
            payload = _as_mcp(payload, "reputation")
            payload["model"] = params.model
            payload["available"] = bool(payload.get("groups", {}).get("positive") or payload.get("groups", {}).get("negative"))
        except Exception as exc:
            payload = _error_payload(exc)
        finally:
            await api.close()
        return render_response(payload, params.response_format)

    @mcp.tool(name="reputation_get_topic_tree", annotations=READ_ONLY_ANNOTATIONS)
    async def reputation_get_topic_tree(params: ReputationModelInput) -> str:
        """Return the L1/L2/L3 reputation taxonomy tree with distinct review counts."""
        api = DataApiClient()
        try:
            payload = await api.get("reputation/tree", params={"model": params.model})
            payload = _as_mcp(payload, "reputation")
            payload["model"] = params.model
        except Exception as exc:
            payload = _error_payload(exc)
        finally:
            await api.close()
        return render_response(payload, params.response_format)

    @mcp.tool(name="reputation_search_reviews", annotations=READ_ONLY_ANNOTATIONS)
    async def reputation_search_reviews(params: ReputationSearchInput) -> str:
        """Search tagged source reviews by model, sentiment direction, taxonomy, source and text keyword."""
        api = DataApiClient()
        try:
            query = {k: v for k, v in params.model_dump().items()
                     if k not in ("response_format", "limit", "offset") and v not in (None, "")}
            if params.direction:
                query["direction"] = params.direction.value
            query["limit"] = params.limit
            query["offset"] = params.offset
            payload = await api.get("reputation/tagged-reviews", params=query)
            payload = _as_mcp(payload, "reputation_reviews")
        except Exception as exc:
            payload = _error_payload(exc)
        finally:
            await api.close()
        return render_response(payload, params.response_format)

    @mcp.tool(name="reputation_get_evidence", annotations=READ_ONLY_ANNOTATIONS)
    async def reputation_get_evidence(params: EvidenceInput) -> str:
        """Return paged original review evidence for a model, direction and tertiary tag."""
        api = DataApiClient()
        try:
            payload = await api.get("reputation/evidence", params={
                "model": params.model, "direction": params.direction.value,
                "tag": params.tertiary_label, "limit": params.limit, "offset": params.offset,
            })
            payload = _as_mcp(payload, "reputation_evidence")
        except Exception as exc:
            payload = _error_payload(exc)
        finally:
            await api.close()
        return render_response(payload, params.response_format)

    @mcp.tool(name="reputation_compare_models", annotations=READ_ONLY_ANNOTATIONS)
    async def reputation_compare_models(params: ReputationCompareInput) -> str:
        """Compare top positive and negative reputation topics for two to ten models."""
        api = DataApiClient()
        try:
            payload = await api.get("reputation/compare", params={"models": params.models, "top_n": params.top_n})
            payload = _as_mcp(payload, "reputation")
        except Exception as exc:
            payload = _error_payload(exc)
        finally:
            await api.close()
        return render_response(payload, params.response_format)

    return mcp


mcp = build_server()


if __name__ == "__main__":
    run_server(mcp, 8814)
