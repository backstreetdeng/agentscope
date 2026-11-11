"""满意度磁贴「本品进攻点」：提炼层与现状核验层。

数据层在 `analysis_service` 里完成（复用 `_loss_split` 竞品集合 + 口碑负向 L3），
本模块只做三件事：

1. 提炼：把「竞品负向 L3 + 条数 + 本品车型定位」交给模型，归一成 3 个 4–8 字的可进攻
   能力方向（如「路面滤震」→「后排滤震舒适性」），不做成长句投诉描述；
2. 校验：模型输出必须是恰好 3 条短词组，不得含数字、车型名、标点或照抄标签；不合格重写
   一次，仍不合格回退为不带数字的 L3 标签；
3. 核验：Tavily 检索每条短板的现状，模型只在给定证据里选结论（仍被反馈 / 已改善 /
   公认通病 / 证据不足），来源域名与抓取日期由代码回填；检索失败或无结果一律标
   「未做现状核验」，不编造。

缓存：
- 联网结果单独缓存 7 天，避免每次打开页面都发请求；
- 最终结论缓存键 = 提示词版本 + 数据哈希 + 联网结果哈希，联网结果变化必然换键重生成。
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse
from urllib.request import Request, urlopen

PROMPT_VERSION = "2026-11-11.5"
SEARCH_QUERY_VERSION = "2026-11-11.1"
PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"
CACHE_DIR = Path(__file__).resolve().parents[2] / "runtime" / "bci-analysis" / "attack-point"

SEARCH_TTL_DAYS = 7
SEARCH_MAX_RESULTS = 5
MIN_ITEM_CHARS = 4
MAX_ITEM_CHARS = 8
AUTHORITATIVE_DOMAINS = (
    "autohome.com.cn",
    "12365auto.com",
    "dongchedi.com",
    "yiche.com",
    "sina.cn",
    "sohu.com",
)

LLM = Callable[[str, str], str]
Search = Callable[[str, int], list[dict[str, Any]]]

VERDICT_TEXT = {
    "still_reported": "仍被车主反馈",
    "improved": "已见改款改善信息",
    "common_issue": "被多个来源称为通病",
    "inconclusive": "未见权威结论",
}
EVIDENCE_VERDICTS = {"still_reported", "improved", "common_issue", "inconclusive"}
SOURCED_VERDICTS = {"still_reported", "improved", "common_issue"}


# --------------------------------------------------------------------- 基础工具


def _prompt(filename: str) -> str:
    return (PROMPT_DIR / filename).read_text(encoding="utf-8").strip()


def _today() -> str:
    return datetime.now().date().isoformat()


def _safe(value: str) -> str:
    return re.sub(r"[^0-9a-zA-Z_-]+", "-", str(value or ""))[:80] or "model"


def _digest(*parts: Any) -> str:
    raw = json.dumps(parts, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:
        pass


def _domain(url: str) -> str:
    host = urlparse(str(url or "")).netloc.lower()
    return host[4:] if host.startswith("www.") else host


# --------------------------------------------------------------------- 联网检索


def tavily_search(query: str, max_results: int = SEARCH_MAX_RESULTS) -> list[dict[str, Any]]:
    """调用 Tavily 检索；失败直接抛错，由调用方标记「未做现状核验」。"""
    from competitor_insight.server import db

    key = db.load_env().get("TAVILY_API_KEY", "")
    if not key:
        raise RuntimeError("未配置 TAVILY_API_KEY")
    request = Request(
        "https://api.tavily.com/search",
        data=json.dumps(
            {
                "api_key": key,
                "query": query,
                "search_depth": "basic",
                "max_results": max_results,
                "include_answer": False,
            },
            ensure_ascii=False,
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=15) as response:
        payload = json.loads(response.read(1024 * 1024).decode("utf-8", errors="replace"))
    results = []
    for item in payload.get("results") or []:
        url = str(item.get("url") or "")
        domain = _domain(url)
        if not domain:
            continue
        results.append(
            {
                "title": str(item.get("title") or "")[:120],
                "url": url,
                "domain": domain,
                "snippet": re.sub(r"\s+", " ", str(item.get("content") or "")).strip()[:280],
            }
        )
    return results


def _search_cache_path(model_key: str, directions: list[dict[str, Any]], cache_dir: Path | None) -> Path:
    key = _digest(
        [[SEARCH_QUERY_VERSION, item["direction"], item["competitor"]] for item in directions]
    )
    return Path(cache_dir or CACHE_DIR) / "search" / f"{_safe(model_key)}-{key}.json"


def _fresh(fetched_at: str) -> bool:
    try:
        return (date.today() - date.fromisoformat(str(fetched_at))).days < SEARCH_TTL_DAYS
    except ValueError:
        return False


def search_one(
    direction: dict[str, Any],
    search: Search,
    model_key: str,
    cache_dir: Path | None = None,
) -> tuple[list[dict[str, Any]], bool, bool]:
    """返回（结果，是否命中检索缓存，是否真实发起联网请求）。"""
    path = _search_cache_path(model_key, [direction], cache_dir)
    cached = _read_json(path)
    if cached and cached.get("results") and _fresh(str(cached.get("fetched_at") or "")):
        return list(cached["results"]), True, False

    query = (
        f"{direction['competitor']} {direction['direction']} "
        "投诉 通病 缺点 车主"
    )
    results = search(query, SEARCH_MAX_RESULTS) or []
    results.sort(key=lambda row: 0 if any(
        str(row.get("domain") or "").endswith(domain) for domain in AUTHORITATIVE_DOMAINS
    ) else 1)
    _write_json(
        path,
        {"query": query, "fetched_at": _today(), "results": results},
    )
    return results, False, True


# --------------------------------------------------------------------- 提炼层


def _numbers_in(text: str) -> list[str]:
    from competitor_insight.server.agent_analysis import AgentAnalysisService

    return AgentAnalysisService._numbers_in(text, [])


def _foreign_names(text: str) -> list[str]:
    from competitor_insight.server.agent_analysis import foreign_model_names

    return foreign_model_names(text, [])


def _normalize_directions(raw: str) -> list[str]:
    """把模型输出压成 3 条方向；只按顿号切，条内逗号保留。"""
    value = str(raw or "").strip().splitlines()
    line = value[0].strip() if value else ""
    line = re.sub(r"^(?:进攻点|输出|方向)\s*[:：]\s*", "", line)
    line = line.replace("；", "、").replace(";", "、")
    parts = [re.sub(r"\s+", "", part).strip("，。、“”\"'") for part in line.split("、")]
    return [part for part in parts if part]


def _attack_problem(items: list[str], directions: list[dict[str, Any]]) -> str:
    if len(items) != 3:
        return f"输出 {len(items)} 条，要求恰好 3 条"
    problems: list[str] = []
    for index, item in enumerate(items):
        if not MIN_ITEM_CHARS <= len(item) <= MAX_ITEM_CHARS:
            problems.append(
                f"第 {index + 1} 条 {len(item)} 字，要求 {MIN_ITEM_CHARS}–{MAX_ITEM_CHARS} 字"
            )
        if re.search(r"[，。；：,.;:！？!?]", item):
            problems.append(f"第 {index + 1} 条写了句子或标点，要求短词组")
        numbers = _numbers_in(item)
        if numbers:
            problems.append(f"第 {index + 1} 条出现数字 {'/'.join(numbers)}")
        names = _foreign_names(item)
        if names:
            problems.append(f"第 {index + 1} 条出现车型名 {'/'.join(names)}")
        if item == directions[index]["direction"]:
            problems.append(f"第 {index + 1} 条直接复述了标签「{item}」")
    if len(set(items)) != 3:
        problems.append("三条方向存在重复")
    return "；".join(problems)


def extract_attack(
    model_label: str,
    model_position: str,
    directions: list[dict[str, Any]],
    llm: LLM | None,
) -> dict[str, Any]:
    """模型提炼；失败返回 error，不合规重写一次后回退为无数字的 L3 标签。"""
    if llm is None:
        return {"texts": [item["direction"] for item in directions], "source": "error",
                "error": "未注入模型通道，未生成进攻点。"}

    system_prompt = _prompt("attack_point.txt")
    facts = "\n".join(
        f"{index + 1}. {item['direction']}（竞品：{item['competitor']}，{item['count']} 条）"
        for index, item in enumerate(directions)
    )
    message = (
        f"【本品】{model_label}（{model_position}）\n"
        f"【竞品车主不满意点（按去重条数降序）】\n{facts}\n"
        "【写作要求】只输出 3 个 4–8 字的能力方向，用「、」连接；每条是短词组、不是句子，"
        "不得照抄标签原词，不出现数字与车型名。"
    )
    started = time.perf_counter()
    try:
        texts = _normalize_directions(llm(system_prompt, message))
        problem = _attack_problem(texts, directions)
        if problem:
            retry = message + f"\n【上一次输出不合格】{problem}，请严格按写作要求重写。"
            texts = _normalize_directions(llm(system_prompt, retry))
            problem = _attack_problem(texts, directions)
    except Exception as exc:  # noqa: BLE001 - 模型失败如实上报，不用标签冒充
        return {
            "texts": [item["direction"] for item in directions],
            "source": "error",
            "error": f"模型调用失败：{exc.__class__.__name__}：{exc}",
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
        }
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    if problem:
        return {
            "texts": [item["direction"] for item in directions],
            "source": "fallback_labels",
            "problem": problem,
            "elapsed_ms": elapsed_ms,
        }
    return {"texts": texts, "source": "llm", "elapsed_ms": elapsed_ms}


# --------------------------------------------------------------------- 核验层


def _parse_verdicts(raw: str) -> dict[int, dict[str, Any]]:
    match = re.search(r"\[[\s\S]*\]", str(raw or ""))
    if not match:
        return {}
    try:
        rows = json.loads(match.group(0))
    except ValueError:
        return {}
    verdicts: dict[int, dict[str, Any]] = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        try:
            index = int(row.get("index"))
        except (TypeError, ValueError):
            continue
        verdict = str(row.get("verdict") or "")
        if verdict not in EVIDENCE_VERDICTS:
            continue
        evidence = row.get("evidence")
        try:
            evidence = int(evidence) if evidence is not None else None
        except (TypeError, ValueError):
            evidence = None
        verdicts[index] = {
            "verdict": verdict,
            "evidence": evidence,
            "quote": str(row.get("quote") or "").strip()[:60],
        }
    return verdicts


def _quote_supports(verdict: str, quote: str) -> bool:
    """原句必须真的能支撑对应的现状判断，避免模型凭印象下结论。"""
    if verdict == "inconclusive":
        return True
    keywords = {
        "improved": ("改款", "新款", "换代", "OTA", "升级", "优化", "改善", "解决", "修复"),
        "common_issue": ("通病", "普遍", "很多车主", "不少车主", "集中反映", "大量"),
        "still_reported": (
            "投诉", "抱怨", "反馈", "反映", "缺点", "不足", "偏硬", "偏重",
            "偏大", "打折", "问题", "不满意",
        ),
    }
    return any(word in quote for word in keywords.get(verdict, ()))


def verify_directions(
    directions: list[dict[str, Any]],
    results: list[list[dict[str, Any]]],
    llm: LLM | None,
) -> dict[str, Any]:
    """只做现状核验：模型选 verdict，来源与日期由代码回填。"""
    fetched_at = _today()
    verdicts: dict[int, tuple[str, int | None]] = {}
    has_evidence = any(results)
    if has_evidence and llm is not None:
        system_prompt = _prompt("attack_point_verify.txt")
        blocks = []
        for index, (item, rows) in enumerate(zip(directions, results), start=1):
            lines = [f"【{index}】{item['direction']}（竞品：{item['competitor']}）"]
            for row_index, row in enumerate(rows[:SEARCH_MAX_RESULTS], start=1):
                lines.append(
                    f"[{row_index}] {row.get('domain', '')} | {row.get('title', '')} "
                    f"| 摘要：{row.get('snippet', '')}"
                )
            blocks.append("\n".join(lines))
        try:
            verdicts = _parse_verdicts(llm(system_prompt, "\n\n".join(blocks)))
        except Exception:  # noqa: BLE001 - 核验失败不影响数据层结论
            verdicts = {}

    items = []
    for index, (item, rows) in enumerate(zip(directions, results), start=1):
        judged = verdicts.get(index, {})
        verdict = str(judged.get("verdict") or "")
        evidence = judged.get("evidence")
        quote = str(judged.get("quote") or "")
        source = rows[evidence - 1] if evidence and 0 < evidence <= len(rows) else {}
        supported = bool(
            source and quote and quote in str(source.get("snippet") or "")
            and _quote_supports(verdict, quote)
        )
        if supported and verdict in SOURCED_VERDICTS:
            items.append({
                "direction": item["direction"],
                "verdict": verdict,
                "text": VERDICT_TEXT[verdict],
                "domain": source.get("domain", ""),
                "url": source.get("url", ""),
                "quote": quote,
                "fetched_at": fetched_at,
            })
        elif verdict == "inconclusive" and source:
            items.append({
                "direction": item["direction"],
                "verdict": verdict,
                "text": VERDICT_TEXT[verdict],
                "domain": source.get("domain", ""),
                "url": source.get("url", ""),
                "quote": quote,
                "fetched_at": fetched_at,
            })
        else:
            items.append({
                "direction": item["direction"],
                "verdict": "",
                "text": "未做现状核验",
                "domain": "",
                "url": "",
                "quote": "",
                "fetched_at": fetched_at,
            })

    sourced = [item for item in items if item["domain"]]
    if not sourced:
        status = "unverified"
    elif len(sourced) == len(items):
        status = "verified"
    else:
        status = "partial"

    parts = []
    for item in items:
        if item["domain"]:
            parts.append(f"{item['direction']}{item['text']}（{item['domain']}）")
        else:
            parts.append(f"{item['direction']}未做现状核验")
    line = "竞品口碑现状：" + "；".join(parts) + f" · 抓取 {fetched_at}"
    return {"status": status, "fetched_at": fetched_at, "items": items, "line": line}


# --------------------------------------------------------------------- 入口


def _final_cache_path(model_key: str, digest: str, cache_dir: Path | None) -> Path:
    return Path(cache_dir or CACHE_DIR) / f"{_safe(model_key)}-{digest}.json"


def build_attack(
    model_key: str,
    model_label: str,
    model_position: str,
    directions: list[dict[str, Any]],
    *,
    llm: LLM | None = None,
    search: Search | None = None,
    cache_dir: Path | None = None,
) -> dict[str, Any]:
    """三层入口：数据层结果由调用方给出，这里做提炼、校验、核验与缓存。"""
    started = time.perf_counter()
    if not directions:
        return {
            "model": {"key": model_key, "label": model_label},
            "directions": [],
            "attack": "",
            "basis": "",
            "source": "empty",
            "error": "没有可用的竞品负向口碑点，未生成进攻点。",
            "verification": {"status": "unverified", "items": [], "line": "竞品口碑现状：未做现状核验"},
            "prompt_version": PROMPT_VERSION,
        }

    data_hash = _digest(
        model_label,
        [
            [item["direction"], item["competitor"], item["count"], item["denominator"]]
            for item in directions
        ],
    )

    search_fn = search or tavily_search
    results: list[list[dict[str, Any]]] = []
    search_error = False
    for item in directions:
        try:
            rows, _cached, _fetched = search_one(item, search_fn, model_key, cache_dir)
        except Exception:  # noqa: BLE001 - 检索失败标「未做现状核验」，不阻断页面
            rows, search_error = [], True
        results.append(rows)
    search_hash = _digest(
        [
            [item["direction"], [[row.get("url"), row.get("title")] for row in rows]]
            for item, rows in zip(directions, results)
        ]
    )
    digest = _digest(PROMPT_VERSION, data_hash, search_hash)
    path = _final_cache_path(model_key, digest, cache_dir)
    cached = _read_json(path)
    if (
        cached
        and cached.get("prompt_version") == PROMPT_VERSION
        and cached.get("data_hash") == data_hash
        and cached.get("search_hash") == search_hash
        and cached.get("attack")
    ):
        cached["source"] = "cache"
        cached["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
        return cached

    extracted = extract_attack(model_label, model_position, directions, llm)
    texts = extracted["texts"]
    verification = verify_directions(directions, results, llm)
    rows = [
        {
            **item,
            "text": texts[index],
            "ratio": round(item["count"] * 100 / item["denominator"], 1)
            if item.get("denominator")
            else None,
        }
        for index, item in enumerate(directions)
    ]
    basis = "依据：" + "、".join(
        f"{item['competitor']} {item['direction']} {item['count']}/{item['denominator']} 条"
        + (f"（{item['ratio']}%）" if item["ratio"] is not None else "")
        for item in rows
    )
    payload = {
        "model": {"key": model_key, "label": model_label},
        "directions": rows,
        "attack": "、".join(item["text"] for item in rows),
        "basis": basis,
        "source": extracted["source"],
        "error": extracted.get("error", ""),
        "problem": extracted.get("problem", ""),
        "verification": verification,
        "prompt_version": PROMPT_VERSION,
        "data_hash": data_hash,
        "search_hash": search_hash,
        "search_error": search_error,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    if payload["source"] != "error" and not search_error:
        _write_json(path, payload)
    return payload
