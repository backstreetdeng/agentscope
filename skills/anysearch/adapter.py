"""AnySearch 工程内适配器。

本文件把外部 AnySearch 能力包装成项目内稳定函数，供 tools/custom_tools.py 调用。
优先走 HTTP API（配置 ANYSEARCH_API_KEY 即可，无需本地 CLI）；CLI 作为后备路径。
如果外部 skill 目录移动，只需要修改 ANYSEARCH_CLI_PATH 环境变量或本文件默认路径。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path


DEFAULT_ANYSEARCH_CLI = (
    Path.home() / ".agents" / "skills" / "anysearch" / "scripts" / "anysearch_cli.py"
)

ANYSEARCH_API_BASE = os.getenv("ANYSEARCH_API_BASE", "https://api.anysearch.com")


def resolve_cli_path() -> Path:
    """解析 AnySearch CLI 路径。"""

    configured = os.getenv("ANYSEARCH_CLI_PATH", "").strip()
    if configured:
        return Path(configured)
    return DEFAULT_ANYSEARCH_CLI


def search_http(query: str, max_results: int = 5, timeout: int = 30):
    """直连 AnySearch REST API。返回 (rc, stdout, stderr, marker)；无 key 返回 None。

    stdout 为与 CLI 输出兼容的格式化文本（编号 + URL + 摘要），供业务工具直接展示。
    """
    api_key = os.getenv("ANYSEARCH_API_KEY", "").strip()
    if not api_key:
        return None
    payload = {"query": query, "max_results": max(1, min(int(max_results), 20))}
    request = urllib.request.Request(
        ANYSEARCH_API_BASE + "/v1/search",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        obj = json.loads(response.read(1024 * 1024).decode("utf-8", errors="replace"))
    if obj.get("code") not in (0, "0"):
        raise RuntimeError(f"AnySearch API code={obj.get('code')}: {obj.get('message')}")
    results = (obj.get("data") or {}).get("results") or []
    lines = []
    for index, item in enumerate(results, start=1):
        lines.append(
            "\n".join(
                [
                    f"{index}. {item.get('title', '无标题')}",
                    f"URL: {item.get('url', '')}",
                    f"摘要: {item.get('snippet', '')}",
                ]
            )
        )
    output = "\n\n".join(lines) if lines else "AnySearch 未返回内容。"
    return 0, output, "", Path("http-rest")


def search(
    query: str,
    max_results: int = 5,
    freshness: str = "",
    content_types: str = "web,news",
    timeout: int = 45,
) -> tuple[int, str, str, Path]:
    """调用 AnySearch 执行通用搜索：HTTP API 优先，CLI 后备。

    返回值：
    - returncode
    - stdout
    - stderr
    - cli_path
    """

    try:
        http_result = search_http(query, max_results)
        if http_result is not None:
            return http_result
    except Exception as exc:
        # HTTP 失败不直接放弃，落到 CLI 后备；两个通道都失败才向上报错。
        cli_path = resolve_cli_path()
        return 1, "", f"AnySearch HTTP error: {exc}", cli_path

    cli_path = resolve_cli_path()
    if not cli_path.is_file():
        return 127, "", f"AnySearch CLI not found: {cli_path}", cli_path

    command = [sys.executable, str(cli_path)]
    api_key = os.getenv("ANYSEARCH_API_KEY")
    if api_key:
        command.extend(["--api_key", api_key])

    command.extend(
        [
            "search",
            query,
            "--max_results",
            str(max(1, min(int(max_results), 20))),
        ],
    )
    if freshness:
        command.extend(["--freshness", freshness])
    if content_types:
        command.extend(["--content_types", content_types])

    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip(), cli_path

