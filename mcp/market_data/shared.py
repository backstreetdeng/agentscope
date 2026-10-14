"""Shared configuration, data access and response helpers for market MCP servers."""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

from openpyxl import Workbook
from pydantic import BaseModel, ConfigDict, Field


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("MARKET_MCP_DATA_DIR", PROJECT_ROOT / "assets" / "data"))
EXPORT_DIR = Path(os.getenv("MARKET_MCP_EXPORT_DIR", PROJECT_ROOT / "outputs" / "mcp-exports"))
EXPORT_BASE_URL = os.getenv("MARKET_MCP_EXPORT_BASE_URL", "").rstrip("/")

READ_ONLY_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}


class ResponseFormat(str, Enum):
    JSON = "json"
    MARKDOWN = "markdown"


class PageInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    limit: int = Field(default=20, ge=1, le=100, description="Maximum records to return, 1-100.")
    offset: int = Field(default=0, ge=0, description="Number of matching records to skip.")
    response_format: ResponseFormat = Field(default=ResponseFormat.JSON, description="json or markdown")


def load_json_dataset(filename: str) -> dict[str, Any]:
    path = DATA_DIR / filename
    if not path.is_file():
        raise FileNotFoundError(f"数据文件不存在：{path.name}。请先执行数据同步任务。")
    return json.loads(path.read_text(encoding="utf-8"))


def load_domain_dataset(domain: str, filename: str) -> dict[str, Any]:
    """Load policy/rights data from PostgreSQL in production or JSON in development."""
    if os.getenv("MARKET_MCP_BACKEND", "json").casefold() != "postgres":
        return load_json_dataset(filename)
    table = {"policy": "policy_record", "rights": "rights_record"}.get(domain)
    if table is None:
        raise ValueError(f"不支持的数据域：{domain}")
    metadata_rows = query_rows(
        "SELECT generated_at, as_of_date, source_name, headers, options, extraction_method "
        "FROM market_dataset_meta WHERE domain=%s",
        (domain,),
    )
    metadata = metadata_rows[0] if metadata_rows else {}
    records = query_rows(f"SELECT payload FROM {table} ORDER BY record_id")
    return {
        "generatedAt": metadata.get("generated_at", ""),
        "asOf": metadata.get("as_of_date", ""),
        "source": metadata.get("source_name", ""),
        "headers": metadata.get("headers") or [],
        "activityTypeOptions": (metadata.get("options") or {}).get("activityTypeOptions", []),
        "extractionMethod": metadata.get("extraction_method", ""),
        "records": [row["payload"] for row in records],
    }


def text_contains(value: Any, needle: str | None) -> bool:
    if not needle:
        return True
    if isinstance(value, list):
        value = " ".join(str(item) for item in value)
    return needle.casefold() in str(value or "").casefold()


def any_text_contains(record: dict[str, Any], needle: str | None) -> bool:
    return not needle or any(text_contains(value, needle) for value in record.values())


def parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    match = re.search(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})", text)
    if not match:
        return None
    try:
        return date(*(int(part) for part in match.groups()))
    except ValueError:
        return None


def date_in_range(value: Any, start: date | None, end: date | None) -> bool:
    parsed = parse_date(value)
    if start and (parsed is None or parsed < start):
        return False
    if end and (parsed is None or parsed > end):
        return False
    return True


def paginated(items: list[dict[str, Any]], limit: int, offset: int, *, source: str, version: str = "") -> dict[str, Any]:
    page = items[offset : offset + limit]
    next_offset = offset + len(page)
    return {
        "success": True,
        "data_source": source,
        "data_version": version,
        "total_count": len(items),
        "count": len(page),
        "offset": offset,
        "has_more": next_offset < len(items),
        "next_offset": next_offset if next_offset < len(items) else None,
        "items": page,
        "warnings": [],
        "trace_id": f"req-{uuid.uuid4().hex[:12]}",
    }


def single(item: dict[str, Any] | None, *, source: str, version: str = "") -> dict[str, Any]:
    if item is None:
        return {
            "success": False,
            "data_source": source,
            "error": "未找到匹配记录，请检查记录编号或筛选条件。",
            "trace_id": f"req-{uuid.uuid4().hex[:12]}",
        }
    return {
        "success": True,
        "data_source": source,
        "data_version": version,
        "item": item,
        "trace_id": f"req-{uuid.uuid4().hex[:12]}",
    }


