"""Create policy/rights tables and import the approved JSON snapshots."""

from __future__ import annotations

import json
import sys
from pathlib import Path


MCP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MCP_ROOT))

from market_data.shared import pg_connect, query_scalar  # noqa: E402
from scripts.import_policy_rights import import_policy, import_rights  # noqa: E402


def audit_domain(storage: str, sql: str, success_action: str) -> dict:
    """Audit an existing domain without making optional permissions fatal."""
    try:
        return {
            "storage": storage,
            "count": query_scalar(sql),
            "available": True,
            "action": success_action,
        }
    except Exception as exc:  # Existing tables may be owned by another database role.
        return {
            "storage": storage,
            "count": None,
            "available": False,
            "action": "select_permission_required",
            "warning": "当前数据库用户无权读取该领域的既有表；政策和权益导入不受影响。",
            "error_code": getattr(exc, "pgcode", None),
        }


def main() -> None:
    schema = (MCP_ROOT / "deploy" / "sql" / "001_market_mcp.sql").read_text(encoding="utf-8")
    connection = pg_connect()
    try:
        with connection, connection.cursor() as cursor:
            cursor.execute(schema)
            policy_count = import_policy(cursor)
            rights_count = import_rights(cursor)
        domains = {
            "policy": audit_domain("policy_record", "SELECT COUNT(*) FROM policy_record", "created_or_updated"),
            "rights": audit_domain("rights_record", "SELECT COUNT(*) FROM rights_record", "created_or_updated"),
            "new_car": audit_domain(
                "new_car_model + planned_new_car + new_car_monthly_sales",
                "SELECT COUNT(*) FROM new_car_model",
                "existing_tables_reused",
            ),
            "reputation": audit_domain(
                "new_car_reputation_taxonomy_summary + new_car_reputation_review_tag",
                "SELECT COUNT(DISTINCT review_key) FROM new_car_reputation_review_tag",
                "existing_tables_reused",
            ),
        }
        print(json.dumps({
            "schema": "ready",
            "imported": {"policy": policy_count, "rights": rights_count},
            "domains": domains,
        }, ensure_ascii=False, default=str))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
