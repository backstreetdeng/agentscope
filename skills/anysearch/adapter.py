"""AnySearch 工程内适配器。

本文件把外部 AnySearch CLI 包装成项目内稳定函数，供 tools/custom_tools.py 调用。
如果外部 skill 目录移动，只需要修改 ANYSEARCH_CLI_PATH 环境变量或本文件默认路径。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


DEFAULT_ANYSEARCH_CLI = (
    Path.home() / ".agents" / "skills" / "anysearch" / "scripts" / "anysearch_cli.py"
)


def resolve_cli_path() -> Path:
    """解析 AnySearch CLI 路径。"""

    configured = os.getenv("ANYSEARCH_CLI_PATH", "").strip()
    if configured:
        return Path(configured)
    return DEFAULT_ANYSEARCH_CLI


def search(
    query: str,
    max_results: int = 5,
    freshness: str = "",
    content_types: str = "web,news",
    timeout: int = 45,
) -> tuple[int, str, str, Path]:
    """调用 AnySearch CLI 执行通用搜索。

    返回值：
    - returncode
    - stdout
    - stderr
    - cli_path
    """

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