def render_response(payload: dict[str, Any], response_format: ResponseFormat) -> str:
    if response_format == ResponseFormat.JSON:
        return json.dumps(payload, ensure_ascii=False, default=str)
    if not payload.get("success"):
        return f"查询失败：{payload.get('error', '未知错误')}"
    lines = [f"# {payload.get('data_source', 'data')} 查询结果", ""]
    if "total_count" in payload:
        lines.append(f"共 {payload['total_count']} 条，本次返回 {payload['count']} 条。")
        lines.append("")
        for item in payload.get("items", []):
            title = item.get("政策名称") or item.get("活动名称") or item.get("model") or item.get("车型") or item.get("id") or "记录"
            lines.append(f"## {title}")
            for key, value in item.items():
                if value not in (None, "", []):
                    lines.append(f"- **{key}**：{value}")
            lines.append("")
    elif payload.get("item"):
        for key, value in payload["item"].items():
            if value not in (None, "", []):
                lines.append(f"- **{key}**：{value}")
    else:
        for key, value in payload.items():
            if key not in {"success", "trace_id"}:
                lines.append(f"- **{key}**：{value}")
    return "\n".join(lines)


def create_excel_export(domain: str, headers: list[str], rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    export_id = f"EXP-{datetime.now():%Y%m%d}-{uuid.uuid4().hex[:8].upper()}"
    filename = f"{domain}-{export_id}.xlsx"
    path = EXPORT_DIR / filename
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "明细"
    sheet.append(headers)
    row_count = 0
    for record in rows:
        values = []
        for header in headers:
            value = record.get(header, "")
            if isinstance(value, list):
                value = "、".join(str(item) for item in value)
            values.append(value)
        sheet.append(values)
        row_count += 1
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    workbook.save(path)
    download_url = f"{EXPORT_BASE_URL}/{filename}" if EXPORT_BASE_URL else ""
    return {
        "success": True,
        "export_id": export_id,
        "status": "completed",
        "row_count": row_count,
        "file_name": filename,
        "download_url": download_url,
        "server_path": str(path) if not download_url else "",
    }


def pg_connect():
    import psycopg2

    return psycopg2.connect(
        host=os.getenv("MARKET_PG_HOST", os.getenv("NEW_CAR_PG_HOST", "192.168.3.146")),
        port=int(os.getenv("MARKET_PG_PORT", os.getenv("NEW_CAR_PG_PORT", "5432"))),
        dbname=os.getenv("MARKET_PG_DATABASE", os.getenv("NEW_CAR_PG_DATABASE", "vectordb")),
        user=os.getenv("MARKET_PG_USER", os.getenv("NEW_CAR_PG_USER", "market_mcp_reader")),
        password=os.getenv("MARKET_PG_PASSWORD", os.getenv("NEW_CAR_PG_PASSWORD", "")),
        connect_timeout=int(os.getenv("MARKET_PG_CONNECT_TIMEOUT", "5")),
        application_name=os.getenv("MARKET_PG_APPLICATION_NAME", "market-mcp"),
    )


def query_rows(sql: str, parameters: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    connection = pg_connect()
    try:
        connection.set_session(readonly=True, autocommit=True)
        with connection.cursor() as cursor:
            cursor.execute(sql, parameters)
            columns = [description[0] for description in cursor.description]
            return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
    finally:
        connection.close()


def query_scalar(sql: str, parameters: tuple[Any, ...] = ()) -> Any:
    connection = pg_connect()
    try:
        connection.set_session(readonly=True, autocommit=True)
        with connection.cursor() as cursor:
            cursor.execute(sql, parameters)
            row = cursor.fetchone()
            return row[0] if row else None
    finally:
        connection.close()


def run_server(mcp: Any, default_port: int) -> None:
    # FastMCP reads host/port from construction time, so entrypoints build their
    # server with environment-specific values before calling this helper.
    transport = os.getenv("MCP_TRANSPORT", "streamable-http")
    if transport not in {"stdio", "sse", "streamable-http"}:
        raise ValueError(f"不支持的 MCP_TRANSPORT：{transport}")
    mcp.run(transport=transport)
