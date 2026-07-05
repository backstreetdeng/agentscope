"""
乘用车市场与产品配置决策 Demo 的本地工具模块。

本文件只使用 AgentScope 2.0.3 稳定版 ToolBase 接口：
    - ToolBase.name / description / input_schema
    - ToolBase.check_permissions(...)
    - ToolBase.call(...)
    - ToolChunk + TextBlock 返回工具结果

未使用 2.0.4 dev 实验接口，也没有依赖未公开的底层运行时。
"""

from __future__ import annotations

import asyncio
import html
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from agentscope.message import TextBlock
from agentscope.permission import (
    PermissionBehavior,
    PermissionContext,
    PermissionDecision,
)
from agentscope.tool import ToolBase, ToolChunk
from skills.anysearch.adapter import search as anysearch_search


TOOL_CALL_EVENTS: list[dict[str, Any]] = []
PROJECT_DIR = Path(__file__).resolve().parents[1]


def clear_tool_call_events() -> None:
    """清空本轮 Agent 调用的工具审计日志。

    Web 演示会在每次请求前清空日志，请求后把日志返回给前端。
    这样可以区分“模型声称使用了某工具”和“后端确实执行了某工具”。
    """

    TOOL_CALL_EVENTS.clear()


def get_tool_call_events() -> list[dict[str, Any]]:
    """返回本轮工具审计日志副本。"""

    return list(TOOL_CALL_EVENTS)


def record_tool_call(name: str, status: str, detail: str) -> None:
    """记录工具调用事件，避免在日志中写入 API Key 等敏感信息。"""

    try:
        now = datetime.now(ZoneInfo("Asia/Shanghai"))
    except Exception:
        now = datetime.now(timezone.utc)

    TOOL_CALL_EVENTS.append(
        {
            "name": name,
            "status": status,
            "detail": detail[:300],
            "time": now.strftime("%Y-%m-%d %H:%M:%S"),
        },
    )


class ReadOnlyBusinessTool(ToolBase):
    """业务只读工具基类。

    市场分析类工具默认只读取公开信息或本地环境状态，不修改文件和系统状态。
    统一返回 ALLOW，避免 demo 在每次工具调用时进入人工确认流程。
    生产环境可在这里增加域名白名单、审计日志、内网地址拦截等策略。
    """

    is_concurrency_safe = True
    is_read_only = True

    async def check_permissions(
        self,
        tool_input: dict[str, Any],
        context: PermissionContext,
    ) -> PermissionDecision:
        return PermissionDecision(
            behavior=PermissionBehavior.ALLOW,
            message=f"{self.name} 是只读业务工具，允许执行。",
        )


class AnySearchTool(ReadOnlyBusinessTool):
    """AnySearch 实时搜索工具。

    业务定位：
    - 替代原先的时间查询演示按钮，作为市场与用户洞察 Agent 的通用搜索入口。
    - 支持公开网页搜索、新闻搜索、批量查询和 URL 内容提取。
    - 通过项目 .env 或系统环境变量读取 ANYSEARCH_API_KEY。

    稳定版说明：
    这里仍然只是 AgentScope 2.0.3 ToolBase 封装，不使用 MCP 或 2.0.4 dev 接口。
    """

    name = "any_search"
    description = "使用 AnySearch 进行实时网页/新闻搜索，适合获取政策、市场、竞品和用户口碑等公开信息。"
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词或问题。"},
            "max_results": {
                "type": "integer",
                "description": "返回结果数量，默认 5，最大 20。",
                "default": 5,
            },
            "freshness": {
                "type": "string",
                "description": "时间范围，可选 day/week/month/year，默认不限制。",
                "default": "",
            },
            "content_types": {
                "type": "string",
                "description": "内容类型，可选 web/news/code/doc/academic/data/image/video/audio，默认 web,news。",
                "default": "web,news",
            },
        },
        "required": ["query"],
    }

    async def call(
        self,
        query: str,
        max_results: int = 5,
        freshness: str = "",
        content_types: str = "web,news",
    ) -> ToolChunk:
        try:
            returncode, stdout, stderr, cli_path = await asyncio.to_thread(
                anysearch_search,
                query,
                max_results,
                freshness,
                content_types,
            )
            output = stdout or stderr
            status = "success" if returncode == 0 else "error"
            if returncode == 127:
                status = "missing_dependency"
                output = (
                    "AnySearch CLI 未找到。请查看 skills/anysearch/README.md，"
                    f"或在 .env 中配置 ANYSEARCH_CLI_PATH。\n当前路径：{cli_path}"
                )
            record_tool_call(self.name, status, f"query={query}; max_results={max_results}")
            return ToolChunk(content=[TextBlock(text=output or "AnySearch 未返回内容。")])
        except Exception as exc:
            record_tool_call(self.name, "error", f"query={query}; error={type(exc).__name__}: {exc}")
            raise


