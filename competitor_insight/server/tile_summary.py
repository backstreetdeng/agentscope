"""即时分析三个磁贴的「块内 AI 结论」：定性画像、关注分层、战胜战败归因。

用途
----
页面在「用户画像 / 购车关注 / 战胜战败原因洞察」三个磁贴底部展示一行 AI 结论。
满意度磁贴按用户要求不再生成 AI 结论。本模块负责：

1. 从磁贴已经算好的结果里抽取事实行（人数、勾选维度、深访原话），不重新查库；
2. 按磁贴各自的 System Prompt + few-shot 调用调用方注入的 LLM 通道
   （`app.py` 复用项目现有 agentscope 模型，本模块不引第三方 SDK）；
3. 结果按「车型 key + 磁贴 key + 提示词哈希 + 本块数据哈希」缓存到
   `runtime/bci-analysis/tile-summary/`，改提示词后不会命中旧缓存；
4. 模型失败时如实返回错误，不再用模板句顶替结论。

口径约束
--------
- 只允许使用本磁贴的数字与原话，不跨磁贴取数，不引入库外事实。
- 战败原因的文本线索只来自深访 Q27/Q28（放弃原因），战胜侧文本线索只来自 Q29
  （选择原因）。定量 Q3_24_* 只有 16 维勾选、没有开放原话，因此原话必须标注
  「来源：深访」并带人数，不能当作定量比例。
- 输出 40–70 个汉字、一句话为主；画像不复述百分比，关注不分层报菜名，
  战胜战败不做计数播报。
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

PROMPT_VERSION = "2026-11-10.8"
MAX_CHARS = 70
QUOTE_CHARS = 80

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = PROJECT_ROOT / "runtime" / "bci-analysis" / "tile-summary"

TILE_TITLES = {
    "profile": "用户画像",
    "attention": "购车关注",
    "winloss": "战胜战败原因洞察",
}

PROFILE_PROMPT = """你是汽车用户洞察分析助手。只依据「本块数字」写 1–2 句用户定性画像，50–65 个汉字（含标点不超过 70）。

必须做到：
1. 禁止出现百分比、占比、人数，禁止「X 最突出、Y 次之」「以 X 为主」这类统计播报；
2. 必须给出 1–2 个性格或生活状态标签，例如：技术理性派、事业上升期、理性消费、家庭决策者、尝鲜型用户、务实代步派；
3. 结合该车型的受众心智（家用 / 硬派 / 性能 / 代步 / 智能科技等）说明这群人是谁、为什么买这类车；
4. 只依据本块数字与车型名推断，不编造收入、职业、家庭结构等数字里没有的细节；
5. 只输出这一两句中文，不加标题、不写「AI 结论」、不用项目符号，结尾用句号。

【few-shot：只学句式与标签写法，不得复用示例中的数字、车型和维度】
示例一
数据：30 人，男性 70%，36–40 岁 27%，换购为主。
结论：以技术理性派为主，处在事业上升期，换购时更看三电与配置的确定性，属于理性消费型用户。
示例二
数据：24 人，25–30 岁 50%，首购为主，二线城市居多。
结论：以尝鲜型年轻首购为主，预算敏感但愿意为智能座舱买单，属于悦己型城市代步用户。"""

ATTENTION_PROMPT = """你是汽车用户洞察分析助手。只依据「本块购车关注勾选率」写一句话，50–65 个汉字（含标点不超过 70），做战略分层。

必须做到：
1. 禁止按勾选率从高到低报菜名，禁止罗列百分比和人数；
2. 固定使用这套分层词汇：
   - 勾选率最高 → 称为「入场券」或「第一触点」；
   - 中等但用户普遍认为不可或缺 → 称为「必备项」「竞争重点」或「竞争决胜点」；
   - 勾选率明显偏低 → 称为「加分项」或「底线筛查」；
