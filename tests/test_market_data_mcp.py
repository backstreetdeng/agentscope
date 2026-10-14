from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


MCP_ROOT = Path(__file__).resolve().parents[1] / "mcp"
sys.path.insert(0, str(MCP_ROOT))

from market_data import new_car_server, policy_server, reputation_server, rights_server  # noqa: E402


def call_json(server, tool_name: str, arguments: dict) -> dict:
    result = asyncio.run(server.call_tool(tool_name, arguments))
    structured = result[1] if isinstance(result, tuple) else result
    return json.loads(structured["result"])


class MarketDataMcpTests(unittest.TestCase):
    def test_four_servers_expose_prefixed_read_only_tools(self):
        servers = {
            "policy": policy_server.mcp,
            "rights": rights_server.mcp,
            "new_car": new_car_server.mcp,
            "reputation": reputation_server.mcp,
        }
        for prefix, server in servers.items():
            tools = asyncio.run(server.list_tools())
            self.assertTrue(tools)
            self.assertTrue(all(tool.name.startswith(prefix) for tool in tools))
            self.assertTrue(all(tool.annotations.readOnlyHint is True for tool in tools))
            self.assertTrue(all(tool.annotations.destructiveHint is False for tool in tools))

    def test_policy_search_and_detail_use_real_snapshot(self):
        search = call_json(
            policy_server.mcp,
            "policy_search_policies",
            {"params": {"province": "河北", "keyword": "消费券", "limit": 5}},
        )
        self.assertTrue(search["success"])
        self.assertGreaterEqual(search["total_count"], 1)
        record_id = search["items"][0]["记录编号"]
        detail = call_json(policy_server.mcp, "policy_get_policy_detail", {"params": {"record_id": record_id}})
        self.assertEqual(detail["item"]["记录编号"], record_id)

    def test_rights_activity_type_filter_uses_standard_options(self):
        payload = call_json(
            rights_server.mcp,
            "rights_search_offers",
            {"params": {"activity_types": ["其他权益"], "limit": 5}},
        )
        self.assertTrue(payload["success"])
        self.assertGreaterEqual(payload["total_count"], 1)
        self.assertTrue(all("其他权益" in item["当前活动类型（支持多选）"] for item in payload["items"]))

    def test_new_car_status_can_report_database_counts(self):
        with patch.object(new_car_server, "query_scalar", side_effect=[487, 120, "batch-1"]):
            payload = call_json(new_car_server.mcp, "new_car_get_status", {})
        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["model_count"], 487)

    def test_reputation_summary_groups_positive_and_negative(self):
        rows = [
            {"direction": "positive", "rank": 1, "primary_label": "空间"},
            {"direction": "negative", "rank": 1, "primary_label": "能耗"},
        ]
        with patch.object(reputation_server, "query_rows", return_value=rows), patch.object(
            reputation_server, "source_status", return_value={
                "analysis_current": True,
                "analysis_source_version": "test-version",
                "analysis_method": "test",
                "analysis_batch": "test-batch",
            },
        ):
            payload = call_json(
                reputation_server.mcp,
                "reputation_get_model_summary",
                {"params": {"model": "示例车型"}},
            )
        self.assertTrue(payload["available"])
        self.assertEqual(payload["groups"]["positive"][0]["primary_label"], "空间")
        self.assertEqual(payload["groups"]["negative"][0]["primary_label"], "能耗")


if __name__ == "__main__":
    unittest.main()