class WebFetchTool(ReadOnlyBusinessTool):
    """web-fetch 工具。

    用标准库 urllib 抓取公开网页，并做轻量 HTML 正文提取。
    适合读取政策网页、公开新闻、企业公告、文档页面等市场时效信息。
    """

    name = "web_fetch"
    description = "读取 http/https 公开网页并提取简洁文本，适合政策、新闻、文档和公开网页取证。"
    input_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "要读取的 http 或 https URL。"},
            "max_chars": {
                "type": "integer",
                "description": "最多返回字符数，默认 6000，上限 12000。",
                "default": 6000,
            },
        },
        "required": ["url"],
    }

    async def check_permissions(
        self,
        tool_input: dict[str, Any],
        context: PermissionContext,
    ) -> PermissionDecision:
        parsed = urlparse(str(tool_input.get("url", "")))
        if parsed.scheme not in {"http", "https"}:
            return PermissionDecision(
                behavior=PermissionBehavior.DENY,
                message="web_fetch 只允许 http/https URL。",
            )
        return await super().check_permissions(tool_input, context)

    async def call(self, url: str, max_chars: int = 6000) -> ToolChunk:
        try:
            text = await asyncio.to_thread(fetch_url_text, url, max_chars)
            record_tool_call(self.name, "success", f"url={url}")
            return ToolChunk(content=[TextBlock(text=text)])
        except Exception as exc:
            record_tool_call(self.name, "error", f"url={url}; error={type(exc).__name__}: {exc}")
            raise


class TavilySearchTool(ReadOnlyBusinessTool):
    """Tavily 搜索工具。

    通过 TAVILY_API_KEY 调用 Tavily Search API。若未配置 Key，工具会返回
    明确的配置提示，不会让主流程崩溃。
    """

    name = "tavily_search"
    description = "使用 Tavily 搜索公开互联网信息，适合获取市场新闻、政策和行业资讯摘要。"
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词。"},
            "max_results": {
                "type": "integer",
                "description": "返回结果数量，默认 5。",
                "default": 5,
            },
        },
        "required": ["query"],
    }

    async def call(self, query: str, max_results: int = 5) -> ToolChunk:
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            record_tool_call(self.name, "missing_api_key", f"query={query}")
            return ToolChunk(
                content=[
                    TextBlock(
                        text=(
                            "Tavily 未配置：请在 .env 中添加 TAVILY_API_KEY。\n"
                            f"本次查询词：{query}"
                        ),
                    ),
                ],
            )

        payload = {
            "api_key": api_key,
            "query": query,
            "search_depth": "basic",
            "max_results": max(1, min(int(max_results), 10)),
            "include_answer": True,
        }
        try:
            text = await asyncio.to_thread(post_json, "https://api.tavily.com/search", payload)
            record_tool_call(self.name, "success", f"query={query}; max_results={max_results}")
            return ToolChunk(content=[TextBlock(text=text)])
        except Exception as exc:
            record_tool_call(self.name, "error", f"query={query}; error={type(exc).__name__}: {exc}")
            raise


