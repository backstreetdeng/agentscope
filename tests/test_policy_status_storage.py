"""Status contract tests: fake dataset, no database/network access."""
import asyncio
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcp"))
from market_data import policy_server


def status_result(arguments=None):
    result = asyncio.run(policy_server.mcp.call_tool("policy_get_status", arguments or {}))
    return json.loads(result[1]["result"])


class PolicyStatusStorageTests(unittest.TestCase):
    def check_backend(self, env, backend, table):
        with patch.dict(os.environ, env, clear=True), patch.object(
            policy_server, "_dataset", return_value={"records": [], "generatedAt": "version-1"}
        ):
            result = status_result()
        self.assertTrue(result["success"])
        self.assertEqual(result["storage_backend"], backend)
        self.assertEqual(result["storage_table"], table)
        self.assertEqual(result["data_version"], "version-1")
        self.assertEqual(result["record_count"], 0)
        self.assertNotIn("last_successful_import", result)

    def test_postgres(self):
        self.check_backend({"MARKET_MCP_BACKEND": "postgres"}, "postgres", "policy_record")

    def test_case_insensitive_postgres(self):
        self.check_backend({"MARKET_MCP_BACKEND": "POSTGRES"}, "postgres", "policy_record")

    def test_explicit_json(self):
        self.check_backend({"MARKET_MCP_BACKEND": "json"}, "json", None)

    def test_missing_uses_actual_default(self):
        self.check_backend({}, "json", None)

    def test_unknown_matches_actual_file_loader(self):
        self.check_backend({"MARKET_MCP_BACKEND": "unknown"}, "json", None)

    def test_query_failure_is_not_successful_status(self):
        with patch.object(policy_server, "_dataset", side_effect=RuntimeError("unavailable")):
            with self.assertRaises(Exception):
                status_result()


if __name__ == "__main__":
    unittest.main()
