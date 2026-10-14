"""Vehicle reputation and evidence MCP server."""

from __future__ import annotations

import asyncio
import os
from enum import Enum

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from .shared import READ_ONLY_ANNOTATIONS, PageInput, ResponseFormat, paginated, query_rows, query_scalar, render_response, run_server
from .reputation_sources import SourceReviewInput, search_source_reviews, source_status


class Direction(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"


class ReputationModelInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    model: str = Field(min_length=1, max_length=100)
    response_format: ResponseFormat = ResponseFormat.JSON


class ReputationSearchInput(PageInput):
    model: str = Field(default="", max_length=100)
    direction: Direction | None = None
    primary_label: str = Field(default="", max_length=100)
    secondary_label: str = Field(default="", max_length=100)
    tertiary_label: str = Field(default="", max_length=100)
    source: str = Field(default="", max_length=80)
    keyword: str = Field(default="", max_length=200)


class EvidenceInput(PageInput):
    model: str = Field(min_length=1, max_length=100)
    direction: Direction
    tertiary_label: str = Field(min_length=1, max_length=100)


class ReputationCompareInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    models: list[str] = Field(min_length=2, max_length=10)
    top_n: int = Field(default=5, ge=1, le=10)
    response_format: ResponseFormat = ResponseFormat.JSON


def _review_search(params: ReputationSearchInput) -> list[dict]:
    clauses = ["TRUE"]
    values: list[object] = []
    for column, value in (
        ("model", params.model), ("primary_label", params.primary_label),
        ("secondary_label", params.secondary_label), ("tertiary_label", params.tertiary_label),
        ("source", params.source),
    ):
        if value:
            clauses.append(f"{column} ILIKE %s")
            values.append(f"%{value}%")
    if params.direction:
        clauses.append("direction=%s")
        values.append(params.direction.value)
    if params.keyword:
        clauses.append("(excerpt ILIKE %s OR review_text ILIKE %s)")
        values.extend([f"%{params.keyword}%", f"%{params.keyword}%"])
    sql = f"""
        SELECT model, direction, source, review_key, primary_label, secondary_label,
               tertiary_label, taxonomy_code, is_custom, excerpt, review_text, import_batch
        FROM new_car_reputation_review_tag
        WHERE {' AND '.join(clauses)}
        ORDER BY model, direction, source, review_key
    """
    return query_rows(sql, tuple(values))


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
        try:
            payload = await asyncio.to_thread(source_status)
            payload.update(analysis_storage_tables=['new_car_reputation_taxonomy_summary','new_car_reputation_review_tag'])
        except Exception as exc:
            payload = {"success": False, "data_source": "reputation", "status": "unavailable", "error": f"口碑数据库暂不可用：{type(exc).__name__}"}
        return render_response(payload, response_format)

    @mcp.tool(name="reputation_search_source_reviews", annotations=READ_ONLY_ANNOTATIONS)
    async def reputation_search_source_reviews(params: SourceReviewInput) -> str:
        """Page current original Autohome and Dongchedi reviews from formal PostgreSQL.

        Exact source model matching; this does not assign reviews based on mentions
        of competitors in text. Returns unique source+review_key records, source counts,
        published/record update dates and platform-native scores, not inferred sentiment.
        """
        payload = await asyncio.to_thread(search_source_reviews, params)
        return render_response(payload, params.response_format)

    @mcp.tool(name="reputation_search_models", annotations=READ_ONLY_ANNOTATIONS)
    async def reputation_search_models(params: PageInput) -> str:
        """List vehicle models that currently have tagged reputation evidence."""
        rows = await asyncio.to_thread(query_rows, "SELECT model, COUNT(DISTINCT review_key) AS review_count, MAX(import_batch) AS latest_batch FROM new_car_reputation_review_tag GROUP BY model ORDER BY review_count DESC, model")
        return render_response(paginated(rows, params.limit, params.offset, source="reputation_models"), params.response_format)

    @mcp.tool(name="reputation_get_model_summary", annotations=READ_ONLY_ANNOTATIONS)
    async def reputation_get_model_summary(params: ReputationModelInput) -> str:
        """Return positive and negative top-level reputation summaries for one model."""
        rows = await asyncio.to_thread(
            query_rows,
            "SELECT direction, rank, primary_label, tertiary_labels, mention_count, mention_share, dongchedi_count, autohome_count, source_mentions, import_batch, taxonomy_version FROM new_car_reputation_taxonomy_summary WHERE model=%s ORDER BY direction, rank",
            (params.model,),
        )
        groups = {"positive": [], "negative": []}
        for row in rows:
            groups.setdefault(row["direction"], []).append(row)
        metadata = await asyncio.to_thread(source_status)
        payload = {"success": True, "data_source": "reputation", "model": params.model, "available": bool(rows), "groups": groups,
                   "analysis_current": metadata['analysis_current'],"analysis_source_version": metadata['analysis_source_version'],
                   "analysis_method":metadata['analysis_method'],"analysis_batch":metadata['analysis_batch']}
        return render_response(payload, params.response_format)

    @mcp.tool(name="reputation_get_topic_tree", annotations=READ_ONLY_ANNOTATIONS)
    async def reputation_get_topic_tree(params: ReputationModelInput) -> str:
        """Return the L1/L2/L3 reputation taxonomy tree with distinct review counts."""
        rows = await asyncio.to_thread(
            query_rows,
            "SELECT direction, primary_label, secondary_label, tertiary_label, taxonomy_code, is_custom, COUNT(DISTINCT review_key) AS review_count FROM new_car_reputation_review_tag WHERE model=%s GROUP BY direction, primary_label, secondary_label, tertiary_label, taxonomy_code, is_custom ORDER BY direction, primary_label, secondary_label, review_count DESC",
            (params.model,),
        )
        return render_response({"success": True, "data_source": "reputation", "model": params.model, "items": rows}, params.response_format)

    @mcp.tool(name="reputation_search_reviews", annotations=READ_ONLY_ANNOTATIONS)
    async def reputation_search_reviews(params: ReputationSearchInput) -> str:
        """Search tagged source reviews by model, sentiment direction, taxonomy, source and text keyword."""
        rows = await asyncio.to_thread(_review_search, params)
        return render_response(paginated(rows, params.limit, params.offset, source="reputation_reviews"), params.response_format)

    @mcp.tool(name="reputation_get_evidence", annotations=READ_ONLY_ANNOTATIONS)
    async def reputation_get_evidence(params: EvidenceInput) -> str:
        """Return paged original review evidence for a model, direction and tertiary tag."""
        rows = await asyncio.to_thread(
            query_rows,
            "SELECT source, review_key, primary_label, secondary_label, tertiary_label, taxonomy_code, is_custom, excerpt, review_text, import_batch FROM new_car_reputation_review_tag WHERE model=%s AND direction=%s AND tertiary_label=%s ORDER BY source, review_key",
            (params.model, params.direction.value, params.tertiary_label),
        )
        return render_response(paginated(rows, params.limit, params.offset, source="reputation_evidence"), params.response_format)

    @mcp.tool(name="reputation_compare_models", annotations=READ_ONLY_ANNOTATIONS)
    async def reputation_compare_models(params: ReputationCompareInput) -> str:
        """Compare top positive and negative reputation topics for two to ten models."""
        comparisons = []
        for model_name in params.models:
            rows = await asyncio.to_thread(
                query_rows,
                "SELECT direction, rank, primary_label, mention_count, mention_share, source_mentions FROM new_car_reputation_taxonomy_summary WHERE model=%s AND rank<=%s ORDER BY direction, rank",
                (model_name, params.top_n),
            )
            comparisons.append({"model": model_name, "topics": rows})
        return render_response({"success": True, "data_source": "reputation", "comparisons": comparisons}, params.response_format)

    return mcp


mcp = build_server()


if __name__ == "__main__":
    run_server(mcp, 8814)