class PlaywrightScraperTool(ReadOnlyBusinessTool):
    """Playwright 动态网页抓取工具。

    用于普通 web_fetch 不能处理的动态页面。首次使用前需要：
        pip install -r requirements.txt
        playwright install chromium
    """

    name = "playwright_scraper"
    description = "使用 Playwright 渲染动态网页并提取页面标题和可见文本。"
    input_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "要渲染抓取的 http/https URL。"},
            "max_chars": {
                "type": "integer",
                "description": "最多返回字符数，默认 6000。",
                "default": 6000,
            },
        },
        "required": ["url"],
    }

    async def check_permissions(
        self,
        tool_input: dict[str, Any],
        context: PermissionContext,
    ) -> PermissionDecision:
        parsed = urlparse(str(tool_input.get("url", "")))
        if parsed.scheme not in {"http", "https"}:
            return PermissionDecision(
                behavior=PermissionBehavior.DENY,
                message="playwright_scraper 只允许 http/https URL。",
            )
        return await super().check_permissions(tool_input, context)

    async def call(self, url: str, max_chars: int = 6000) -> ToolChunk:
        try:
            from playwright.async_api import async_playwright
        except Exception:
            record_tool_call(self.name, "missing_dependency", "playwright is not available")
            return ToolChunk(
                content=[
                    TextBlock(
                        text=(
                            "Playwright 未安装或不可用。请执行：\n"
                            "pip install -r requirements.txt\n"
                            "playwright install chromium"
                        ),
                    ),
                ],
            )

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, wait_until="networkidle", timeout=15000)
            title = await page.title()
            body_text = await page.locator("body").inner_text(timeout=5000)
            await browser.close()

        body_text = normalize_text(body_text)
        max_chars = max(500, min(int(max_chars), 12000))
        if len(body_text) > max_chars:
            body_text = body_text[:max_chars] + "\n\n[内容已截断]"

        record_tool_call(self.name, "success", f"url={url}; title={title}")
        return ToolChunk(
            content=[TextBlock(text=f"URL: {url}\nTitle: {title}\n\n{body_text}")],
        )


def tool(name: str, description: str) -> Callable:
    """本地 agent-reach 风格 @tool 装饰器示例。

    AgentScope 2.0.3 稳定版没有要求使用某个实验装饰器。这里用普通 Python
    装饰器给函数附加元数据，再由 AgentReachDecoratedTool 包装成 ToolBase。
    这样既展示 @tool 二开方式，又不依赖 2.0.4 dev 接口。
    """

    def decorator(func: Callable) -> Callable:
        func.tool_name = name
        func.tool_description = description
        return func

    return decorator


@tool(
    name="agent_reach_search",
    description="调用本机 agent-reach CLI 执行互联网搜索或平台路由查询。",
)
def agent_reach_search_impl(query: str, limit: int = 5) -> str:
    """agent-reach CLI 适配函数。

    若本机未安装 agent-reach，则回退到工程内 AnySearch 适配器。此函数通过装饰器暴露元数据，
    再由 AgentReachDecoratedTool 适配为 AgentScope 2.0.3 ToolBase。
    """

    executable = shutil.which("agent-reach")
    if not executable:
        code, stdout, stderr, cli_path = anysearch_search(query, max_results=limit)
        if code == 0:
            return "agent-reach CLI 未安装，已自动回退到 AnySearch。\n" + (
                stdout or "AnySearch 未返回内容。"
            )
        return (
            "agent-reach CLI 未安装，AnySearch 兜底也未成功。\n"
            f"AnySearch CLI 路径：{cli_path}\n"
            f"错误信息：{stderr or stdout or 'unknown error'}\n"
            f"本次查询词：{query}"
        )

    completed = subprocess.run(
        [executable, "search", query, "--limit", str(max(1, min(int(limit), 10)))],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    output = completed.stdout.strip() or completed.stderr.strip()
    return output or "agent-reach 未返回内容。"


class AgentReachDecoratedTool(ReadOnlyBusinessTool):
    """把 agent_reach_search_impl 这个 @tool 函数包装成 AgentScope 工具。"""

    name = agent_reach_search_impl.tool_name
    description = agent_reach_search_impl.tool_description
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索或调研关键词。"},
            "limit": {"type": "integer", "description": "最多返回数量。", "default": 5},
        },
        "required": ["query"],
    }

    async def call(self, query: str, limit: int = 5) -> ToolChunk:
        text = await asyncio.to_thread(agent_reach_search_impl, query, limit)
        status = "success" if "未成功" not in text else "error"
        record_tool_call(self.name, status, f"query={query}; limit={limit}")
        return ToolChunk(content=[TextBlock(text=text)])


