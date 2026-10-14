"""Verify all four deployed MCP endpoints with the official MCP client."""

from __future__ import annotations

import argparse
import asyncio

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


ENDPOINTS = {
    "policy": "/mcp/policy",
    "rights": "/mcp/rights",
    "new-car": "/mcp/new-car",
    "reputation": "/mcp/reputation",
}


def error_messages(exc: BaseException) -> list[str]:
    """Flatten AnyIO/asyncio exception groups into useful endpoint errors."""
    nested = getattr(exc, "exceptions", None)
    if nested:
        messages: list[str] = []
        for child in nested:
            messages.extend(error_messages(child))
        return messages
    message = str(exc).strip() or repr(exc)
    return [f"{type(exc).__name__}: {message}"]


async def verify(name: str, url: str, token: str) -> tuple[str, list[str], list[str]]:
    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with httpx.AsyncClient(headers=headers, timeout=30) as http_client:
            async with streamable_http_client(url, http_client=http_client) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    return name, [tool.name for tool in tools.tools], []
    except BaseException as exc:
        return name, [], error_messages(exc)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True, help="Example: http://192.168.3.146:8790")
    parser.add_argument("--token", required=True)
    args = parser.parse_args()
    results = []
    for name, path in ENDPOINTS.items():
        url = args.base_url.rstrip("/") + path
        result = await verify(name, url, args.token)
        results.append((url, result))

    failed = False
    for url, (name, tools, errors) in results:
        if errors:
            failed = True
            print(f"{name}: FAILED - {url}")
            for error in errors:
                print(f"  {error}")
        else:
            print(f"{name}: OK ({len(tools)} tools) - {', '.join(tools)}")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