3. 先点第一触点，再点必备项，最后落到真正的竞争决胜点或底线项，体现取舍；
4. 加分项或底线筛查最多点名 2 个维度，不得把其余维度逐一罗列；
5. 只依据本块勾选率分层，不补库外结论，不改写维度名；
6. 只输出这一句中文，不加标题、不写「AI 结论」、不用项目符号，结尾用句号。

【few-shot：只学分层句式，不得复用示例中的数字和维度组合】
示例一
数据：外观 62%、智驾 55%、续航 48%、底盘操控 41%、安全 30%。
结论：外观是入场券，智驾是必备项，续航与底盘操控才是竞争决胜点。
示例二
数据：外观 90%、智驾 80%、安全 30%。
结论：外观是绝对的第一触发点（入场券），智驾是标配，安全仅作为底线筛查。"""

WINLOSS_PROMPT = """你是汽车用户洞察分析助手。只依据「本块战胜战败数字」与「深访原话」写一句归因判断，50–65 个汉字（含标点不超过 70）。

必须做到：
1. 禁止计数播报，不写「胜出 X 人」「占比 X%」这类句子；
2. 战胜侧给出核心归因（品牌信任 / 智驾领先 / 价格优势 / 空间 / 外观 等），说清「为什么赢」；
3. 战败侧指出流失痛点，只能来自本块勾选的 16 维原因或深访原话，例如交付周期、价格超预算、配置不满；
4. 深访原话只作线索，已经标注「来源：深访」并带人数，不能把它当定量比例，也不得把个别人的话写成群体结论；
5. 若本块没有深访原话，就只能按 16 维勾选归因，严禁编造「未上市」「等不及」这类具体原因；
6. 最后半句固定写成「下一步重点防御 <对象>」，不得省略、不得换成其他总结；
7. 只输出这一句中文，不加标题、不写「AI 结论」、不用项目符号，结尾用句号。

