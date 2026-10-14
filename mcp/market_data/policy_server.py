"""Policy data MCP server."""

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
    render_response,
    run_server,
    single,
    text_contains,
)


DATASET = "policy-intelligence.json"


class PolicySearchInput(PageInput):
    province: str = Field(default="", max_length=50, description="Province name, e.g. 江苏.")
    city: str = Field(default="", max_length=80, description="City name, e.g. 南京市.")
    keyword: str = Field(default="", max_length=200, description="Keyword matched against all policy fields.")
    start_date: date | None = Field(default=None, description="Earliest monitoring/publish date.")
    end_date: date | None = Field(default=None, description="Latest monitoring/publish date.")
    policy_type: str = Field(default="", max_length=80, description="Policy promotion type or audience keyword.")


class PolicyIdInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    record_id: str = Field(min_length=1, max_length=80, description="Policy record ID, e.g. POL-0002-408044.")
    response_format: ResponseFormat = ResponseFormat.JSON


class PolicyChangeInput(PageInput):
    province: str = Field(default="", max_length=50, description="Optional province filter.")
    change_type: str = Field(default="", max_length=80, description="Change type, such as 新增、调整、到期.")
    start_date: date | None = Field(default=None, description="Earliest monitoring date.")
    end_date: date | None = Field(default=None, description="Latest monitoring date.")


class PolicyCompareInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    regions: list[str] = Field(min_length=2, max_length=10, description="Two to ten province/city names.")
    keyword: str = Field(default="", max_length=200, description="Optional policy keyword.")
    active_on: date | None = Field(default=None, description="Optional date that must fall in the policy validity range.")
    limit_per_region: int = Field(default=10, ge=1, le=30)
    response_format: ResponseFormat = ResponseFormat.JSON


class PolicyExportInput(PolicySearchInput):
    record_ids: list[str] = Field(default_factory=list, max_length=5000, description="Optional explicit policy IDs.")
    limit: int = Field(default=100, ge=1, le=5000)


def _dataset() -> dict:
    return load_domain_dataset("policy", DATASET)


def _search(params: PolicySearchInput) -> tuple[dict, list[dict]]:
    dataset = _dataset()
    matches = []
    for record in dataset.get("records", []):
        if not text_contains(record.get("省份"), params.province):
            continue
        if not text_contains(record.get("城市"), params.city):
            continue
        if not any_text_contains(record, params.keyword):
            continue
        if params.policy_type and not (
            text_contains(record.get("促消费类型（统一表准/不统一标准）"), params.policy_type)
            or text_contains(record.get("适用客群（首购/增换购；个人/单位消费者；新能源/燃油车）"), params.policy_type)
        ):
            continue
        if not date_in_range(record.get("监测日期/发布日期"), params.start_date, params.end_date):
            continue
        matches.append(record)
    return dataset, matches


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
        """Return policy source status, effective storage backend, count and version.

        storage_backend is postgres or json, matching the actual dataset loader.
        storage_table is policy_record for postgres and null for file storage.
        These are runtime configuration facts, not additional database columns.
        """
        dataset = _dataset()
        # Keep this condition identical to load_domain_dataset; report effective
        # storage rather than echoing an unrecognised environment value.
        backend = "postgres" if os.getenv("MARKET_MCP_BACKEND", "json").casefold() == "postgres" else "json"
        payload = {
            "success": True,
            "data_source": "policy",
            "status": "ready",
            "storage_backend": backend,
            "storage_table": "policy_record" if backend == "postgres" else None,
            "record_count": len(dataset.get("records", [])),
            "data_version": dataset.get("generatedAt", ""),
            "as_of": dataset.get("asOf", ""),
            "source": dataset.get("source", ""),
            "extraction_method": dataset.get("extractionMethod", ""),
        }
        return render_response(payload, response_format)

    @mcp.tool(name="policy_search_policies", annotations=READ_ONLY_ANNOTATIONS)
    async def policy_search_policies(params: PolicySearchInput) -> str:
        """Search policy records by region, dates, type and free-text keyword with pagination."""
        dataset, matches = _search(params)
        payload = paginated(matches, params.limit, params.offset, source="policy", version=dataset.get("generatedAt", ""))
        return render_response(payload, params.response_format)

    @mcp.tool(name="policy_get_policy_detail", annotations=READ_ONLY_ANNOTATIONS)
    async def policy_get_policy_detail(params: PolicyIdInput) -> str:
        """Return the complete structured policy record for one policy record ID."""
        dataset = _dataset()
        item = next((record for record in dataset.get("records", []) if record.get("记录编号") == params.record_id), None)
        return render_response(single(item, source="policy", version=dataset.get("generatedAt", "")), params.response_format)

    @mcp.tool(name="policy_get_policy_changes", annotations=READ_ONLY_ANNOTATIONS)
    async def policy_get_policy_changes(params: PolicyChangeInput) -> str:
        """List policies whose structured change type/detail match the requested filters."""
        dataset = _dataset()
        matches = [
            record for record in dataset.get("records", [])
            if text_contains(record.get("省份"), params.province)
            and text_contains(record.get("较上期变化类型"), params.change_type)
            and (record.get("较上期变化类型") or record.get("较上期变化详情"))
            and date_in_range(record.get("监测日期/发布日期"), params.start_date, params.end_date)
        ]
        payload = paginated(matches, params.limit, params.offset, source="policy", version=dataset.get("generatedAt", ""))
        return render_response(payload, params.response_format)

    @mcp.tool(name="policy_compare_regions", annotations=READ_ONLY_ANNOTATIONS)
    async def policy_compare_regions(params: PolicyCompareInput) -> str:
        """Compare matching policy records across two to ten provinces or cities."""
        dataset = _dataset()
        comparisons = []
        for region in params.regions:
            records = [
                record for record in dataset.get("records", [])
                if (text_contains(record.get("省份"), region) or text_contains(record.get("城市"), region))
                and any_text_contains(record, params.keyword)
            ]
            if params.active_on:
                from .shared import parse_date
                records = [
                    record for record in records
                    if (parse_date(record.get("政策开始时间")) is None or parse_date(record.get("政策开始时间")) <= params.active_on)
                    and (parse_date(record.get("政策结束时间")) is None or parse_date(record.get("政策结束时间")) >= params.active_on)
                ]
            comparisons.append({"region": region, "count": len(records), "items": records[: params.limit_per_region]})
        payload = {"success": True, "data_source": "policy", "data_version": dataset.get("generatedAt", ""), "comparisons": comparisons}
        return render_response(payload, params.response_format)

    @mcp.tool(name="policy_export_policies", annotations=READ_ONLY_ANNOTATIONS)
    async def policy_export_policies(params: PolicyExportInput) -> str:
        """Export matching policies to Excel using the approved policy header order."""
        dataset, matches = _search(params)
        if params.record_ids:
            selected = set(params.record_ids)
            matches = [record for record in matches if record.get("记录编号") in selected]
        payload = create_excel_export("policy", dataset.get("headers", []), matches[: params.limit])
        return render_response(payload, params.response_format)

    return mcp


mcp = build_server()


if __name__ == "__main__":
    run_server(mcp, 8811)
