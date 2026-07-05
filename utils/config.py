"""工程配置加载工具。

本文件集中管理项目根目录、.env 路径和模型配置路径，避免业务 Agent、Web 前端、
命令行入口各自硬编码路径。这里不使用任何 AgentScope 2.0.4 dev 接口。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_DIR / ".env"
CONFIG_PATH = PROJECT_DIR / "model_config" / "config.json"


def load_json_config() -> dict[str, Any]:
    """读取统一模型与 Agent 配置。

    二次开发时优先修改 model_config/config.json：
    - active_provider：切换 MiniMax、OpenAI 兼容云模型、本地 Ollama、自定义适配器
    - providers：维护不同模型端点
    - agents：维护不同智能体的名称和 ReAct 最大轮数
    - demo_tasks：维护命令行 Demo 的默认任务
    """

    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def expand_env(value: Any) -> Any:
    """解析 `${ENV_NAME}` 形式的环境变量占位符。"""

    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        return os.getenv(value[2:-1], "")
    return value