class UserInsightTaggerTool(ReadOnlyBusinessTool):
    """用户洞察自动打标签工具。

    适用输入：
    - 用户访谈音频的 ASR 转写稿
    - 群访谈纪要
    - 深访逐字稿
    - 车主口碑评论、论坛评论、销售线索备注

    当前版本是规则+词典的轻量打标器，适合 Demo 和冷启动。
    后续可升级为：
    - LLM 二次抽取
    - 向量检索相似用户原声
    - 监督学习分类器
    - 接入调研平台 MCP 批量处理访谈项目
    """

    name = "user_insight_tagger"
    description = "对访谈转写稿、车主评论、口碑文本进行用户圈层、需求、配置诉求和情绪强度自动打标签。"
    input_schema = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "访谈转写稿、评论或用户原声文本。"},
            "source_type": {
                "type": "string",
                "description": "来源类型，如 interview/focus_group/depth_interview/owner_review/social_comment。",
                "default": "owner_review",
            },
        },
        "required": ["text"],
    }

    TAG_RULES = {
        "user_segment": {
            "城市家庭": ["孩子", "老人", "家庭", "后排", "安全座椅", "露营", "周末"],
            "年轻首购": ["第一辆", "首购", "年轻", "颜值", "智能", "科技", "好玩"],
            "增换购": ["换车", "原来", "油车", "升级", "置换", "第二辆"],
            "运营用户": ["网约", "营运", "跑车", "接单", "成本", "电耗"],
            "科技尝鲜": ["智驾", "激光雷达", "OTA", "座舱", "芯片", "自动驾驶"],
        },
        "needs": {
            "续航补能": ["续航", "充电", "快充", "超充", "补能", "电耗", "里程焦虑"],
            "智能驾驶": ["智驾", "辅助驾驶", "NOA", "激光雷达", "自动泊车", "高快领航"],
            "智能座舱": ["车机", "屏幕", "语音", "座舱", "导航", "应用", "娱乐"],
            "空间舒适": ["空间", "后排", "座椅", "通风", "按摩", "悬架", "舒适"],
            "安全可靠": ["安全", "刹车", "碰撞", "电池安全", "可靠", "质量"],
            "价格价值": ["价格", "优惠", "性价比", "贵", "便宜", "保值", "预算"],
        },
        "config": {
            "800V高压平台": ["800V", "快充", "超充", "5C"],
            "热泵空调": ["热泵", "冬天", "低温", "续航衰减"],
            "激光雷达": ["激光雷达", "智驾", "NOA"],
            "大电池长续航": ["长续航", "大电池", "里程"],
            "舒适座椅": ["座椅", "通风", "加热", "按摩"],
            "智能座舱芯片": ["车机", "芯片", "流畅", "卡顿"],
            "家庭娱乐配置": ["后排屏", "冰箱", "音响", "娱乐"],
        },
    }

    async def call(self, text: str, source_type: str = "owner_review") -> ToolChunk:
        normalized = normalize_text(text)
        result: dict[str, Any] = {
            "source_type": source_type,
            "text_length": len(normalized),
            "user_segment": self._match_group(normalized, self.TAG_RULES["user_segment"]),
            "needs": self._match_group(normalized, self.TAG_RULES["needs"]),
            "config": self._match_group(normalized, self.TAG_RULES["config"]),
            "sentiment": self._sentiment(normalized),
            "evidence_quotes": self._quotes(normalized),
            "next_step": "建议把音频先通过 ASR 转写，再批量调用本工具形成用户标签表和配置需求矩阵。",
        }
        record_tool_call(self.name, "success", f"source_type={source_type}; text_length={len(normalized)}")
        return ToolChunk(content=[TextBlock(text=json.dumps(result, ensure_ascii=False, indent=2))])

    @staticmethod
    def _match_group(text: str, rules: dict[str, list[str]]) -> list[dict[str, Any]]:
        hits = []
        for tag, keywords in rules.items():
            matched = [word for word in keywords if word.lower() in text.lower()]
            if matched:
                hits.append({"tag": tag, "score": min(1.0, 0.25 * len(matched)), "keywords": matched[:6]})
        return sorted(hits, key=lambda item: item["score"], reverse=True)

    @staticmethod
    def _sentiment(text: str) -> dict[str, Any]:
        positive = ["满意", "喜欢", "舒服", "放心", "省钱", "好用", "流畅", "惊喜"]
        negative = ["不满意", "焦虑", "担心", "太贵", "卡顿", "异响", "麻烦", "后悔"]
        pos = sum(1 for word in positive if word in text)
        neg = sum(1 for word in negative if word in text)
        label = "positive" if pos > neg else "negative" if neg > pos else "neutral"
        return {"label": label, "positive_hits": pos, "negative_hits": neg}

    @staticmethod
    def _quotes(text: str) -> list[str]:
        parts = re.split(r"[。！？!?；;\n]", text)
        return [part.strip() for part in parts if len(part.strip()) >= 8][:5]


