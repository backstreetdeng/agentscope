"""模型工厂。

本文件只使用 AgentScope 2.0.3 稳定正式版模型 API：
- agentscope.model.OpenAIChatModel
- agentscope.model.OllamaChatModel
- agentscope.credential.OpenAICredential
- agentscope.credential.OllamaCredential

不使用 2.0.4 dev 实验接口、临时兼容参数或私有运行时。
"""

from __future__ import annotations

import os
from typing import Any

from agentscope.credential import OllamaCredential, OpenAICredential
from agentscope.model import OllamaChatModel, OpenAIChatModel

from model_adapters.local_adapter import build_custom_adapter_from_config
from utils.config import expand_env


def build_model(config: dict[str, Any]):
    """基于 model_config/config.json 创建模型实例。

    支持三类模型：
    1. openai_compatible：MiniMax、DeepSeek、Moonshot 等兼容 OpenAI Chat Completions 的云端模型
    2. ollama：本地 Ollama 模型
    3. custom_openai_compatible：二次开发自定义适配器示例
    """

    provider_name = config["active_provider"]
    provider = dict(config["providers"][provider_name])
    provider_type = provider["type"]
    provider["model"] = expand_env(provider.get("model", ""))

    if provider_type in {"openai_compatible", "custom_openai_compatible"}:
        api_key_env = provider["api_key_env"]
        api_key = os.getenv(api_key_env)
        if not api_key:
            raise RuntimeError(f"未找到环境变量 {api_key_env}，请检查 .env。")

        if provider_type == "custom_openai_compatible":
            return build_custom_adapter_from_config(provider, api_key)

        return OpenAIChatModel(
            credential=OpenAICredential(
                api_key=api_key,
                base_url=provider["base_url"],
            ),
            model=provider["model"],
            stream=bool(provider.get("stream", True)),
            context_size=int(provider.get("context_size", 128000)),
            parameters=OpenAIChatModel.Parameters(
                temperature=provider.get("temperature"),
                top_p=provider.get("top_p"),
                max_tokens=provider.get("max_tokens"),
            ),
            extra_body=provider.get("extra_body"),
        )

    if provider_type == "ollama":
        return OllamaChatModel(
            credential=OllamaCredential(host=provider.get("host")),
            model=provider["model"],
            stream=bool(provider.get("stream", True)),
            context_size=int(provider.get("context_size", 32768)),
            parameters=OllamaChatModel.Parameters(
                temperature=provider.get("temperature"),
                max_tokens=provider.get("max_tokens"),
            ),
        )

    raise ValueError(f"不支持的 provider type: {provider_type}")

