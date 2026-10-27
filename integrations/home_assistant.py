"""Lightweight conversational assistant with only market-data query tools."""
from __future__ import annotations

import asyncio
import logging
import json
from datetime import datetime

from agentscope.agent import Agent, ReActConfig
from agentscope.message import UserMsg
from agentscope.tool import Toolkit

from integrations.market_mcp_plugins import load_market_mcp_plugins
from utils.model_factory import build_model

logger = logging.getLogger(__name__)

# MCP plugins are optional for the home assistant.  Discovery is bounded so a
# slow upstream MCP server never blocks the user-facing chat.
MCP_DISCOVERY_TIMEOUT_SECONDS = 10.0
# Per-request budget for the LLM + tool calls.  Keep this comfortably below the
# frontend's 210s abort so we always have time to package a graceful response.
AGENT_REPLY_TIMEOUT_SECONDS = 180.0

_UNAVAILABLE_FALLBACK = "市场数据 MCP 插件（当前不可用）"


async def answer_home_question(config: dict, messages: list[dict]) -> dict:
    from utils.model_routing import route_model
    config = route_model(config,question=str(messages[-1].get('content','')) if messages else '')
    from integrations.forecast_engine_runtime import is_forecast_question, run_forecast_engine_agent
    if messages and is_forecast_question(str(messages[-1].get('content',''))):
        return await run_forecast_engine_agent(config, str(messages[-1]['content']))
    try:
        bundle = await asyncio.wait_for(
            load_market_mcp_plugins(config, agent_key="market_strategy"),
            timeout=MCP_DISCOVERY_TIMEOUT_SECONDS,
        )
        tools = [
            tool for tool in bundle.tools
            if any(w in tool.name.lower() for w in ("search", "get_", "query", "compare", "status", "changes", "active"))
            and not any(w in tool.name.lower() for w in ("export", "import", "update", "delete", "sync"))
        ]
        unavailable = [item.display_name for item in bundle.statuses if item.status != "ready"]
        mcp_degraded = not tools
    except asyncio.TimeoutError:
        logger.warning("MCP plugin discovery timed out after %.1fs; falling back to plain LLM.", MCP_DISCOVERY_TIMEOUT_SECONDS)
        tools = []
        unavailable = [_UNAVAILABLE_FALLBACK]
        mcp_degraded = True
    except Exception as exc:
        logger.warning("MCP plugin discovery failed: %s; falling back to plain LLM.", exc)
        tools = []
        unavailable = [_UNAVAILABLE_FALLBACK]
        mcp_degraded = True

    if mcp_degraded:
        tool_guidance = (
            "当前 MCP 数据工具不可用，请基于通用知识直接作答，"
            "并明确说明无法核实实时数据，禁止编造具体政策、车型、价格或口碑数字。"
        )
    else:
        tool_guidance = (
            "涉及政策、权益、新车、口碑事实时，优先调用工具获取真实数据并注明来源与日期；"
            "工具未返回结果或数据缺失时如实说明，禁止编造。"
        )

    prompt = (
        "你是市场情报 AI 助手，用简洁自然的中文回答用户当前问题，并结合会话中的追问。"
        "普通问题直接回答，不强制套用报告章节。涉及政策、权益、新车、口碑事实时，"
        + tool_guidance +
        "会话中的旧答案不是核实证据。不要透露模型内部思考。你只提供问答与只读数据查询。"
        "月报、预测、导出及维护任务请引导到已有工作台，不声称执行这些任务。"
        f"当前日期：{datetime.now().date().isoformat()}。"
        f"当前不可用的数据源：{'、'.join(unavailable) or '无'}。"
    )
    agent = Agent(
        name="市场情报AI助手", system_prompt=prompt,
        model=build_model(config, max_tokens_override=4096),
        toolkit=Toolkit(tools=tools), react_config=ReActConfig(max_iters=6),
    )
    reply = await asyncio.wait_for(agent.reply(UserMsg(
        name="业务用户", content="以下为会话历史，最后一条是当前问题：\n" + json.dumps(messages, ensure_ascii=False),
    )), timeout=AGENT_REPLY_TIMEOUT_SECONDS)
    from main import strip_thinking
    answer = strip_thinking(reply.get_text_content())
    if not answer:
        raise RuntimeError("模型未返回可展示的回答，请重试。")
    return {"answer": answer, "model_provider": config['active_provider']}
