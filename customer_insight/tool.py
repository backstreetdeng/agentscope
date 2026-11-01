"""interview_evidence_search AgentScope Tool：把访谈证据检索服务包装为只读业务工具。"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from agentscope.message import TextBlock
from agentscope.tool import ToolChunk

from customer_insight.retrieval_service import InterviewRetrievalService
from tools.custom_tools import ReadOnlyBusinessTool, record_tool_call


class InterviewEvidenceSearchTool(ReadOnlyBusinessTool):
    """从 63 位受访者的真实访谈证据库检索可引用原话。

    返回结构化证据：匿名受访者编号、城市、车型、购车类型、题号、说话人、
    秒级/段落时间、原文、置信度和来源校验和。原话只来自数据库，不生成或改写。
    """

    name = "interview_evidence_search"
    description = (
        "从 63 位乘用车受访者的真实访谈证据库中检索可引用的原话证据，"
        "返回受访者匿名编号、城市、车型、购车类型、题号、说话人、时间戳和原文。"
        "用于需要真实用户原声佐证的问题；没有命中时返回空证据，不得编造访谈观点。"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "要检索的访谈问题或关注点。"},
            "filters": {
                "type": "object",
                "description": "可选结构化过滤，键限 city/vehicle_model/purchase_type/question_ids/tag_names/tag_values/respondent_codes，值为字符串或字符串数组。",
            },
            "top_k": {"type": "integer", "description": "返回证据条数，默认 6，最大 8。", "default": 6},
        },
        "required": ["question"],
    }

    async def call(
        self,
        question: str,
        filters: dict[str, Any] | None = None,
        top_k: int = 6,
    ) -> ToolChunk:
        try:
            service = InterviewRetrievalService()
            result = await asyncio.to_thread(service.search, question, filters, top_k)
            record_tool_call(
                self.name,
                "success",
                f"question={question[:80]}; evidence={len(result.get('evidence', []))}",
            )
            return ToolChunk(
                content=[TextBlock(text=json.dumps(result, ensure_ascii=False, default=str))],
            )
        except Exception as exc:
            record_tool_call(
                self.name,
                "error",
                f"question={question[:80]}; error={type(exc).__name__}: {exc}",
            )
            raise
