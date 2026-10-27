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
from urllib.parse import urlparse
from typing import Any

import httpx

from agentscope.credential import OllamaCredential, OpenAICredential
from agentscope.model import OllamaChatModel, OpenAIChatModel

from model_adapters.local_adapter import build_custom_adapter_from_config
from utils.config import expand_env


def _proxy_client_kwargs() -> dict[str, Any] | None:
    """Build an ``http_client`` kwarg when HTTP(S)_PROXY is set in the env.

    The openai SDK does not read proxy variables on its own; we hand-roll an
    ``httpx.AsyncClient`` with explicit ``proxy=`` so the home assistant and
    other LLM calls go through a local proxy (e.g. when running behind
    aTrust/VPN or a corporate forward proxy).
    """
    http_proxy = os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
    https_proxy = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")
    if not (http_proxy or https_proxy):
        return None
    proxy_url = https_proxy or http_proxy
    if proxy_url and not proxy_url.startswith(("http://", "https://", "socks5://", "socks5h://")):
        proxy_url = "http://" + proxy_url
    client = httpx.AsyncClient(
        proxy=proxy_url,
        timeout=httpx.Timeout(60.0, connect=15.0),
    )
    return {"http_client": client}


def build_model(config: dict[str, Any], max_tokens_override: int | None = None):
    """基于 model_config/config.json 创建模型实例。

    支持三类模型：
    1. openai_compatible：MiniMax、DeepSeek、Moonshot 等兼容 OpenAI Chat Completions 的云端模型
    2. ollama：本地 Ollama 模型
    3. custom_openai_compatible：二次开发自定义适配器示例
    """

    provider_name = config["active_provider"]
    provider = dict(config["providers"][provider_name])
    if provider.get("enabled") is False:
        raise RuntimeError(
            str(provider.get("availability_note"))
            or f"模型提供方 {provider_name} 当前不可用。"
        )
    provider_type = provider["type"]
    provider["model"] = expand_env(provider.get("model", ""))
    host=urlparse(provider.get('base_url','')).hostname
    if host and host.endswith('minimaxi.com'):
        raise RuntimeError('用户已停用 MiniMax，不允许继续调用。')
    if provider.get('api_key_env') == 'DASHSCOPE_API_KEY' and host != 'api.deepseek.com':
        raise RuntimeError('DASHSCOPE_API_KEY 当前存放 DeepSeek 凭证，只允许发送至 api.deepseek.com。')
    # 月报等长文本任务可通过公开的 ``max_tokens`` 参数单独提高输出额度，
    # 不改变默认对话任务的成本和响应长度。
    if max_tokens_override is not None:
        provider["max_tokens"] = max(1, int(max_tokens_override))

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
            client_kwargs=_proxy_client_kwargs(),
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
