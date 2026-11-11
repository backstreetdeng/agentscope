"""洞察档案生成的最小同步模型客户端。

固定发送至已核实的 DeepSeek 接口；密钥沿用 `.env` 中的 `DASHSCOPE_API_KEY`
（该变量当前存放用户提供的 DeepSeek 凭证），不打印、不回显。
"""

from __future__ import annotations

import os

import httpx

from competitor_insight.server import db as bci_db

DESTINATION = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-v4-flash"
SYSTEM_PROMPT = (
    "你是用户深访档案抽取助手。只依据用户消息中的访谈材料填写一个维度，"
    '输出严格 JSON：{"value": 字符串或数组, "evidence_ids": ["证据ID"]}。'
    "evidence_ids 只能取自材料中列出的证据 ID；没有依据时 value 输出空字符串且 evidence_ids 为空。"
    "不得编造原话、数字或证据 ID。"
)


class LlmUnavailable(RuntimeError):
    """模型客户端不可用（缺少凭证、网络或响应异常）。"""


def build_deepseek_client(model: str | None = None, system_prompt: str | None = None):
    """返回 ``Callable[[str], str]``；构造期只校验凭证，不发起网络请求。"""

    # 以项目 `.env` 中的 DeepSeek 凭证为准；进程环境变量可能是阿里云 Token Plan
    # 的另一把密钥（长度/产品均不同），不能混用。
    api_key = (
        bci_db.load_env().get("DASHSCOPE_API_KEY")
        or os.getenv("DASHSCOPE_API_KEY")
        or ""
    ).strip()
    if not api_key:
        raise LlmUnavailable("未找到 DASHSCOPE_API_KEY（DeepSeek 凭证）。")
    chosen = (model or os.getenv("BCI_ARCHIVE_LLM_MODEL") or DEFAULT_MODEL).strip()

    def call(prompt: str) -> str:
        payload = {
            "model": chosen,
            "messages": [
                {"role": "system", "content": system_prompt or SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        try:
            response = httpx.post(
                DESTINATION,
                json=payload,
                headers={"Authorization": "Bearer " + api_key},
                timeout=httpx.Timeout(180.0, connect=15.0),
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            raise LlmUnavailable(f"模型调用失败：{exc.__class__.__name__}") from exc
        if not isinstance(content, str) or not content.strip():
            raise LlmUnavailable("模型返回为空。")
        return content

    call.model = chosen  # type: ignore[attr-defined]
    return call
