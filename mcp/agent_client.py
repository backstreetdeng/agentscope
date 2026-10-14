"""Compatibility facade for the four remote market-data MCP plugins."""

from __future__ import annotations

import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from integrations.market_mcp_plugins import (  # noqa: E402
    MarketMCPPluginBundle,
    load_market_mcp_plugins,
    market_mcp_plugin_catalog,
)
from utils.config import load_json_config  # noqa: E402


def build_market_mcp_clients() -> list:
    """Build the four independent clients for older integration callers."""
    config = load_json_config()
    settings = config.get("mcp_plugins", {})
    token = os.getenv(str(settings.get("token_env", "MARKET_MCP_API_TOKEN")), "").strip()
    return [plugin.build_client(token) for plugin in market_mcp_plugin_catalog(config) if plugin.enabled and token]


async def load_market_mcp_tools() -> list:
    """Discover all tools from the four plugins for registration on an AgentScope agent."""
    bundle: MarketMCPPluginBundle = await load_market_mcp_plugins(load_json_config())
    return bundle.tools
