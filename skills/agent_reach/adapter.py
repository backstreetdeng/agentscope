"""Agent Reach 的项目内稳定适配层。

Agent Reach 本身是互联网能力路由器，不直接提供 ``agent-reach search`` 命令。
本适配器固定使用其推荐的 Exa MCP 路由：

``mcporter call exa.web_search_exa query=<查询> numResults=<数量>``

调用方只接收结构化的来源、链接、发布日期和摘要，避免把 CLI 原始输出、错误信息或
环境配置泄漏给 Agent 或前端。模块只使用 Python 标准库，不新增虚拟环境依赖。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse


PROJECT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_TIMEOUT_SECONDS = 45
MAX_RESULTS = 8

# 月报优先使用可复核的行业、政府和主机厂来源。搜索结果的等级用于提示模型和门禁，
# 不会把二级媒体的摘要伪装成一手事实。
PRIMARY_DOMAIN_SUFFIXES = (
    ".gov.cn",
    "miit.gov.cn",
    "ndrc.gov.cn",
    "caam.org.cn",
    "cada.cn",
    "cpcaauto.com",
    "catarc.ac.cn",
)
OFFICIAL_OEM_DOMAIN_SUFFIXES = (
    "byd.com",
    "denza.com",
    "buick.com.cn",
    "li.com",
    "nio.com",
    "zeekrlife.com",
    "saic-gm.com",
    "greatwall.com.cn",
)
INDUSTRY_DOMAIN_SUFFIXES = (
    "gasgoo.com",
    "marklines.com",
    "autohome.com.cn",
    "bitauto.com",
    "cheyong.com",
    "d1ev.com",
    "nevofocus.com",
)


@dataclass(frozen=True)
class EvidenceItem:
    """一条可进入市场报告证据包的外部来源。

    ``highlights`` 只是检索摘要而不是报告结论；写作时仍需结合内部销量事实，并以
    ``evidence_id`` 建立可审计引用。
    """

    title: str
    url: str
    published: str = ""
    author: str = ""
    highlights: str = ""
    source_tier: str = "C"
    provider: str = "agent-reach/exa"
    query: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "title": self.title,
            "url": self.url,
            "published": self.published,
            "author": self.author,
            "highlights": self.highlights,
            "source_tier": self.source_tier,
            "provider": self.provider,
            "query": self.query,
        }


@dataclass(frozen=True)
class SearchResponse:
    """一次 Agent Reach 检索或抓取的稳定返回结构。"""

    ok: bool
    operation: str
    query: str = ""
    items: tuple[EvidenceItem, ...] = ()
    raw_text: str = ""
    error: str = ""

    def to_agent_text(self) -> str:
        """输出给 AgentScope 工具的无密钥、可读文本。"""

        if not self.ok:
            return f"Agent Reach {self.operation} 失败：{self.error or '未返回可用结果。'}"
        if not self.items:
            return f"Agent Reach {self.operation} 未返回可解析来源。"
        lines = [f"Agent Reach / Exa 已检索到 {len(self.items)} 条来源："]
        for index, item in enumerate(self.items, 1):
            line = f"{index}. [{item.source_tier}级] {item.title}\n   URL: {item.url}"
            if item.published:
                line += f"\n   发布日期: {item.published}"
            if item.highlights:
                line += f"\n   摘要: {item.highlights[:700]}"
            lines.append(line)
        return "\n".join(lines)


def doctor(timeout_seconds: int = 120) -> SearchResponse:
    """执行 Agent Reach 健康检查，供状态页或人工排障使用。

    正常月报执行不调用本函数，避免每次报告额外等待多个渠道的网络检查。
    """

    executable = shutil.which("agent-reach")
    if not executable:
        return SearchResponse(False, "doctor", error="未找到 agent-reach CLI。")
    completed = _run([executable, "doctor", "--json"], timeout_seconds)
    if completed.returncode != 0:
        return SearchResponse(False, "doctor", error=_command_error(completed))
    return SearchResponse(True, "doctor", raw_text=completed.stdout.strip())


def _mcporter_executable() -> str | None:
    executable = shutil.which("mcporter")
    if executable:
        return executable
    local = PROJECT_DIR / "runtime" / "tool-bin" / "mcporter.cmd"
    return str(local) if local.is_file() else None


def search(query: str, max_results: int = 5, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> SearchResponse:
    """通过 Agent Reach 推荐的 Exa MCP 搜索公开专业资料。"""

    normalized_query = " ".join(str(query or "").split())
    if not normalized_query:
        return SearchResponse(False, "search", error="查询词不能为空。")

    executable = _mcporter_executable()
    if not executable:
        return SearchResponse(False, "search", query=normalized_query, error="未找到 mcporter，无法调用 Agent Reach 的 Exa 路由。")

    result_count = max(1, min(int(max_results), MAX_RESULTS))
    completed = _run(
        [
            executable,
            "call",
            "exa.web_search_exa",
            f"query={normalized_query}",
            f"numResults={result_count}",
            "objective=Find relevant authoritative sources answering the query; preserve "
            "source URLs, publication dates, and factual context. Query: " + normalized_query[:3000],
            "--output",
            "json",
            "--timeout",
            str(max(1000, int(timeout_seconds) * 1000)),
        ],
        timeout_seconds + 5,
    )
    if completed.returncode != 0:
        return SearchResponse(False, "search", query=normalized_query, error=_command_error(completed))

    raw_text = extract_mcporter_text(completed.stdout)
    items = tuple(parse_exa_search_items(raw_text, normalized_query))
    if not items:
        return SearchResponse(
            False,
            "search",
            query=normalized_query,
            raw_text=raw_text[:2000],
            error="Exa 返回成功，但未解析出带 URL 的来源。",
        )
    return SearchResponse(True, "search", query=normalized_query, items=items, raw_text=raw_text)


def fetch_pages(urls: Iterable[str], max_characters: int = 3000, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> SearchResponse:
    """读取已检索来源的正文，用于人工复核或后续更严格的证据提取。

    抓取失败不会影响已有搜索摘要；月报运行时优先使用搜索结果中可追溯的摘要，避免
    单个站点反爬或超时阻塞整份报告。
    """

    clean_urls = [url for url in dict.fromkeys(str(item).strip() for item in urls) if is_http_url(url)]
    if not clean_urls:
        return SearchResponse(False, "fetch", error="没有可抓取的 http/https URL。")
    executable = _mcporter_executable()
    if not executable:
        return SearchResponse(False, "fetch", error="未找到 mcporter，无法调用 Agent Reach 的 Exa 路由。")

    completed = _run(
        [
            executable,
            "call",
            "exa.web_fetch_exa",
            "urls=" + json.dumps(clean_urls, ensure_ascii=False),
            f"maxCharacters={max(500, min(int(max_characters), 8000))}",
            "--output",
            "json",
            "--timeout",
            str(max(1000, int(timeout_seconds) * 1000)),
        ],
        timeout_seconds + 5,
    )
    if completed.returncode != 0:
        return SearchResponse(False, "fetch", error=_command_error(completed))
    return SearchResponse(True, "fetch", raw_text=extract_mcporter_text(completed.stdout))


def parse_exa_search_items(raw_text: str, query: str = "") -> list[EvidenceItem]:
    """解析 Exa 标准文本块，兼容缺少作者或发布日期的公开页面。"""

    items: list[EvidenceItem] = []
    for block in re.split(r"(?m)^---\s*$", raw_text or ""):
        title = extract_field(block, "Title")
        url = extract_field(block, "URL")
        if not title or not is_http_url(url):
            continue
        highlights = extract_tail(block, "Highlights")
        items.append(
            EvidenceItem(
                title=title,
                url=url,
                published=extract_field(block, "Published"),
                author=extract_field(block, "Author"),
                highlights=normalize_excerpt(highlights),
                source_tier=classify_source_tier(url, extract_field(block, "Author"), title),
                query=query,
            ),
        )
    return items


def extract_mcporter_text(stdout: str) -> str:
    """从 mcporter JSON 响应中取出文本内容；异常时保留原文供诊断。"""

    raw = (stdout or "").strip()
    if not raw:
        return ""
    try:
        payload: Any = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    content = payload.get("content", []) if isinstance(payload, dict) else []
    chunks = [str(item.get("text", "")) for item in content if isinstance(item, dict) and item.get("type") == "text"]
    return "\n\n".join(chunk for chunk in chunks if chunk).strip() or raw


def classify_source_tier(url: str, author: str = "", title: str = "") -> str:
    """按域名给出来源等级，提示模型优先引用权威来源。"""

    host = (urlparse(url).hostname or "").lower()
    if any(host == suffix.lstrip(".") or host.endswith(suffix) for suffix in PRIMARY_DOMAIN_SUFFIXES):
        return "A"
    if any(host == suffix or host.endswith("." + suffix) for suffix in OFFICIAL_OEM_DOMAIN_SUFFIXES):
        return "A"
    publisher_hint = (author + " " + title).lower()
    if any(token in publisher_hint for token in ("乘联会", "中国汽车流通协会", "中国汽车工业协会", "中汽数据")):
        return "B"
    if any(host == suffix or host.endswith("." + suffix) for suffix in INDUSTRY_DOMAIN_SUFFIXES):
        return "B"
    return "C"


def is_http_url(value: str) -> bool:
    parsed = urlparse(str(value or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def extract_field(text: str, label: str) -> str:
    match = re.search(rf"(?mi)^{re.escape(label)}:\s*(.+)$", text or "")
    value = match.group(1).strip() if match else ""
    return "" if value in {"N/A", "None", "null"} else value


def extract_tail(text: str, label: str) -> str:
    match = re.search(rf"(?is){re.escape(label)}:\s*(.*)$", text or "")
    return match.group(1).strip() if match else ""


def normalize_excerpt(value: str, limit: int = 1200) -> str:
    compact = re.sub(r"\s+", " ", value or "").strip()
    return compact[:limit].rstrip("，。；; ") + ("。" if len(compact) > limit else "")


def _run(command: list[str], timeout_seconds: int) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(5, int(timeout_seconds)),
            cwd=PROJECT_DIR,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(command, returncode=124, stdout="", stderr="调用超时。")
    except OSError as exc:
        return subprocess.CompletedProcess(command, returncode=127, stdout="", stderr=f"启动命令失败：{exc}")


def _command_error(completed: subprocess.CompletedProcess[str]) -> str:
    detail = (completed.stderr or completed.stdout or "未知错误").strip()
    return detail[:800]
