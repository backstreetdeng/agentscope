"""Independent remote MCP plugin loader for the four market data domains.

The remote services use stateless Streamable HTTP.  Each domain is discovered
independently so that one unavailable data source does not remove the other
three from an AgentScope agent.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any, Iterable

from agentscope.mcp import HttpMCPConfig, MCPClient


DEFAULT_PLUGINS: dict[str, dict[str, Any]] = {
    "policy": {
        "display_name": "政策数据插件",
        "client_name": "policy_data_mcp",
        "path": "/mcp/policy",
        "timeout": 30.0,
        "agents": ["market_strategy", "user_insight_config"],
    },
    "rights": {
        "display_name": "权益数据插件",
        "client_name": "rights_data_mcp",
        "path": "/mcp/rights",
        "timeout": 30.0,
        "agents": ["market_strategy", "user_insight_config"],
    },
    "new-car": {
        "display_name": "新车数据插件",
        "client_name": "new_car_data_mcp",
        "path": "/mcp/new-car",
        "timeout": 30.0,
        "agents": ["market_strategy", "user_insight_config"],
    },
    "reputation": {
        "display_name": "口碑数据插件",
        "client_name": "reputation_data_mcp",
        "path": "/mcp/reputation",
        "timeout": 60.0,
        "agents": ["market_strategy", "user_insight_config"],
    },
}


def _env_enabled(plugin_id: str, default: bool) -> bool:
    env_name = "MARKET_MCP_" + plugin_id.upper().replace("-", "_") + "_ENABLED"
    raw = os.getenv(env_name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off", "disabled"}


def _flatten_error(exc: BaseException) -> str:
    nested = getattr(exc, "exceptions", None)
    if nested:
        messages = [_flatten_error(child) for child in nested]
        return "; ".join(message for message in messages if message)
    message = str(exc).strip() or type(exc).__name__
    return f"{type(exc).__name__}: {message}"


@dataclass(frozen=True)
class MarketMCPPlugin:
    plugin_id: str
    display_name: str
    client_name: str
    url: str
    timeout: float
    agents: tuple[str, ...]
    enabled: bool = True
    token_env: str = "MARKET_MCP_API_TOKEN"

    def resolve_token(self) -> str:
        """Resolve this endpoint's credential; never fall back across servers."""
        return os.getenv(self.token_env, "").strip()

    def build_client(self, token: str) -> MCPClient:
        headers = {"Authorization": f"Bearer {token}"}
        return MCPClient(
            name=self.client_name,
            is_stateful=False,
            mcp_config=HttpMCPConfig(url=self.url, headers=headers, timeout=self.timeout),
        )


@dataclass
class MarketMCPPluginStatus:
    plugin_id: str
    display_name: str
    url: str
    status: str
    tool_count: int = 0
    tools: list[str] = field(default_factory=list)
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.plugin_id,
            "display_name": self.display_name,
            "url": self.url,
            "status": self.status,
            "tool_count": self.tool_count,
            "tools": list(self.tools),
            "detail": self.detail,
        }


@dataclass
class MarketMCPPluginBundle:
    tools: list[Any] = field(default_factory=list)
    statuses: list[MarketMCPPluginStatus] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        ready = sum(item.status == "ready" for item in self.statuses)
        return {
            "ready": ready,
            "total": len(self.statuses),
            "tool_count": len(self.tools),
            "plugins": [item.as_dict() for item in self.statuses],
        }


def market_mcp_plugin_catalog(
    config: dict[str, Any],
    *,
    agent_key: str | None = None,
    selected_plugin_ids: Iterable[str] | None = None,
) -> list[MarketMCPPlugin]:
    """Build the effective plugin catalog without exposing the API token."""
    settings = config.get("mcp_plugins", {})
    globally_enabled = bool(settings.get("enabled", True))
    base_url = os.getenv(
        str(settings.get("base_url_env", "MARKET_MCP_BASE_URL")),
        str(settings.get("default_base_url", "http://192.168.3.146:8790")),
    ).rstrip("/")
    configured = settings.get("plugins", {})
    selected = set(selected_plugin_ids) if selected_plugin_ids is not None else None
    catalog: list[MarketMCPPlugin] = []
    for plugin_id, defaults in DEFAULT_PLUGINS.items():
        override = configured.get(plugin_id, {}) if isinstance(configured, dict) else {}
        agents = tuple(override.get("agents", defaults["agents"]))
        enabled = globally_enabled and bool(override.get("enabled", True))
        enabled = _env_enabled(plugin_id, enabled)
        if selected is not None:
            enabled = enabled and plugin_id in selected
        if agent_key and agent_key not in agents:
            enabled = False
        path = str(override.get("path", defaults["path"]))
        env_prefix = "MARKET_MCP_" + plugin_id.upper().replace("-", "_")
        url_env = str(override.get("url_env", env_prefix + "_URL"))
        explicit_url = os.getenv(url_env, str(override.get("url", ""))).strip()
        token_env = str(override.get("token_env", (
            env_prefix + "_API_TOKEN" if explicit_url else
            settings.get("token_env", "MARKET_MCP_API_TOKEN")
        )))
        catalog.append(MarketMCPPlugin(
            plugin_id=plugin_id,
            display_name=str(override.get("display_name", defaults["display_name"])),
            client_name=str(override.get("client_name", defaults["client_name"])),
            url=explicit_url or base_url + path,
            timeout=float(override.get("timeout", defaults["timeout"])),
            agents=agents,
            enabled=enabled,
            token_env=token_env,
        ))
    return catalog


async def _discover_plugin(plugin: MarketMCPPlugin, token: str) -> tuple[list[Any], MarketMCPPluginStatus]:
    if not plugin.enabled:
        return [], MarketMCPPluginStatus(
            plugin.plugin_id, plugin.display_name, plugin.url, "disabled", detail="插件未启用",
        )
    if not token:
        return [], MarketMCPPluginStatus(
            plugin.plugin_id,
            plugin.display_name,
            plugin.url,
            "misconfigured",
            detail=f"未配置 {plugin.token_env}",
        )
    try:
        from .rights_tunnel import ensure_tunnel
        await asyncio.to_thread(ensure_tunnel, plugin.url)
        tools = await plugin.build_client(token).list_tools()
        names = [str(tool.name) for tool in tools]
        return list(tools), MarketMCPPluginStatus(
            plugin.plugin_id,
            plugin.display_name,
            plugin.url,
            "ready",
            tool_count=len(names),
            tools=names,
            detail="MCP 工具发现成功",
        )
    except BaseException as exc:
        return [], MarketMCPPluginStatus(
            plugin.plugin_id,
            plugin.display_name,
            plugin.url,
            "unavailable",
            detail=_flatten_error(exc),
        )


async def load_market_mcp_plugins(
    config: dict[str, Any],
    *,
    agent_key: str | None = None,
    selected_plugin_ids: Iterable[str] | None = None,
) -> MarketMCPPluginBundle:
    """Discover enabled plugins independently and return all available tools."""
    catalog = market_mcp_plugin_catalog(
        config,
        agent_key=agent_key,
        selected_plugin_ids=selected_plugin_ids,
    )
    results = await asyncio.gather(*(_discover_plugin(plugin, plugin.resolve_token()) for plugin in catalog))
    tools: list[Any] = []
    statuses: list[MarketMCPPluginStatus] = []
    for plugin_tools, status in results:
        tools.extend(plugin_tools)
        statuses.append(status)
    return MarketMCPPluginBundle(tools=tools, statuses=statuses)

