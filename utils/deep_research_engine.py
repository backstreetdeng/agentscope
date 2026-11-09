"""深度调研确定性编排引擎（deep-research Skill / MKT-002）。

模型只承担两次受限调用：检索计划（输出 JSON）、报告正文撰写。
搜索、精读、来源登记、引用清理、报告组装全部由本引擎确定性执行；
工具回执是证据，模型文字不是完成证据。

搜索双源：主搜 AnySearch（HTTP 直连）→ 备搜 Tavily；精读 = fetch_url_text。
两个搜索源都不可用时明确失败，不编造来源。
"""
from __future__ import annotations

import json
import os
import re
from datetime import date
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from skills.anysearch.adapter import search as anysearch_search
from tools.custom_tools import fetch_url_text

TAVILY_SEARCH_URL = "https://api.tavily.com/search"
FETCH_TOP_PER_QUERY = 2
FETCH_MAX_CHARS = 3000
MAX_SOURCES = 12

_TIER_RULES: list[tuple[str, str]] = [
    ("gov.cn", "P0"),
    ("miit", "P0"),
    ("baike", "P3"),
    ("zhihu.com/question", "P3"),
    ("forum", "P3"),
    ("autohome.com.cn", "P2"),
    ("dongchedi.com", "P2"),
    ("yiche.com", "P2"),
    ("12365auto.com", "P2"),
]


def classify_tier(url: str) -> str:
    host = urlparse(url).netloc.lower()
    for needle, tier in _TIER_RULES:
        if needle in host or needle in url.lower():
            return tier
    return "P1"


def parse_plan(text: str) -> dict[str, Any]:
    """从模型输出提取计划 JSON；失败返回空 dict（调用方走确定性兜底）。"""
    text = (text or "").strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {}
    try:
        plan = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    if not isinstance(plan, dict):
        return {}
    queries = [str(item).strip() for item in plan.get("queries") or [] if str(item).strip()]
    plan["queries"] = queries[:6]
    plan["intent"] = "comparison" if plan.get("intent") == "comparison" else "report"
    plan["depth"] = plan.get("depth") if plan.get("depth") in {"L1", "L2", "L3"} else "L2"
    return plan if plan["queries"] else {}


def _parse_anysearch_output(stdout: str) -> list[dict[str, Any]]:
    """解析 AnySearch 格式化输出（N. 标题 / URL: ... / 摘要: ...）为结构化结果。"""
    results: list[dict[str, Any]] = []
    for block in re.split(r"\n\s*\n", stdout or ""):
        block = block.strip()
        if not block:
            continue
        url_match = re.search(r"^URL:\s*(\S+)\s*$", block, re.MULTILINE)
        if not url_match:
            continue
        url = url_match.group(1)
        first_line = block.splitlines()[0].strip()
        title = re.sub(r"^\d+[.、]\s*", "", first_line)
        if title.startswith("无标题"):
            title = url
        snippet_match = re.search(r"^摘要:\s*(.*)$", block, re.MULTILINE | re.DOTALL)
        snippet = snippet_match.group(1).strip() if snippet_match else ""
        results.append({
            "title": title[:120],
            "url": url,
            "snippet": re.sub(r"\s+", " ", snippet)[:600],
        })
    return results


def _search_any(query: str, max_results: int = 4) -> list[dict[str, Any]]:
    """主搜：AnySearch（HTTP 直连）。失败抛异常，由调用方降级 Tavily。"""
    rc, stdout, stderr, _marker = anysearch_search(query, max_results)
    if rc != 0:
        raise RuntimeError((stderr or "AnySearch 无结果")[:150])
    results = _parse_anysearch_output(stdout)
    if not results:
        raise RuntimeError("AnySearch 未返回内容")
    return results


