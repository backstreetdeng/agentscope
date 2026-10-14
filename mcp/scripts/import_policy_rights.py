"""Import approved policy and rights JSON snapshots into PostgreSQL."""

from __future__ import annotations

import json
import sys
from pathlib import Path


MCP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MCP_ROOT))

from market_data.shared import DATA_DIR, parse_date, pg_connect  # noqa: E402


def _load(filename: str) -> dict:
    return json.loads((DATA_DIR / filename).read_text(encoding="utf-8"))


def _upsert_meta(cursor, domain: str, dataset: dict) -> None:
    cursor.execute(
        """
        INSERT INTO market_dataset_meta
            (domain, generated_at, as_of_date, source_name, headers, options, extraction_method, updated_at)
        VALUES (%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,now())
        ON CONFLICT (domain) DO UPDATE SET
            generated_at=excluded.generated_at, as_of_date=excluded.as_of_date,
            source_name=excluded.source_name, headers=excluded.headers,
            options=excluded.options, extraction_method=excluded.extraction_method,
            updated_at=now()
        """,
        (
            domain, dataset.get("generatedAt") or None, parse_date(dataset.get("asOf")),
            dataset.get("source", ""), json.dumps(dataset.get("headers", []), ensure_ascii=False),
            json.dumps({"activityTypeOptions": dataset.get("activityTypeOptions", [])}, ensure_ascii=False),
            dataset.get("extractionMethod", ""),
        ),
    )


def import_policy(cursor) -> int:
    dataset = _load("policy-intelligence.json")
    _upsert_meta(cursor, "policy", dataset)
    for record in dataset.get("records", []):
        cursor.execute(
            """
            INSERT INTO policy_record
                (record_id, monitor_date, province, city, policy_name, policy_start_date,
                 policy_end_date, source_url, payload, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,now())
            ON CONFLICT (record_id) DO UPDATE SET
                monitor_date=excluded.monitor_date, province=excluded.province,
                city=excluded.city, policy_name=excluded.policy_name,
                policy_start_date=excluded.policy_start_date,
                policy_end_date=excluded.policy_end_date, source_url=excluded.source_url,
                payload=excluded.payload, updated_at=now()
            """,
            (
                record.get("记录编号"), parse_date(record.get("监测日期/发布日期")),
                record.get("省份", ""), record.get("城市", ""), record.get("政策名称", ""),
                parse_date(record.get("政策开始时间")), parse_date(record.get("政策结束时间")),
                record.get("信息来源链接", ""), json.dumps(record, ensure_ascii=False),
            ),
        )
    return len(dataset.get("records", []))


def import_rights(cursor) -> int:
    dataset = _load("rights-intelligence.json")
    _upsert_meta(cursor, "rights", dataset)
    for record in dataset.get("records", []):
        cursor.execute(
            """
            INSERT INTO rights_record
                (record_id, monitor_date, brand, model, activity_start_date,
                 activity_end_date, activity_types, source_url, payload, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,now())
            ON CONFLICT (record_id) DO UPDATE SET
                monitor_date=excluded.monitor_date, brand=excluded.brand, model=excluded.model,
                activity_start_date=excluded.activity_start_date,
                activity_end_date=excluded.activity_end_date,
                activity_types=excluded.activity_types, source_url=excluded.source_url,
                payload=excluded.payload, updated_at=now()
            """,
            (
                record.get("记录编号"), parse_date(record.get("监测日期/发布日期")),
                record.get("车企/品牌", ""), record.get("车型", ""),
                parse_date(record.get("活动开始日期")), parse_date(record.get("活动结束日期")),
                record.get("当前活动类型（支持多选）") or [], record.get("信息来源链接", ""),
                json.dumps(record, ensure_ascii=False),
            ),
        )
    return len(dataset.get("records", []))


def main() -> None:
    connection = pg_connect()
    try:
        with connection, connection.cursor() as cursor:
            policy_count = import_policy(cursor)
            rights_count = import_rights(cursor)
        print(json.dumps({"policy": policy_count, "rights": rights_count}, ensure_ascii=False))
    finally:
        connection.close()


if __name__ == "__main__":
    main()