def build_business_toolkit() -> list[ToolBase]:
    """统一生成两个业务 Agent 可复用的工具列表。"""

    return [
        AnySearchTool(),
        WebFetchTool(),
        TavilySearchTool(),
        PlaywrightScraperTool(),
        AgentReachDecoratedTool(),
        UserInsightTaggerTool(),
    ]


def fetch_url_text(url: str, max_chars: int) -> str:
    """抓取公开网页并返回简化文本。"""

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("只支持 http/https URL。")

    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 AgentScope203AutoDecisionDemo/1.0",
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.8",
        },
    )

    try:
        with urlopen(request, timeout=15) as response:
            raw = response.read(1024 * 1024)
            content_type = response.headers.get("Content-Type", "")
            charset = response.headers.get_content_charset() or "utf-8"
    except HTTPError as error:
        raise RuntimeError(f"HTTP {error.code}: {error.reason}") from error
    except URLError as error:
        raise RuntimeError(f"网络访问失败：{error.reason}") from error

    decoded = raw.decode(charset, errors="replace")
    if "text/html" in content_type or "<html" in decoded[:500].lower():
        decoded = html_to_text(decoded)

    decoded = normalize_text(decoded)
    max_chars = max(500, min(int(max_chars), 12000))
    if len(decoded) > max_chars:
        decoded = decoded[:max_chars] + "\n\n[内容已截断]"
    return f"URL: {url}\nContent-Type: {content_type}\n\n{decoded}"


def post_json(url: str, payload: dict[str, Any]) -> str:
    """用标准库 POST JSON，避免额外 Tavily SDK 依赖。"""

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=20) as response:
        raw = response.read(1024 * 1024)
    obj = json.loads(raw.decode("utf-8", errors="replace"))
    answer = obj.get("answer") or ""
    results = obj.get("results") or []
    lines = [f"Tavily answer: {answer}".strip()]
    for index, item in enumerate(results, start=1):
        lines.append(
            "\n".join(
                [
                    f"{index}. {item.get('title', '无标题')}",
                    f"URL: {item.get('url', '')}",
                    f"摘要: {item.get('content', '')}",
                ],
            ),
        )
    return "\n\n".join(lines).strip()


def html_to_text(markup: str) -> str:
    """轻量 HTML 转文本，保留标题和正文可读片段。"""

    markup = re.sub(r"(?is)<(script|style|noscript).*?>.*?</\1>", " ", markup)
    title_match = re.search(r"(?is)<title[^>]*>(.*?)</title>", markup)
    title = html.unescape(re.sub(r"\s+", " ", title_match.group(1)).strip()) if title_match else ""
    text = re.sub(r"(?is)<br\s*/?>", "\n", markup)
    text = re.sub(r"(?is)</(p|div|h[1-6]|li|tr|section|article)>", "\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = html.unescape(text)
    text = normalize_text(text)
    return f"Title: {title}\n\n{text}" if title else text


def normalize_text(text: str) -> str:
    """压缩空白，提升工具返回给模型的上下文质量。"""

    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
