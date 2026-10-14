"""Discover and invoke a remote market MCP server over Streamable HTTP."""

from __future__ import annotations

import argparse
import asyncio

from agentscope.mcp import HttpMCPConfig, MCPClient


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--tool", default="")
    parser.add_argument("--token", default="")
    args = parser.parse_args()

    headers = {"Authorization": f"Bearer {args.token}"} if args.token else None
    client = MCPClient(
        name="market_mcp_smoke",
        is_stateful=False,
        mcp_config=HttpMCPConfig(url=args.url, headers=headers, timeout=20),
    )
    tools = await client.list_tools()
    print("tools:", ", ".join(tool.name for tool in tools))
    if args.tool:
        tool = await client.get_tool(args.tool)
        print("result:", await tool(response_format="json"))


if __name__ == "__main__":
    asyncio.run(main())