【few-shot：只学归因方式与收尾句式，不得复制其中的具体原因；没有对应原话时不许照搬】
示例一（原型句式）
数据：战胜侧智驾认知领先；深访 3 人提到「未上市、等不及」，属于时间性流失。
结论：本品在智驾认知上已占优，但「未上市、等不及」造成时间性流失；上市节奏本身就是竞争力。
示例二（动作建议收尾）
数据：战胜侧智驾最高；战败 17 人中零跑B10 胜出 4 人，勾选原因以价格为主。
结论：智驾认知是胜出核心，战败主要流失于价格；下一步重点防御零跑B10的价格攻势。"""

SYSTEM_PROMPTS = {
    "profile": PROFILE_PROMPT,
    "attention": ATTENTION_PROMPT,
    "winloss": WINLOSS_PROMPT,
}

LLM = Callable[[str, str], str]


def _ratio_text(item: dict[str, Any]) -> str:
    """统一人数/比例写法：比例被隐藏时只给人数。"""
    count = int(item.get("count") or 0)
    if item.get("ratio") is None:
        return f"{count} 人"
    return f"{count} 人/{item.get('ratio')}%"


def _clip(text: str, limit: int = MAX_CHARS) -> str:
    """压成一行并截到上限；优先断在标点，避免半句。"""
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(value) <= limit:
        return value
    cut = value[:limit]
    for mark in ("；", "，", "、", "。"):
        position = cut.rfind(mark)
        if position >= int(limit * 0.6):
            cut = cut[:position]
            break
    return cut.rstrip("；，、。") + "。"


def _labels(tile: dict[str, Any]) -> set[str]:
    """收集本块出现过的车型/维度名称，用于把模型输出里的空格改回库里写法。"""
    found: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "label" and isinstance(value, str):
                    found.add(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(tile)
    return {name for name in found if re.search(r"\s", name)}


def _repair_spacing(text: str, names: set[str]) -> str:
    """只修空格：把「奇瑞iCARV23」还原成库里的「奇瑞iCAR V23」，不改字。"""
    for name in sorted(names, key=len, reverse=True):
        pattern = r"\s*".join(re.escape(part) for part in name.split())
        text = re.sub(pattern, name, text)
    return text


def _normalize(text: str, names: set[str] | None = None, clip: bool = True) -> str:
    """模型输出清洗：只留第一句，去掉「AI 结论：」前缀与列表符号。

    `clip=False` 用于校验前保留全文，避免 70 字截断把必填的收尾句切掉。
    """
    line = str(text or "").strip().splitlines()
    value = line[0].strip() if line else ""
    value = re.sub(r"^(?:AI\s*结论|结论)\s*[:：]\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"^(?:[-*•]\s*|\d+[.、]\s*)", "", value).strip().strip('"“”')
    if not value:
        return ""
    if names:
        value = _repair_spacing(value, names)
    if not value.endswith(("。", "！", "？")):
        value += "。"
    return _clip(value) if clip else value


# --------------------------------------------------------------------- 事实抽取


def _profile_lines(tile: dict[str, Any]) -> list[str]:
    """只给人数分布，不给比例，避免模型直接抄百分比。"""
    lines = [f"定量样本 {tile.get('n') or 0} 人"]
    used = 0
    for metric in tile.get("metrics") or []:
        if metric.get("kind") not in {"distribution", "numeric"}:
            continue
        items = sorted(
            [item for item in metric.get("items") or [] if item.get("count")],
            key=lambda item: (-int(item["count"]), str(item["label"])),
        )[:3]
        if not items:
            continue
        lines.append(
            f"{metric['label']}：" + "、".join(f"{item['label']} {item['count']} 人" for item in items)
        )
        used += 1
        if used >= 6:
            break
    return lines


def _attention_lines(tile: dict[str, Any]) -> list[str]:
    """给出全部非零勾选项及勾选率，由模型自己分层，不在事实行里预判高低。"""
    metric = (tile.get("metrics") or [{}])[0]
    lines = [f"实际作答 {metric.get('answered')}/{metric.get('n')} 人"]
    items = sorted(
        [item for item in metric.get("items") or [] if item.get("count")],
        key=lambda item: (-int(item["count"]), str(item["label"])),
    )
    if items:
        lines.append(
            "各维度勾选：" + "、".join(f"{item['label']} {_ratio_text(item)}" for item in items)
        )
    return lines


def _pick_quotes(
    metric: dict[str, Any], names: list[str], limit: int = 3
) -> list[str]:
    """深访原话取与当前车型/流失车型最相关的几条，压到 80 字以内。"""
    items = [item for item in metric.get("items") or [] if str(item.get("quote") or "").strip()]

    def score(item: dict[str, Any]) -> tuple[int, int]:
        text = str(item.get("quote") or "")
        related = any(name and name in text for name in names)
        return (0 if related else 1, len(text))

    picked = sorted(items, key=score)[:limit]
    return [_clip(str(item.get("quote") or ""), QUOTE_CHARS) for item in picked]


def _winloss_lines(tile: dict[str, Any]) -> list[str]:
    metrics = {metric.get("key"): metric for metric in tile.get("metrics") or []}
    win = metrics.get("q3_23") or {}
    loss = metrics.get("loss_split") or {}
    win_quotes = metrics.get("win_quotes") or {}
    abandon_quotes = metrics.get("abandon_quotes") or {}
    target = str(loss.get("target") or "")
    lines: list[str] = []

    if win.get("top"):
        lines.append(
            f"战胜侧·选择本车原因（Q3_23，作答 {win.get('answered')}/{win.get('n')} 人）："
            + "、".join(f"{item['label']} {_ratio_text(item)}" for item in win["top"][:5])
        )

    loss_items = loss.get("items") or []
    if loss_items:
        rows = []
        for item in loss_items[:4]:
            reasons = "、".join(
                f"{reason['label']} {reason['count']} 人" for reason in (item.get("reasons") or [])[:3]
            )
            rows.append(f"{item['label']} {item['count']} 人" + (f"（勾选原因：{reasons}）" if reasons else "（无勾选原因）"))
        lines.append(
            f"战败侧·对比过{target}后买了别的车 {loss.get('n')} 人：" + "；".join(rows)
        )

    names = [target] + [str(item.get("label") or "") for item in loss_items]
    win_picked = _pick_quotes(win_quotes, [target])
    if win_picked:
        lines.append(
            f"深访原话（Q29 选择本车原因，{win_quotes.get('people')} 人，来源：深访，不是定量比例）："
            + "；".join(f"「{text}」" for text in win_picked)
        )
    else:
        lines.append("深访原话（Q29 选择本车原因）：无有效作答，不得编造具体原因。")

    abandon_picked = _pick_quotes(abandon_quotes, names)
    if abandon_picked:
        lines.append(
            f"深访原话（Q27/Q28 放弃对比车型原因，{abandon_quotes.get('people')} 人，来源：深访，不是定量比例）："
            + "；".join(f"「{text}」" for text in abandon_picked)
        )
    else:
        lines.append("深访原话（Q27/Q28 放弃对比车型原因）：无有效作答，只能按 16 维勾选归因。")
    return lines


BUILDERS = {
    "profile": _profile_lines,
    "attention": _attention_lines,
    "winloss": _winloss_lines,
}


def build_facts(tile_key: str, tile: dict[str, Any], model_label: str) -> dict[str, Any]:
    builder = BUILDERS.get(tile_key)
    lines = builder(tile) if builder else []
    lines = [line for line in lines if line]
    return {
        "tile": tile_key,
        "title": TILE_TITLES.get(tile_key, tile_key),
        "model": model_label,
        "lines": lines,
    }


def facts_digest(facts: dict[str, Any], system_prompt: str = "") -> str:
    """缓存键：提示词版本 + 提示词全文哈希 + 本块事实，改提示词必然换键。"""
    raw = json.dumps([facts["model"], facts["lines"]], ensure_ascii=False, sort_keys=True)
    prompt_hash = hashlib.sha1(system_prompt.encode("utf-8")).hexdigest()[:8]
    return hashlib.sha1((PROMPT_VERSION + prompt_hash + raw).encode("utf-8")).hexdigest()[:16]


OUTPUT_HINTS = {
    "profile": "定性画像，不出现人数、百分比和「最突出/次之」。",
    "attention": "按入场券 / 必备项 / 加分项分层，不按勾选率报菜名。",
    "winloss": "先归因，最后半句写「下一步重点防御…」。",
}

ATTENTION_MARKERS = ("入场券", "第一触点", "必备项", "竞争重点", "竞争决胜点", "加分项", "底线筛查")


def format_problem(tile_key: str, summary: str) -> str:
    """按用户 2026-11-10 的硬要求校验成句，不满足则触发一次重写。"""
    text = str(summary or "")
    if not text:
        return ""
    if len(text) > MAX_CHARS:
        return f"输出 {len(text)} 字，超过 70 字上限"
    if tile_key == "profile":
        if re.search(r"\d+(?:\.\d+)?%|最突出|次之|占比|\d+\s*人", text):
            return "画像仍出现人数、百分比或「最突出/次之」"
    elif tile_key == "attention":
        if not any(marker in text for marker in ATTENTION_MARKERS):
            return "没有使用入场券 / 必备项 / 加分项分层"
        if text.count("、") > 4:
            return "把低分维度逐一罗列成了报菜名"
    elif tile_key == "winloss":
        if "下一步重点防御" not in text:
            return "结尾缺少「下一步重点防御…」"
        if re.search(r"\d+(?:\.\d+)?%|胜出\s*\d+\s*人", text):
            return "仍在做计数播报"
    return ""


def user_message(facts: dict[str, Any]) -> str:
    body = "\n".join("- " + line for line in facts["lines"]) or "- 本块暂无可读数字"
    hint = OUTPUT_HINTS.get(facts["tile"], "")
    return (
        f"【块】{facts['title']}（车型：{facts['model']}）\n"
        f"【本块数字】\n{body}\n"
        f"【写作要求】只输出一句 40–70 字的中文结论，不加标题与项目符号。{hint}"
    )


# --------------------------------------------------------------------- 缓存


def cache_path(model_key: str, tile_key: str, digest_value: str, cache_dir: Path | None = None) -> Path:
    safe = re.sub(r"[^0-9a-zA-Z_-]+", "-", f"{model_key}-{tile_key}")[:80]
    return Path(cache_dir or CACHE_DIR) / f"{safe}-{digest_value}.json"


def read_cache(path: Path) -> str:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if payload.get("prompt_version") != PROMPT_VERSION:
        return ""
    return str(payload.get("summary") or "").strip()


def write_cache(path: Path, summary: str, source: str) -> None:
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(
            json.dumps(
                {
                    "summary": summary,
                    "source": source,
                    "prompt_version": PROMPT_VERSION,
                    "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except OSError:
        pass


# --------------------------------------------------------------------- 入口


def summarize_tile(
    tile_key: str,
    tile: dict[str, Any],
    model_label: str,
    model_key: str = "",
    llm: LLM | None = None,
    cache_dir: Path | None = None,
) -> dict[str, Any]:
    """生成单个磁贴的 AI 结论，返回 summary / source / error / digest / prompt。

    source 取值：llm（模型生成）、cache（命中同版本缓存）、
    empty（本块无可读数字）、error（模型缺失/调用失败/返回为空）。
    失败时 summary 为空并给出 error，不再用模板句充当结论。
    """
    facts = build_facts(tile_key, tile, model_label)
    system_prompt = SYSTEM_PROMPTS.get(tile_key, "")
    prompt = (system_prompt + "\n\n" + user_message(facts)) if facts["lines"] else ""
    if not facts["lines"]:
        return {
            "summary": "",
            "source": "empty",
            "error": f"{model_label}{facts['title']}暂无可读数字，未生成结论。",
            "digest": "",
            "prompt": "",
        }
    if not system_prompt:
        return {
            "summary": "",
            "source": "error",
            "error": f"未配置“{tile_key}”的提示词，本块不生成 AI 结论。",
            "digest": "",
            "prompt": prompt,
        }

    digest_value = facts_digest(facts, system_prompt)
    path = cache_path(model_key or model_label, tile_key, digest_value, cache_dir)
    cached = read_cache(path)
    if cached:
        return {"summary": cached, "source": "cache", "digest": digest_value, "prompt": prompt}

    if llm is None:
        return {
            "summary": "",
            "source": "error",
            "error": "未注入模型通道，本块不生成 AI 结论。",
            "digest": digest_value,
            "prompt": prompt,
        }

    started = time.perf_counter()
    names = _labels(tile) | ({model_label} if re.search(r"\s", model_label) else set())
    message = user_message(facts)
    try:
        summary = _normalize(llm(system_prompt, message), names, clip=False)
        problem = format_problem(tile_key, summary)
        if problem:  # 格式不合格时只重写一次，不无限调用
            retry_message = message + f"\n【上一次输出不合格】{problem}，请严格按写作要求重写一句。"
            summary = _normalize(llm(system_prompt, retry_message), names, clip=False)
            problem = format_problem(tile_key, summary)
    except Exception as exc:  # noqa: BLE001 - 失败必须如实上报，不再降级成模板句
        return {
            "summary": "",
            "source": "error",
            "error": f"模型调用失败：{exc.__class__.__name__}：{exc}",
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "digest": digest_value,
            "prompt": prompt,
        }
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    if not summary:
        return {
            "summary": "",
            "source": "error",
            "error": "模型返回为空或无法解析，未生成结论。",
            "elapsed_ms": elapsed_ms,
            "digest": digest_value,
            "prompt": prompt,
        }
    if problem:
        return {
            "summary": "",
            "source": "error",
            "error": f"模型输出不符合格式要求：{problem}（已重写一次）",
            "elapsed_ms": elapsed_ms,
            "digest": digest_value,
            "prompt": prompt,
        }
    write_cache(path, summary, "llm")
    return {
        "summary": summary,
        "source": "llm",
        "elapsed_ms": elapsed_ms,
        "digest": digest_value,
        "prompt": prompt,
    }
