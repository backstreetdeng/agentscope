"""Status contract tests: fake data-api response, no database/network access."""
import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcp"))
from market_data import policy_server
from market_data.data_api_client import DataApiError


def status_result(arguments=None):
    result = asyncio.run(policy_server.mcp.call_tool("policy_get_status", arguments or {}))
    return json.loads(result[1]["result"])


class PolicyStatusProxyTests(unittest.TestCase):
    def test_status_passes_through_and_maps_source_name(self):
        payload = {
            "success": True,
            "source": "api",
            "status": "ready",
            "storage_backend": "postgres",
            "storage_table": "policy_record",
            "record_count": 3,
            "data_version": "version-1",
            "as_of": "2026-10-31",
            "source_name": "policy-intelligence",
            "extraction_method": "manual",
        }
        with patch.object(policy_server.DataApiClient, "get", new=AsyncMock(return_value=payload)):
            result = status_result()
        self.assertTrue(result["success"])
        self.assertEqual(result["data_source"], "policy")
        self.assertEqual(result["source"], "policy-intelligence")
        self.assertNotIn("source_name", result)
        self.assertEqual(result["storage_backend"], "postgres")
        self.assertEqual(result["storage_table"], "policy_record")
        self.assertEqual(result["data_version"], "version-1")
        self.assertEqual(result["record_count"], 3)

    def test_status_returns_error_payload_on_data_api_failure(self):
        with patch.object(
            policy_server.DataApiClient,
            "get",
            new=AsyncMock(side_effect=DataApiError("DATA_API_UNAVAILABLE", "数据服务不可用")),
        ):
            result = status_result()
        self.assertFalse(result["success"])
        self.assertEqual(result["data_source"], "policy")
        self.assertIn("数据服务不可用", result["error"])


if __name__ == "__main__":
    unittest.main()