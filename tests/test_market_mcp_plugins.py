from __future__ import annotations

import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from integrations.market_mcp_plugins import (
    DEFAULT_PLUGINS,
    MarketMCPPlugin,
    load_market_mcp_plugins,
    market_mcp_plugin_catalog,
)


def test_config() -> dict:
    return {
        "mcp_plugins": {
            "enabled": True,
            "default_base_url": "http://example.test:8790",
            "plugins": {plugin_id: {"enabled": True} for plugin_id in DEFAULT_PLUGINS},
        },
    }


class FakeClient:
    def __init__(self, plugin_id: str):
        self.plugin_id = plugin_id

    async def list_tools(self):
        if self.plugin_id == "rights":
            raise ConnectionError("rights endpoint unavailable")
        return [SimpleNamespace(name=self.plugin_id.replace("-", "_") + "_status")]


class MarketMCPPluginTests(unittest.TestCase):
    def test_rights_can_use_cloud_without_changing_other_endpoints(self):
        with patch.dict(os.environ, {
            "MARKET_MCP_RIGHTS_URL": "https://rights.example.test/mcp",
            "MARKET_MCP_RIGHTS_API_TOKEN": "cloud-token",
            "MARKET_MCP_API_TOKEN": "lan-token",
        }, clear=True):
            catalog = market_mcp_plugin_catalog(test_config())
            rights = next(p for p in catalog if p.plugin_id == "rights")
            self.assertEqual(rights.url, "https://rights.example.test/mcp")
            self.assertEqual(rights.resolve_token(), "cloud-token")
            for plugin in catalog:
                if plugin.plugin_id != "rights":
                    self.assertTrue(plugin.url.startswith("http://example.test:8790/"))
                    self.assertEqual(plugin.resolve_token(), "lan-token")

    def test_cloud_does_not_receive_lan_token_when_cloud_token_missing(self):
        with patch.dict(os.environ, {
            "MARKET_MCP_RIGHTS_URL": "https://rights.example.test/mcp",
            "MARKET_MCP_API_TOKEN": "lan-secret",
        }, clear=True):
            plugin = next(p for p in market_mcp_plugin_catalog(test_config()) if p.plugin_id == "rights")
            self.assertEqual(plugin.resolve_token(), "")
            bundle = asyncio.run(load_market_mcp_plugins(test_config(), selected_plugin_ids=["rights"]))
            rights = next(p for p in bundle.statuses if p.plugin_id == "rights")
            self.assertEqual(rights.status, "misconfigured")

    def test_catalog_keeps_four_plugins_independent(self):
        catalog = market_mcp_plugin_catalog(test_config(), selected_plugin_ids=["policy", "new-car"])
        self.assertEqual([item.plugin_id for item in catalog], list(DEFAULT_PLUGINS))
        self.assertEqual([item.plugin_id for item in catalog if item.enabled], ["policy", "new-car"])
        self.assertTrue(all(item.url.startswith("http://example.test:8790/mcp/") for item in catalog))

    def test_one_failed_plugin_does_not_remove_other_tools(self):
        def build_fake(plugin: MarketMCPPlugin, token: str):
            self.assertEqual(token, "test-token")
            return FakeClient(plugin.plugin_id)

        with patch.dict(os.environ, {"MARKET_MCP_API_TOKEN": "test-token"}, clear=False):
            with patch.object(MarketMCPPlugin, "build_client", build_fake):
                bundle = asyncio.run(load_market_mcp_plugins(test_config()))

        statuses = {item.plugin_id: item.status for item in bundle.statuses}
        self.assertEqual(statuses["rights"], "unavailable")
        self.assertEqual(statuses["policy"], "ready")
        self.assertEqual(statuses["new-car"], "ready")
        self.assertEqual(statuses["reputation"], "ready")
        self.assertEqual(len(bundle.tools), 3)

    def test_missing_token_reports_configuration_without_network_calls(self):
        with patch.dict(os.environ, {"MARKET_MCP_API_TOKEN": ""}, clear=False):
            bundle = asyncio.run(load_market_mcp_plugins(test_config()))
        self.assertTrue(all(item.status == "misconfigured" for item in bundle.statuses))
        self.assertEqual(bundle.tools, [])


if __name__ == "__main__":
    unittest.main()
