from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch


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

    def test_policy_search_and_detail_roundtrip_via_data_api(self):
        search_payload = {
            "success": True,
            "source": "api",
            "total_count": 1,
            "count": 1,
            "offset": 0,
            "has_more": False,
            "next_offset": None,
            "data_version": "v1",
            "items": [{"记录编号": "P-001", "省份": "河北", "政策名称": "汽车消费券"}],
        }
        detail_payload = {
            "success": True,
            "source": "api",
            "item": {"记录编号": "P-001", "省份": "河北", "政策名称": "汽车消费券"},
            "data_version": "v1",
        }

        async def fake_get(resource, params=None):
            return detail_payload if resource == "policies/detail" else search_payload

        with patch.object(policy_server.DataApiClient, "get", new=AsyncMock(side_effect=fake_get)):
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

    def test_new_car_status_can_report_counts(self):
        status_payload = {
            "success": True,
            "source": "api",
            "status": "ready",
            "model_count": 487,
            "planned_count": 120,
            "latest_batch": "batch-1",
        }
        with patch.object(new_car_server.DataApiClient, "get", new=AsyncMock(return_value=status_payload)):
            payload = call_json(new_car_server.mcp, "new_car_get_status", {})
        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["model_count"], 487)

    def test_reputation_summary_groups_positive_and_negative(self):
        summary_payload = {
            "success": True,
            "source": "api",
            "groups": {
                "positive": [{"direction": "positive", "rank": 1, "primary_label": "空间"}],
                "negative": [{"direction": "negative", "rank": 1, "primary_label": "能耗"}],
            },
        }
        with patch.object(reputation_server.DataApiClient, "get", new=AsyncMock(return_value=summary_payload)):
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