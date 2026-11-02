"""PostgreSQL data access helpers（仅 data-api 与数据写入脚本使用，MCP server 不得导入）。"""

from __future__ import annotations

import os
from typing import Any

from .protocol import load_json_dataset


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


def load_domain_dataset(domain: str, filename: str) -> dict[str, Any]:
    """Load policy/rights data from PostgreSQL in production or JSON in development.

    仅供 data-api（以及尚未整改的权益 146 旧路径）使用；MCP server 已改为调用 data-api。
    """
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