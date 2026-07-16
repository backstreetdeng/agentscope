"""文本清理工具。"""

from __future__ import annotations

import re


def strip_thinking(text: str) -> str:
    """只保留可展示的最终正文，绝不把模型推理文本交给业务端。

    MiniMax 的 OpenAI 兼容接口在未启用推理拆分时，可能将推理内容放入
    ``<think>...</think>``。正常情况下可以直接移除完整标签块；如果网络流
    或兼容层只返回了未闭合的 ``<think>``，则无法可靠识别最终答案的起点，
    此时返回空字符串，由调用方提示重试，而不是把推理文本写进报告或 PPT。
    """

    cleaned = re.sub(r"<think>.*?</think>\s*", "", str(text or ""), flags=re.DOTALL | re.IGNORECASE)
    if re.search(r"<think\b", cleaned, flags=re.IGNORECASE):
        return ""
    return cleaned.strip()