def _tavily_search(query: str, max_results: int = 4) -> list[dict[str, Any]]:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY 未配置，无法联网取证。")
    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": "basic",
        "max_results": max(1, min(int(max_results), 10)),
        "include_answer": False,
    }
    request = Request(
        TAVILY_SEARCH_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=20) as response:
        obj = json.loads(response.read(1024 * 1024).decode("utf-8", errors="replace"))
    results = obj.get("results") or []
    return [
        {"title": str(item.get("title") or "")[:120], "url": str(item.get("url") or ""),
         "snippet": str(item.get("content") or "")[:600]}
        for item in results if item.get("url")
    ]


def execute_retrieval(queries: list[str], log: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """确定性取证：逐 query 双源搜索（主 any_search → 备 Tavily）、按 URL 去重、对头部结果精读。"""
    seen_urls: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for query in queries:
        results: list[dict[str, Any]] = []
        engine = "any_search"
        try:
            results = _search_any(query)
        except Exception as any_exc:
            try:
                results = _tavily_search(query)
                engine = "tavily_search"
            except Exception as tavily_exc:
                if log is not None:
                    log.append({
                        "stage": "search", "query": query, "status": "error",
                        "detail": f"any_search: {str(any_exc)[:80]}; tavily: {str(tavily_exc)[:80]}",
                    })
                continue
        if log is not None:
            log.append({"stage": "search", "engine": engine, "query": query, "status": "ok", "results": len(results)})
        for item in results:
            url = item["url"].rstrip("/")
            if url not in seen_urls:
                seen_urls[url] = item
                order.append(url)

    # 精读优先级：P0/P1 来源在前，保持发现顺序
    ranked = sorted(order, key=lambda u: 0 if classify_tier(u) in {"P0", "P1"} else 1)
    fetched: dict[str, str] = {}
    for url in ranked[: MAX_SOURCES // 2 * FETCH_TOP_PER_QUERY]:
        try:
            fetched[url] = fetch_url_text(url, FETCH_MAX_CHARS)
            if log is not None:
                log.append({"stage": "fetch", "url": url, "status": "ok", "chars": len(fetched[url])})
        except Exception as exc:
            if log is not None:
                log.append({"stage": "fetch", "url": url, "status": "error", "detail": str(exc)[:120]})

    sources: list[dict[str, Any]] = []
    for n, url in enumerate(ranked[:MAX_SOURCES], start=1):
        item = seen_urls[url]
        sources.append({
            "n": n,
            "title": item["title"] or url,
            "url": url,
            "tier": classify_tier(url),
            "as_of": date.today().isoformat(),
            "snippet": item["snippet"],
            "page_text": fetched.get(url, ""),
        })
    return sources


def build_evidence_block(sources: list[dict[str, Any]]) -> str:
    lines = []
    for item in sources:
        content = item.get("page_text") or item.get("snippet") or ""
        content = re.sub(r"\s+", " ", content).strip()
        lines.append(
            f"[cite:{item['n']}]（{item['tier']}）{item['title']} — {item['url']}\n{content[:900]}"
        )
    return "\n\n".join(lines)


def strip_invalid_cites(text: str, valid_numbers: set[int]) -> str:
    """删除指向不存在来源的 [cite:N]，防止虚构引用。"""

    def _sub(match: re.Match) -> str:
        return match.group(0) if int(match.group(1)) in valid_numbers else ""

    return re.sub(r"\[cite:(\d+)\]", _sub, text)


def append_source_section(text: str, sources: list[dict[str, Any]]) -> str:
    lines = [text.rstrip(), "", "## 参考来源", ""]
    for item in sources:
        lines.append(
            f"{item['n']}. {item['title']} — {item['url']}（{item['tier']}，时点 {item['as_of']}）"
        )
    return "\n".join(lines) + "\n"


def build_report_markdown(body: str, sources: list[dict[str, Any]]) -> str:
    """组装最终报告：清理虚构引用 + 追加确定性参考来源清单。"""
    valid = {item["n"] for item in sources}
    body = strip_invalid_cites(body or "", valid)
    if "## 参考来源" in body:
        body = body.split("## 参考来源")[0].rstrip()
    return append_source_section(body, sources)
