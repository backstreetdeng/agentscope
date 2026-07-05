"""文本清理工具。"""

from __future__ import annotations

import re


def strip_thinking(text: str) -> str:
    """清理 MiniMax M2.x 或其他推理模型可能返回的 `<think>...</think>` 内容。"""

    return re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL).strip()

