"""Vehicle sales rights/offer data MCP server."""

from __future__ import annotations

import os
from datetime import date

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from .shared import (
    READ_ONLY_ANNOTATIONS,
    PageInput,
    ResponseFormat,
    any_text_contains,
    create_excel_export,
    date_in_range,
    load_domain_dataset,
    paginated,
    parse_date,
    render_response,
    run_server,
    single,
    text_contains,
)


DATASET = "rights-intelligence.json"


class RightsSearchInput(PageInput):
    brand: str = Field(default="", max_length=80, description="Vehicle brand or manufacturer.")
    model: str = Field(default="", max_length=100, description="Vehicle model.")
    keyword: str = Field(default="", max_length=200, description="Keyword matched against all offer fields.")
    activity_types: list[str] = Field(default_factory=list, max_length=6, description="Standard activity types to match.")
    region: str = Field(default="", max_length=100, description="Applicable region or channel.")
    active_on: date | None = Field(default=None, description="Return offers active on this date where dates are available.")


class RightsIdInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    record_id: str = Field(min_length=1, max_length=80, description="Rights record ID, e.g. PM2609-929022.")
    response_format: ResponseFormat = ResponseFormat.JSON


class RightsCompareInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    models: list[str] = Field(min_length=2, max_length=10, description="Two to ten model names.")
    active_on: date | None = Field(default=None, description="Optional effective date.")
    response_format: ResponseFormat = ResponseFormat.JSON


class RightsChangeInput(PageInput):
    brand: str = Field(default="", max_length=80)
    change_type: str = Field(default="", max_length=80, description="新增、取消、加码、减码 or another stored change type.")


class RightsExportInput(RightsSearchInput):
    record_ids: list[str] = Field(default_factory=list, max_length=5000)
    limit: int = Field(default=100, ge=1, le=5000)


def _dataset() -> dict:
    return load_domain_dataset("rights", DATASET)


def _active(record: dict, active_on: date | None) -> bool:
    if active_on is None:
        return True
    start = parse_date(record.get("活动开始日期"))
    end = parse_date(record.get("活动结束日期"))
    return (start is None or start <= active_on) and (end is None or end >= active_on)


def _search(params: RightsSearchInput) -> tuple[dict, list[dict]]:
    dataset = _dataset()
    allowed = set(dataset.get("activityTypeOptions", []))
    requested = set(params.activity_types)
    if requested - allowed:
        raise ValueError(f"活动类型仅支持：{'、'.join(sorted(allowed))}")
    matches = []
    for record in dataset.get("records", []):
        current_types = set(record.get("当前活动类型（支持多选）") or [])
        if not text_contains(record.get("车企/品牌"), params.brand):
            continue
        if not text_contains(record.get("车型"), params.model):
            continue
        if not text_contains(record.get("适用地区及渠道"), params.region):
            continue
        if requested and not requested.issubset(current_types):
            continue
        if not any_text_contains(record, params.keyword):
            continue
        if not _active(record, params.active_on):
            continue
        matches.append(record)
    return dataset, matches


def build_server() -> FastMCP:
    mcp = FastMCP(
        "rights_mcp",
        instructions="只读查询乘用车厂商权益、金融方案、补贴和活动变化。",
        host=os.getenv("MCP_HOST", "0.0.0.0"),
        port=int(os.getenv("MCP_PORT", "8812")),
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
    )

    @mcp.tool(name="rights_get_status", annotations=READ_ONLY_ANNOTATIONS)
    async def rights_get_status(response_format: ResponseFormat = ResponseFormat.JSON) -> str:
        """Return rights source status, record count, version and allowed activity types."""
        dataset = _dataset()
        payload = {
            "success": True,
            "data_source": "rights",
            "status": "ready",
            "record_count": len(dataset.get("records", [])),
            "data_version": dataset.get("generatedAt", ""),
            "as_of": dataset.get("asOf", ""),
            "activity_types": dataset.get("activityTypeOptions", []),
        }
        return render_response(payload, response_format)

    @mcp.tool(name="rights_search_offers", annotations=READ_ONLY_ANNOTATIONS)
    async def rights_search_offers(params: RightsSearchInput) -> str:
        """Search offers by brand, model, activity types, region, keyword and effective date."""
        dataset, matches = _search(params)
        payload = paginated(matches, params.limit, params.offset, source="rights", version=dataset.get("generatedAt", ""))
        return render_response(payload, params.response_format)

    @mcp.tool(name="rights_get_offer_detail", annotations=READ_ONLY_ANNOTATIONS)
    async def rights_get_offer_detail(params: RightsIdInput) -> str:
        """Return the complete structured offer for one rights record ID."""
        dataset = _dataset()
        item = next((record for record in dataset.get("records", []) if record.get("记录编号") == params.record_id), None)
        return render_response(single(item, source="rights", version=dataset.get("generatedAt", "")), params.response_format)

    @mcp.tool(name="rights_get_active_offers", annotations=READ_ONLY_ANNOTATIONS)
    async def rights_get_active_offers(params: RightsSearchInput) -> str:
        """Return offers active on active_on; undated offers are retained with their original fields."""
        dataset, matches = _search(params)
        payload = paginated(matches, params.limit, params.offset, source="rights", version=dataset.get("generatedAt", ""))
        return render_response(payload, params.response_format)

    @mcp.tool(name="rights_compare_models", annotations=READ_ONLY_ANNOTATIONS)
    async def rights_compare_models(params: RightsCompareInput) -> str:
        """Compare active rights records for two to ten vehicle models."""
        dataset = _dataset()
        comparisons = []
        for model_name in params.models:
            records = [
                record for record in dataset.get("records", [])
                if text_contains(record.get("车型"), model_name) and _active(record, params.active_on)
            ]
            activity_counts: dict[str, int] = {}
            for record in records:
                for activity_type in record.get("当前活动类型（支持多选）") or []:
                    activity_counts[activity_type] = activity_counts.get(activity_type, 0) + 1
            comparisons.append({"model": model_name, "offer_count": len(records), "activity_counts": activity_counts, "items": records[:10]})
        payload = {"success": True, "data_source": "rights", "data_version": dataset.get("generatedAt", ""), "comparisons": comparisons}
        return render_response(payload, params.response_format)

    @mcp.tool(name="rights_get_offer_changes", annotations=READ_ONLY_ANNOTATIONS)
    async def rights_get_offer_changes(params: RightsChangeInput) -> str:
        """List offer records with stored period-over-period change information."""
        dataset = _dataset()
        matches = [
            record for record in dataset.get("records", [])
            if text_contains(record.get("车企/品牌"), params.brand)
            and text_contains(record.get("较上期变化类型"), params.change_type)
            and (record.get("较上期变化类型") or record.get("较上期变化详情"))
        ]
        payload = paginated(matches, params.limit, params.offset, source="rights", version=dataset.get("generatedAt", ""))
        return render_response(payload, params.response_format)

    @mcp.tool(name="rights_export_offers", annotations=READ_ONLY_ANNOTATIONS)
    async def rights_export_offers(params: RightsExportInput) -> str:
        """Export matching rights records to Excel using the approved rights header order."""
        dataset, matches = _search(params)
        if params.record_ids:
            selected = set(params.record_ids)
            matches = [record for record in matches if record.get("记录编号") in selected]
        payload = create_excel_export("rights", dataset.get("headers", []), matches[: params.limit])
        return render_response(payload, params.response_format)

    return mcp


mcp = build_server()


if __name__ == "__main__":
    run_server(mcp, 8812)
