"""Bounded Playwright MCP diagnostics for AgentScope 2.0.3.

The probe bypasses Agent/LLM orchestration and exercises the transport in this
order: connect, list_tools, browser_tabs, browser_snapshot, browser_navigate,
browser_snapshot. Every operation has its own timeout and timing log.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import time
import traceback
from pathlib import Path
from typing import Any, Awaitable, Callable

from agentscope.mcp import HttpMCPConfig, MCPClient, StdioMCPConfig


PROJECT_DIR = Path(__file__).resolve().parents[1]
CLI_PATH = PROJECT_DIR / "node_modules" / "@playwright" / "mcp" / "cli.js"
PINNED_VERSION = "0.0.82"
TOOLS = ["browser_tabs", "browser_snapshot", "browser_navigate"]


def emit(event: str, **fields: Any) -> None:
    print(
        json.dumps(
            {"event": event, "time": time.strftime("%Y-%m-%dT%H:%M:%S"), **fields},
            ensure_ascii=False,
            default=str,
        ),
        flush=True,
    )


def server_processes() -> list[dict[str, Any]]:
    try:
        import psutil

        matches: list[dict[str, Any]] = []
        for process in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                command = " ".join(process.info.get("cmdline") or [])
                lowered = command.lower()
                if "@playwright" in lowered or "playwright\\mcp\\cli.js" in lowered:
                    matches.append(
                        {
                            "pid": process.info.get("pid"),
                            "name": process.info.get("name"),
                            "command": command,
                        },
                    )
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                continue
        return matches
    except Exception as exc:  # pragma: no cover - diagnostic fallback
        if os.name == "nt":
            try:
                output = subprocess.check_output(
                    [
                        "powershell",
                        "-NoProfile",
                        "-Command",
                        "Get-Process node -ErrorAction SilentlyContinue | "
                        "Select-Object Id,ProcessName | ConvertTo-Json -Compress",
                    ],
                    text=True,
                    timeout=5,
                ).strip()
                parsed = json.loads(output) if output else []
                return parsed if isinstance(parsed, list) else [parsed]
            except Exception as fallback_exc:
                return [
                    {
                        "process_inspection_error": repr(exc),
                        "fallback_error": repr(fallback_exc),
                    },
                ]
        return [{"process_inspection_error": repr(exc)}]


async def step(
    name: str,
    operation: Callable[[], Awaitable[Any]],
    timeout: float,
) -> Any:
    started = time.perf_counter()
    emit(
        "step_start",
        step=name,
        timeout_seconds=timeout,
        server_processes=server_processes(),
    )
    try:
        # asyncio.timeout keeps the operation in the current task.  This is
        # important because MCP/AnyIO cancel scopes must be closed by the same
        # task that entered them; asyncio.wait_for would create a child task.
        async with asyncio.timeout(timeout):
            result = await operation()
    except Exception as exc:
        emit(
            "step_error",
            step=name,
            elapsed_seconds=round(time.perf_counter() - started, 3),
            exception=repr(exc),
            traceback=traceback.format_exc(),
            server_processes=server_processes(),
        )
        raise
    emit(
        "step_ok",
        step=name,
        elapsed_seconds=round(time.perf_counter() - started, 3),
        result_type=type(result).__name__,
        server_processes=server_processes(),
    )
    return result


def preview(result: Any, limit: int = 800) -> str:
    content = getattr(result, "content", None)
    if content is None:
        return repr(result)[:limit]
    pieces = []
    for block in content:
        text = getattr(block, "text", None)
        pieces.append(text if text is not None else repr(block))
    return "\n".join(pieces)[:limit]


def build_client(args: argparse.Namespace) -> tuple[MCPClient, dict[str, Any]]:
    if args.transport == "http":
        config = HttpMCPConfig(url=args.url, timeout=args.timeout)
        details = {
            "transport": "streamable_http",
            "url": args.url,
            "is_stateful": True,
            "execution_timeout": args.timeout,
            "cdp_endpoint": None,
        }
    else:
        if args.stdio_launch == "npx":
            command = shutil.which("npx.cmd") or shutil.which("npx")
            if not command:
                raise RuntimeError("npx is not available on PATH")
            command_args = [
                "-y",
                f"@playwright/mcp@{args.package_version}",
                "--headless",
                "--browser",
                "chrome",
                "--no-sandbox",
                "--proxy-server",
                "http://127.0.0.1:7897",
                "--user-data-dir",
                str(PROJECT_DIR / "runtime" / "playwright-mcp-probe-profile-npx"),
                "--output-dir",
                str(PROJECT_DIR / "runtime" / "playwright-mcp-probe-output-npx"),
                "--no-webmcp",
            ]
        else:
            command = shutil.which("node")
            if not command:
                raise RuntimeError("Node.js is not available on PATH")
            if not CLI_PATH.is_file():
                raise RuntimeError(f"Playwright MCP is not installed: {CLI_PATH}")
            command_args = [
                str(CLI_PATH),
                "--headless",
                "--browser",
                "chrome",
                "--no-sandbox",
                "--proxy-server",
                "http://127.0.0.1:7897",
                "--user-data-dir",
                str(PROJECT_DIR / "runtime" / "playwright-mcp-probe-profile-stdio"),
                "--output-dir",
                str(PROJECT_DIR / "runtime" / "playwright-mcp-probe-output-stdio"),
                "--no-webmcp",
            ]
        local_app_data = PROJECT_DIR / "runtime" / "playwright-mcp-localappdata"
        local_app_data.mkdir(parents=True, exist_ok=True)
        config = StdioMCPConfig(
            command=command,
            args=command_args,
            cwd=PROJECT_DIR,
            env={"LOCALAPPDATA": str(local_app_data)},
        )
        details = {
            "transport": "stdio",
            "command": command,
            "args": command_args,
            "cwd": str(PROJECT_DIR),
            "env": {"LOCALAPPDATA": str(local_app_data)},
            "is_stateful": True,
            "execution_timeout": args.timeout,
            "cdp_endpoint": None,
        }
    return (
        MCPClient(
            name=f"playwright_probe_{args.transport}",
            is_stateful=True,
            mcp_config=config,
            enable_tools=TOOLS,
            execution_timeout=args.timeout,
        ),
        details,
    )


async def run(args: argparse.Namespace) -> int:
    client, details = build_client(args)
    emit(
        "probe_config",
        agentscope_version="2.0.3",
        playwright_mcp_version=args.package_version,
        **details,
    )
    try:
        await step("connect", client.connect, args.timeout)
        raw_tools = await step("list_tools", client.list_raw_tools, args.timeout)
        emit(
            "tools",
            names=[tool.name for tool in raw_tools],
            schemas={tool.name: tool.inputSchema for tool in raw_tools},
        )

        async def invoke(tool_name: str, **kwargs: Any) -> Any:
            tool = await client.get_tool(tool_name)
            result = await tool(**kwargs)
            result_preview = preview(result)
            if result_preview.lstrip().startswith("### Error"):
                raise RuntimeError(f"{tool_name} returned an MCP error: {result_preview}")
            return result

        tabs = await step(
            "browser_tabs",
            lambda: invoke("browser_tabs", action="list"),
            args.timeout,
        )
        emit("tool_result", tool="browser_tabs", preview=preview(tabs))

        before = await step(
            "browser_snapshot_before_navigation",
            lambda: invoke("browser_snapshot"),
            args.timeout,
        )
        emit("tool_result", tool="browser_snapshot", preview=preview(before))

        navigation = await step(
            "browser_navigate",
            lambda: invoke("browser_navigate", url=args.navigate_url),
            args.timeout,
        )
        emit("tool_result", tool="browser_navigate", preview=preview(navigation))

        after = await step(
            "browser_snapshot_after_navigation",
            lambda: invoke("browser_snapshot"),
            args.timeout,
        )
        after_preview = preview(after)
        emit(
            "tool_result",
            tool="browser_snapshot",
            preview=after_preview,
            contains_example_domain="Example Domain" in after_preview,
        )
        emit("probe_complete", ok=True)
        return 0
    except Exception:
        emit(
            "probe_complete",
            ok=False,
            failed_step="see_last_step_error",
            client_connected=client.is_connected,
            server_processes=server_processes(),
        )
        return 1
    finally:
        if client.is_connected:
            try:
                async with asyncio.timeout(10):
                    await client.close()
                emit("client_close", ok=True)
            except Exception as exc:
                emit(
                    "client_close",
                    ok=False,
                    exception=repr(exc),
                    traceback=traceback.format_exc(),
                    server_processes=server_processes(),
                )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=("stdio", "http"), default="stdio")
    parser.add_argument("--stdio-launch", choices=("node", "npx"), default="node")
    parser.add_argument("--package-version", default=PINNED_VERSION)
    parser.add_argument("--url", default="http://127.0.0.1:8931/mcp")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--navigate-url", default="https://example.com")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run(parse_args())))
