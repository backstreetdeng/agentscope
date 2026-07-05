"""
自定义大模型适配器示例。

目标：
    展示如何在 AgentScope 2.0.3 稳定版中做二次开发模型适配，
    而不是依赖 2.0.4 dev 的实验接口。

说明：
    本示例继承 OpenAIChatModel，因为 MiniMax、DeepSeek、Moonshot 等服务
    常提供 OpenAI Chat Completions 兼容接口。若某厂商完全不兼容 OpenAI，
    可参考 AgentScope 2.0.3 文档继承 ChatModelBase 并实现 _call_api。
"""

from __future__ import annotations

from typing import Any

from agentscope.credential import OpenAICredential
from agentscope.model import OpenAIChatModel


class BusinessOpenAICompatibleModel(OpenAIChatModel):
    """汽车业务场景 OpenAI 兼容模型适配器。

    这个类只覆盖稳定构造参数，并通过 extra_body 透传厂商扩展字段。
    它没有访问 AgentScope 内部私有运行时，也没有使用 dev-only 参数。
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        temperature: float | None = 0.3,
        top_p: float | None = 0.9,
        max_tokens: int | None = 4096,
        stream: bool = True,
        context_size: int = 128000,
        extra_body: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            credential=OpenAICredential(
                api_key=api_key,
                base_url=base_url,
            ),
            model=model,
            stream=stream,
            context_size=context_size,
            parameters=OpenAIChatModel.Parameters(
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
            ),
            extra_body=extra_body,
        )


def build_custom_adapter_from_config(provider: dict[str, Any], api_key: str) -> BusinessOpenAICompatibleModel:
    """从 model_config/config.json 的 provider 配置创建自定义适配器实例。"""

    return BusinessOpenAICompatibleModel(
        api_key=api_key,
        base_url=provider["base_url"],
        model=provider["model"],
        temperature=provider.get("temperature"),
        top_p=provider.get("top_p"),
        max_tokens=provider.get("max_tokens"),
        stream=bool(provider.get("stream", True)),
        context_size=int(provider.get("context_size", 128000)),
        extra_body=provider.get("extra_body"),
    )
