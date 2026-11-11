"""BCI-006 · 智能化分析：固定骨架工作流。

链路：Router（模型，受 JSON 约束）→ Preflight（靶心只来自前端）→ Toolbox（代码取数）
→ Derive（代码算差值/排序）→ Composer（模型，受证据表约束）→ Validator（数字/引用/口径）。

模型只出现在路由与合成两处；取数、算术、阈值判断全部在代码里。
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from competitor_insight.server.agent_tools import Toolbox
from competitor_insight.server.analysis_service import (
    AnalysisError,
    AnalysisService,
    normalize_competitor,
    _name_key,
)

PROMPT_VERSION = "2026-11-11.1"
PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"
ROUTER_PROMPT = (PROMPT_DIR / "agent_router.txt").read_text(encoding="utf-8")
COMPOSE_PROMPTS = {
    "W1": (PROMPT_DIR / "agent_compose_w1.txt").read_text(encoding="utf-8"),
    "W2": (PROMPT_DIR / "agent_compose_w2.txt").read_text(encoding="utf-8"),
}

LLM = Callable[[str, str], str]
TEMPLATES = {"W1", "W2", "W3", "W4", "unknown"}
METRICS = {"attention", "winloss", "satisfaction", "profile", None}

NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
STRIP_NUMBER_PATTERNS = [
    re.compile(r"Q\d+_\d+(?:__\d+)?"),
    re.compile(r"\bT\d+:[^\s，。；、)）]*"),
    re.compile(r"\b[EWL]\d+\b"),
    re.compile(r"\[E\d+\]"),
    # 年龄段与价格段是标签不是结论数字，26-30岁、10-15万 不参与数字校验。
    re.compile(r"\d+\s*[-~至]\s*\d+\s*岁"),
    re.compile(r"\d+\s*[-~至]\s*\d+\s*万"),
]
BANNED_WORDS = ("全部", "唯一", "仅有", "均为", "都是", "所有")
SHARE_PHRASES = ("领先竞品", "优于竞品", "领先于竞品", "口碑领先", "领先市场")
UNSUPPORTED_TEMPLATES = {
    "W3": "当前版本先支持综合诊断与双车对标。你可以问“综合看下本品应该如何对标竞品”，或“本品和竞品在画像、关注上有什么差异”。",
    "W4": "当前版本先支持综合诊断与双车对标；口碑已作为第四路数据进入综合诊断。你可以问“综合看下本品的关注、战胜战败和满意度”。",
}
CLARIFY_TEXT = (
    "识别不出你想看哪一类，请换一种问法：① 综合诊断（关注 + 战胜战败 + 满意度 + 画像）；"
    "② 双车对标（当前车型 vs 竞品池）。"
)


def _ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


class AgentAnalysisError(RuntimeError):
    def __init__(self, code: str, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.status = status

    def to_payload(self) -> dict[str, Any]:
        return {"ok": False, "error": {"code": self.code, "message": str(self)}}


# --------------------------------------------------------------------- 路由


def _parse_json(text: str) -> dict[str, Any] | None:
    value = str(text or "").strip()
    if value.startswith("```"):
        value = re.sub(r"^```[a-zA-Z]*\s*", "", value)
        value = re.sub(r"\s*```$", "", value)
    match = re.search(r"\{.*\}", value, re.S)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def fallback_route(question: str) -> dict[str, Any]:
    """模型不可用或返回不可解析时，用固定关键词兜底；不让模型自由发挥。"""
    text = str(question or "")
    # 先判综合诊断：出现“营销/怎么打”时即使带“竞品/对标”也不是双车逐项对比。
    if re.search(r"综合|整体|怎么打|如何打|营销|诊断", text):
        return {"template": "W1", "metric": None, "competitor": None, "confidence": 0.6, "source": "fallback"}
    if re.search(r"对比|差异|vs|VS|和.{1,12}比", text):
        return {"template": "W2", "metric": None, "competitor": None, "confidence": 0.6, "source": "fallback"}
    if re.search(r"口碑|评论|负面|吐槽", text):
        return {"template": "W4", "metric": None, "competitor": None, "confidence": 0.6, "source": "fallback"}
    metric = None
    if re.search(r"关注|在意|看重", text):
        metric = "attention"
    elif re.search(r"没买|战败|为什么买|放弃", text):
        metric = "winloss"
    elif re.search(r"满意|评分|推荐", text):
        metric = "satisfaction"
    elif re.search(r"画像|人群|年龄|职业|收入", text):
        metric = "profile"
    if metric:
        return {"template": "W3", "metric": metric, "competitor": None, "confidence": 0.55, "source": "fallback"}
    return {"template": "unknown", "metric": None, "competitor": None, "confidence": 0.4, "source": "fallback"}


def _normalize_route(parsed: dict[str, Any], source: str) -> dict[str, Any]:
    template = str(parsed.get("template") or "").strip()
    if template not in TEMPLATES:
        template = "unknown"
    metric = parsed.get("metric")
    if metric not in METRICS:
        metric = None
    competitor = parsed.get("competitor")
    competitor = str(competitor).strip() if competitor and str(competitor).strip() not in {"null", "None"} else None
    confidence = parsed.get("confidence")
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.0
    route = {
        "template": template,
        "metric": metric,
        "competitor": competitor,
        "confidence": confidence,
        "source": source,
    }
    if parsed.get("reject_reason"):
        route["reject_reason"] = str(parsed["reject_reason"])
    return route


# --------------------------------------------------------------------- 工作流


def _fmt_ratio(item: dict[str, Any]) -> str:
    if item.get("ratio") is None:
        return f"{item.get('count', 0)}/{item.get('n', 0)}（不展示比例）"
    return f"{item.get('count', 0)}/{item.get('n', 0)}（{item.get('ratio')}%）"


class AgentAnalysisService:
    """对外只暴露 run()；靶心由请求给定，模型不参与选择车型。"""

    def __init__(
        self,
        reader_factory=None,
        llm: LLM | None = None,
        config_path: Path | None = None,
    ) -> None:
        self.service = AnalysisService(reader_factory=reader_factory, config_path=config_path)
        self.llm = llm

    # ---------------------------------------------------------------- 入口

    def run(self, model_key: str, question: str, power_form: str | None = None) -> dict[str, Any]:
        question = str(question or "").strip()
        if not question:
            raise AnalysisError("question_required", "请输入要分析的问题。", 400)
        if len(question) > 300:
            raise AnalysisError("question_too_long", "问题请控制在 300 字以内。", 400)
        target = self.service._model(model_key)
        timings: dict[str, int] = {}
        started = time.perf_counter()
        route = self._route(question)
        timings["route"] = _ms(started)
        template = route["template"]

        if template == "unknown":
            return self._simple(target, question, route, "clarify", CLARIFY_TEXT)
        if template in UNSUPPORTED_TEMPLATES:
            return self._simple(target, question, route, "unsupported", UNSUPPORTED_TEMPLATES[template])

        reader = self.service._reader(power_form)
        toolbox = Toolbox(self.service, reader, power_form)
        try:
            if template == "W1":
                result = self._run_w1(toolbox, target, question, route, timings)
            else:
                result = self._run_w2(toolbox, target, question, route, timings)
            result["timings"] = {**timings, "total": _ms(started)}
            return result
        except AnalysisError:
            raise
        finally:
            reader.close()

    def _simple(
        self, target: dict[str, Any], question: str, route: dict[str, Any], status: str, message: str
    ) -> dict[str, Any]:
        return {
            "status": status,
            "template": route["template"],
            "question": question,
            "model": {"key": target["key"], "label": target["label"]},
            "router": route,
            "message": message,
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }

    # ---------------------------------------------------------------- 路由

    def _as_model(self, label: str) -> dict[str, Any]:
        """竞品池成员可能不在五款配置里；按实际购车名称构造只读车型描述。"""
        for model in self.service.config()["models"]:
            if _name_key(model["label"]) == _name_key(label):
                return model
        return {
            "key": label,
            "label": label,
            "quant_models": [label],
            "interview_models": [label],
            "reputation_models": [label],
            "miit_models": [label],
        }

    def _route(self, question: str) -> dict[str, Any]:
        if self.llm is None:
            return fallback_route(question)
        try:
            raw = self.llm(ROUTER_PROMPT, f"用户问题：{question}")
        except Exception:  # noqa: BLE001 - 路由失败按关键词兜底，不把异常抛给页面
            return fallback_route(question)
        parsed = _parse_json(raw)
        if not parsed:
            return fallback_route(question)
        return _normalize_route(parsed, "model")

    # ---------------------------------------------------------------- W1

    def _run_w1(
        self,
        toolbox: Toolbox,
        target: dict[str, Any],
        question: str,
        route: dict[str, Any],
        timings: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        tools_started = time.perf_counter()
        context = toolbox.context(target)
        profile = toolbox.quant_distribution(target, "profile")
        attention = toolbox.quant_distribution(target, "attention")
        winloss = toolbox.winloss(target)
        satisfaction = toolbox.satisfaction(target)
        rep_positive = toolbox.reputation(target, "positive")
        rep_negative = toolbox.reputation(target, "negative")
        pool = toolbox.competitor_candidates(target, 3)
        quotes = toolbox.interview_quotes(target, "all", 6)
        circulation = toolbox.circulation([target])

        catalog, warnings = self._catalog_w1(
            context, profile, attention, winloss, satisfaction, rep_positive, rep_negative, pool, quotes, circulation
        )
        payload = {
            "template": "W1",
            "target": target["label"],
            "question": question,
            "evidence_catalog": catalog,
            "pool": pool["data"],
            "circulation": circulation["data"],
            "warnings": warnings,
        }
        if timings is not None:
            timings["tools"] = _ms(tools_started)
        answer = self._compose("W1", payload, catalog, [], toolbox, timings)
        return self._ok(target, question, route, answer, pool, [context, profile, attention, winloss, satisfaction, rep_positive, rep_negative, pool, quotes, circulation], warnings)

    def _catalog_w1(
        self,
        context,
        profile,
        attention,
        winloss,
        satisfaction,
        rep_positive,
        rep_negative,
        pool,
        quotes,
        circulation,
    ) -> tuple[list[dict[str, str]], list[str]]:
        catalog: list[dict[str, str]] = []
        warnings: list[str] = []

        sources = context["data"]["sources"]
        catalog.append(
            {
                "ref": "T1:context",
                "text": f"定量 {sources.get('quant', 0)} 人，深访 {sources.get('interview', 0)} 人，口碑提及 {sources.get('reputation', 0)} 条",
            }
        )

        for item in profile["data"]["items"][:4]:
            catalog.append(
                {
                    "ref": f"T2:profile.{item['segment_key']}.{item['label']}",
                    "text": f"{item['segment']}·{item['label']} {_fmt_ratio(item)}",
                }
            )
        for item in attention["data"]["items"][:5]:
            catalog.append({"ref": f"T2:attention.{item['key']}", "text": f"购车关注·{item['label']} {_fmt_ratio(item)}"})
        for item in attention["data"]["items"][5:8]:
            catalog.append({"ref": f"T2:attention.{item['key']}", "text": f"购车关注·{item['label']} {_fmt_ratio(item)}"})
        for item in winloss["data"]["win"]["items"][:3]:
            catalog.append({"ref": f"T3:win.{item['key']}", "text": f"选择本车原因·{item['label']} {_fmt_ratio(item)}"})
        for row in winloss["data"]["loss"]["rows"][:3]:
            catalog.append(
                {
                    "ref": f"T3:loss.{row['model']}.people",
                    "text": f"对比过本品后买 {row['model']} {row['people']} 人（对比总数 {row['total_compared']}）",
                }
            )
            for index, reason in enumerate(row.get("reasons", [])[:2]):
                catalog.append(
                    {
                        "ref": f"T3:loss.{row['model']}.reason[{index}]",
                        "text": f"{row['model']} 胜出原因·{reason['label']} {reason['count']} 人",
                    }
                )
        overall = satisfaction["data"]["overall"]
        if overall.get("mean") is not None:
            catalog.append(
                {
                    "ref": "T4:overall",
                    "text": f"整体满意度 {overall['mean']} 分（{overall['answered']}/{overall['n']} 人作答）",
                }
            )
        rated = [item for item in satisfaction["data"]["dims"] if item.get("mean") is not None]
        for item in sorted(rated, key=lambda value: (value["mean"], value["label"]))[:4]:
            catalog.append(
                {
                    "ref": f"T4:dim.{item['key']}",
                    "text": f"满意度·{item['label']} {item['mean']} 分（{item['answered']} 人作答）",
                }
            )
        for item in rep_positive["data"]["items"][:3]:
            catalog.append(
                {
                    "ref": f"T5:positive.{item['label']}",
                    "text": f"口碑正向·{item['label']} {item['count']} 条/分母 {item['denominator']}",
                }
            )
        for item in rep_negative["data"]["items"][:3]:
            catalog.append(
                {
                    "ref": f"T5:negative.{item['label']}",
                    "text": f"口碑负向·{item['label']} {item['count']} 条/分母 {item['denominator']}",
                }
            )
        for index, row in enumerate(pool["data"]["pool"]):
            catalog.append(
                {
                    "ref": f"T8:pool.{index}",
                    "text": f"竞品池第 {index + 1}·{row['model']} {row['people']} 人/对比总数 {row['total_compared']}"
                    + (f"（{row['ratio']}%）" if row.get("ratio") is not None else ""),
                }
            )
        for quote in quotes["data"]["quotes"]:
            catalog.append({"ref": f"T6:{quote['ref']}", "text": f"深访原话（{quotes['data']['people']} 人）「{quote['text']}」"})
        catalog.append({"ref": "T7:circulation", "text": circulation["data"]["reason"]})

        if circulation["status"] == "not_available":
            warnings.append("流通数据尚未接入，本次结论不含规模维度。")
        if quotes["data"]["people"] and quotes["data"]["people"] < 5:
            warnings.append(f"深访仅 {quotes['data']['people']} 人，只出原话，不构成比例证据。")
        return catalog, warnings

    # ---------------------------------------------------------------- W2

    def _run_w2(
        self,
        toolbox: Toolbox,
        target: dict[str, Any],
        question: str,
        route: dict[str, Any],
        timings: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        tools_started = time.perf_counter()
        pool = toolbox.competitor_candidates(target, 3)
        if not pool["data"]["pool"]:
            return self._simple(
                target,
                question,
                route,
                "no_comparison_sample",
                "本品暂无对比样本，无法定位竞品；可改用单车型综合诊断。",
            )

        pool_rows = pool["data"]["pool"]
        requested = route.get("competitor")
        chosen = None
        if requested:
            requested_key = _name_key(normalize_competitor(requested, self.service.config().get("competitor_aliases") or {}))
            chosen = next((row for row in pool_rows if _name_key(row["model"]) == requested_key), None)
            if chosen is None:
                return {
                    "status": "no_comparison_sample",
                    "template": "W2",
                    "question": question,
                    "model": {"key": target["key"], "label": target["label"]},
                    "router": route,
                    "message": "该车型与本品无对比样本。",
                    "pool": pool_rows,
                    "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                }
        else:
            chosen = pool_rows[0]

        competitor = self._as_model(chosen["model"])
        context_a = toolbox.context(target)
        context_b = toolbox.context(competitor)
        compare_attention = toolbox.compare_metric(target, competitor, "attention")
        compare_profile = toolbox.compare_metric(target, competitor, "profile")
        compare_satisfaction = toolbox.compare_metric(target, competitor, "satisfaction")
        head = toolbox.head_to_head(target, competitor)
        satisfaction_a = toolbox.satisfaction(target)
        satisfaction_b = toolbox.satisfaction(competitor)
        rep_a_pos = toolbox.reputation(target, "positive")
        rep_a_neg = toolbox.reputation(target, "negative")
        rep_b_pos = toolbox.reputation(competitor, "positive")
        rep_b_neg = toolbox.reputation(competitor, "negative")
        quotes_a = toolbox.interview_quotes(target, "all", 3)
        quotes_b = toolbox.interview_quotes(competitor, "all", 3)
        circulation = toolbox.circulation([target, competitor])

        catalog, warnings, compare_rows = self._catalog_w2(
            pool,
            chosen,
            context_a,
            context_b,
            compare_attention,
            compare_profile,
            compare_satisfaction,
            head,
            satisfaction_a,
            satisfaction_b,
            rep_a_pos,
            rep_a_neg,
            rep_b_pos,
            rep_b_neg,
            quotes_a,
            quotes_b,
            circulation,
        )
        payload = {
            "template": "W2",
            "target": target["label"],
            "competitor": competitor["label"],
            "question": question,
            "evidence_catalog": catalog,
            "pool": pool["data"],
            "comparison": compare_rows,
            "circulation": circulation["data"],
            "warnings": warnings,
        }
        if timings is not None:
            timings["tools"] = _ms(tools_started)
        answer = self._compose("W2", payload, catalog, compare_rows, toolbox, timings)
        result = self._ok(
            target,
            question,
            route,
            answer,
            pool,
            [context_a, context_b, compare_attention, compare_profile, compare_satisfaction, head, satisfaction_a, satisfaction_b, rep_a_pos, rep_a_neg, rep_b_pos, rep_b_neg, pool, quotes_a, quotes_b, circulation],
            warnings,
        )
        result["competitor"] = {"key": competitor["key"], "label": competitor["label"]}
        result["pool_rank"] = next(index + 1 for index, row in enumerate(pool_rows) if row["model"] == chosen["model"])
        return result

    def _catalog_w2(
        self,
        pool,
        chosen,
        context_a,
        context_b,
        compare_attention,
        compare_profile,
        compare_satisfaction,
        head,
        satisfaction_a,
        satisfaction_b,
        rep_a_pos,
        rep_a_neg,
        rep_b_pos,
        rep_b_neg,
        quotes_a,
        quotes_b,
        circulation,
    ) -> tuple[list[dict[str, str]], list[str], list[dict[str, Any]]]:
        catalog: list[dict[str, str]] = []
        warnings: list[str] = []
        compare_rows: list[dict[str, Any]] = []

        rank = int(chosen.get("rank") or next(index + 1 for index, row in enumerate(pool["data"]["pool"]) if row["model"] == chosen["model"]))
        catalog.append(
            {
                "ref": f"T8:pool.{rank - 1}",
                "text": f"本次对标 {pool['data']['target']} vs {chosen['model']}（池内第 {rank}，{chosen['people']} 人，对比总数 {chosen['total_compared']}"
                + (f"，{chosen['ratio']}%" if chosen.get("ratio") is not None else "")
                + "）",
            }
        )
        for index, row in enumerate(pool["data"]["pool"]):
            if index == rank - 1:
                continue
            catalog.append(
                {
                    "ref": f"T8:pool.{index}",
                    "text": f"竞品池第 {index + 1}·{row['model']} {row['people']} 人/对比总数 {row['total_compared']}",
                }
            )

        for result, metric in (
            (compare_attention, "购车关注"),
            (compare_profile, "用户画像"),
            (compare_satisfaction, "满意度"),
        ):
            for row in result["data"]["rows"]:
                compare_rows.append({"metric": metric, **row})
                text = self._compare_text(metric, row, pool["data"]["target"], chosen["model"])
                if text:
                    catalog.append({"ref": f"T10:{metric}.{row['key']}", "text": text})

        head_data = head["data"]
        catalog.append(
            {
                "ref": "T9:a_to_b",
                "text": f"{head_data['a']}→{head_data['b']}：{head_data['a_to_b']['people']} 人（对比总数 {head_data['a_to_b']['total_compared']}）"
                + (f"，{head_data['a_to_b']['ratio']}%" if head_data["a_to_b"].get("ratio") is not None else "，不展示比例"),
            }
        )
        catalog.append(
            {
                "ref": "T9:b_to_a",
                "text": f"{head_data['b']}→{head_data['a']}：{head_data['b_to_a']['people']} 人（对比总数 {head_data['b_to_a']['total_compared']}）"
                + (f"，{head_data['b_to_a']['ratio']}%" if head_data["b_to_a"].get("ratio") is not None else "，不展示比例"),
            }
        )
        for row in head_data["a_to_b"].get("reasons", [])[:2]:
            catalog.append({"ref": f"T9:a_to_b.reason[{row['label']}]", "text": f"{head_data['a']}流向{head_data['b']}的原因·{row['label']} {row['count']} 人"})

        for prefix, data in (("a", satisfaction_a), ("b", satisfaction_b)):
            overall = data["data"]["overall"]
            if overall.get("mean") is not None:
                catalog.append(
                    {
                        "ref": f"T4:{prefix}.overall",
                        "text": f"车型整体满意度 {overall['mean']} 分（{overall['answered']}/{overall['n']} 人作答）",
                    }
                )
            rated = [item for item in data["data"]["dims"] if item.get("mean") is not None]
            for item in sorted(rated, key=lambda value: (value["mean"], value["label"]))[:3]:
                catalog.append(
                    {
                        "ref": f"T4:{prefix}.dim.{item['key']}",
                        "text": f"{'本品' if prefix == 'a' else '对标车'}满意度·{item['label']} {item['mean']} 分（{item['answered']} 人作答）",
                    }
                )

        for prefix, positive, negative, label in (
            ("a", rep_a_pos, rep_a_neg, "本品"),
            ("b", rep_b_pos, rep_b_neg, "对标车"),
        ):
            for item in positive["data"]["items"][:2]:
                catalog.append(
                    {
                        "ref": f"T5:{prefix}.positive.{item['label']}",
                        "text": f"{label}口碑正向·{item['label']} {item['count']} 条/分母 {item['denominator']}",
                    }
                )
            for item in negative["data"]["items"][:2]:
                catalog.append(
                    {
                        "ref": f"T5:{prefix}.negative.{item['label']}",
                        "text": f"{label}口碑负向·{item['label']} {item['count']} 条/分母 {item['denominator']}",
                    }
                )

        for quotes, label in ((quotes_a, "本品"), (quotes_b, "对标车")):
            for quote in quotes["data"]["quotes"]:
                catalog.append(
                    {
                        "ref": f"T6:{quote['ref']}",
                        "text": f"{label}深访原话（{quotes['data']['people']} 人）「{quote['text']}」",
                    }
                )

        catalog.append({"ref": "T7:circulation", "text": circulation["data"]["reason"]})

        if circulation["status"] == "not_available":
            warnings.append("流通数据尚未接入，本次结论不含规模维度。")
        small = [row["label"] for row in compare_rows if row["level"] != "L0"]
        if small:
            warnings.append("以下维度样本不足，只给人数与原话：" + "、".join(small[:8]))
        return catalog, warnings, compare_rows

    @staticmethod
    def _compare_text(metric: str, row: dict[str, Any], a_label: str, b_label: str) -> str:
        side_a, side_b = row["a"], row["b"]
        if side_a.get("ratio") is not None and side_b.get("ratio") is not None:
            return (
                f"{metric}·{row['label']}：{a_label} {side_a['ratio']}%（{side_a['count']}/{side_a['n']}）"
                f" vs {b_label} {side_b['ratio']}%（{side_b['count']}/{side_b['n']}），差 {row.get('delta_pp')} 个百分点"
            )
        if side_a.get("mean") is not None and side_b.get("mean") is not None:
            return (
                f"{metric}·{row['label']}：{a_label} {side_a['mean']} 分（{side_a['answered']} 人）"
                f" vs {b_label} {side_b['mean']} 分（{side_b['answered']} 人），差 {row.get('delta')} 分"
            )
        return f"{metric}·{row['label']}：{a_label} {side_a.get('count', side_a.get('answered', 0))} 人，{b_label} {side_b.get('count', side_b.get('answered', 0))} 人（样本不足，不出差值）"

    # ---------------------------------------------------------------- 合成

    def _compose(
        self,
        template: str,
        payload: dict[str, Any],
        catalog: list[dict[str, str]],
        compare_rows: list[dict[str, Any]],
        toolbox: Toolbox,
        timings: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        if self.llm is None:
            raise AgentAnalysisError("E_MODEL_UNAVAILABLE", "未注入模型通道，无法生成结论。", 503)
        system_prompt = COMPOSE_PROMPTS[template]
        message = "【输入】\n" + json.dumps(payload, ensure_ascii=False, indent=1)
        model_names = [payload.get("target"), payload.get("competitor")]
        model_names += [row.get("model") for row in (payload.get("pool") or {}).get("pool", [])]
        model_names = [str(name) for name in model_names if name]
        problems: list[str] = []
        answer: dict[str, Any] | None = None
        attempts = 0
        compose_ms = 0
        validate_ms = 0
        for attempt in range(2):
            attempts = attempt + 1
            llm_started = time.perf_counter()
            try:
                raw = self.llm(system_prompt, message if not problems else message + "\n【上一次输出不合格】" + "；".join(problems) + "。请修正后重新输出完整 JSON。")
            except Exception as exc:  # noqa: BLE001 - 模型失败如实返回错误码
                raise AgentAnalysisError("E_MODEL_FAILED", f"模型调用失败：{exc.__class__.__name__}", 503) from exc
            compose_ms += _ms(llm_started)
            parsed = _parse_json(raw)
            if not parsed:
                problems = ["输出不是合法 JSON"]
                continue
            normalized = self._normalize_answer(template, parsed)
            validate_started = time.perf_counter()
            problems = self._validate(template, normalized, {item["ref"] for item in catalog}, self._numeric_values(toolbox), compare_rows, model_names)
            validate_ms += _ms(validate_started)
            if not problems:
                answer = normalized
                break
        if timings is not None:
            timings["compose"] = compose_ms
            timings["validate"] = validate_ms
        if answer is None:
            code = "E_NUM_UNVERIFIED" if any("数字" in problem for problem in problems) else "E_VALIDATION_FAILED"
            raise AgentAnalysisError(code, "结论未通过校验：" + "；".join(problems[:4]) + "。未渲染结论。", 422)
        return {"answer": answer, "attempts": attempts}

    @staticmethod
    def _normalize_answer(template: str, parsed: dict[str, Any]) -> dict[str, Any]:
        def items(value: Any) -> list[dict[str, Any]]:
            result = []
            for entry in value if isinstance(value, list) else []:
                if isinstance(entry, str):
                    result.append({"text": entry.strip(), "refs": []})
                elif isinstance(entry, dict):
                    refs = entry.get("refs")
                    result.append(
                        {
                            "text": str(entry.get("text") or "").strip(),
                            "refs": [str(ref) for ref in refs] if isinstance(refs, list) else [],
                        }
                    )
            return result

        if template == "W1":
            return {
                "template": "W1",
                "evidence": items(parsed.get("evidence")),
                "causes": items(parsed.get("causes")),
                "actions": items(parsed.get("actions")),
                "sample_note": str(parsed.get("sample_note") or "").strip(),
            }
        benchmark = parsed.get("benchmark")
        if isinstance(benchmark, str):
            benchmark = {"text": benchmark.strip(), "refs": []}
        elif not isinstance(benchmark, dict):
            benchmark = {"text": "", "refs": []}
        return {
            "template": "W2",
            "benchmark": {"text": str(benchmark.get("text") or "").strip(), "refs": [str(ref) for ref in benchmark.get("refs") or []]},
            "differences": items(parsed.get("differences")),
            "causes": items(parsed.get("causes")),
            "gaps": items(parsed.get("gaps")),
            "sample_note": str(parsed.get("sample_note") or "").strip(),
        }

    @staticmethod
    def _numeric_values(toolbox: Toolbox) -> set[float]:
        values: set[float] = set()
        for item in toolbox.index:
            value = round(item["value"], 4)
            values.add(value)
            values.add(abs(value))  # 差值可为负，正文常写“差 12.5 个百分点”
        return values

    def _validate(
        self,
        template: str,
        answer: dict[str, Any],
        refs: set[str],
        numbers: set[float],
        compare_rows: list[dict[str, Any]],
        model_names: list[str],
    ) -> list[str]:
        problems: list[str] = []
        if template == "W1":
            blocks = [answer["evidence"], answer["causes"], answer["actions"]]
            required = {"evidence": answer["evidence"], "causes": answer["causes"], "actions": answer["actions"]}
        else:
            blocks = [[answer["benchmark"]], answer["differences"], answer["causes"], answer["gaps"]]
            required = {
                "benchmark": [answer["benchmark"]],
                "differences": answer["differences"],
                "causes": answer["causes"],
                "gaps": answer["gaps"],
            }
        for name, entries in required.items():
            if not entries or not any(entry.get("text") for entry in entries):
                problems.append(f"{name} 为空")
        # 提示词仍要求 W1 ≤450 / W2 ≤400 字；硬校验留出模型抖动余量，避免因几十字超限丢掉整份结论。
        limits = {"W1": 600, "W2": 650}
        total_chars = sum(len(entry.get("text") or "") for entries in blocks for entry in entries)
        if total_chars > limits[template]:
            problems.append(f"正文 {total_chars} 字，超过 {limits[template]} 字上限")

        compare_refs = {f"T10:购车关注.{row['key']}": row for row in compare_rows}
        compare_refs.update({f"T10:用户画像.{row['key']}": row for row in compare_rows})
        compare_refs.update({f"T10:满意度.{row['key']}": row for row in compare_rows})

        for entries in blocks:
            for entry in entries:
                text = str(entry.get("text") or "")
                entry_refs = entry.get("refs") or []
                if not text:
                    problems.append("存在空结论")
                    continue
                if not entry_refs:
                    problems.append("存在未挂证据的结论")
                for ref in entry_refs:
                    if ref not in refs:
                        problems.append(f"引用不在本次证据表：{ref}")
                if any(word in text for word in BANNED_WORDS):
                    problems.append("出现全称词（都/全部/唯一/仅有）")
                if any(phrase in text for phrase in SHARE_PHRASES) or re.search(r"领先(?:竞品|市场).{0,6}\d+(?:\.\d+)?%", text):
                    problems.append("把口碑/对标写成跨车份额或市场领先")
                if re.search(r"综合评分|综合指数|重叠人群", text):
                    problems.append("出现综合评分、重叠人群或合并口径")
                if entry_refs and all(ref.startswith("T6:") for ref in entry_refs):
                    if "%" in text or "多数" in text or "大部分" in text:
                        problems.append("深访原话出现比例或群体化表述")
                for ref in entry_refs:
                    row = compare_refs.get(ref)
                    if row and row.get("level") != "L0" and re.search(r"高于|优于|领先|落后", text):
                        problems.append(f"小样本维度做了优劣判断：{row['label']}")
                for token in self._numbers_in(text, model_names):
                    if not self._number_allowed(token, numbers):
                        problems.append(f"数字未在证据中登记：{token}")
        note = str(answer.get("sample_note") or "").strip()
        if not note:
            problems.append("sample_note 为空")
        else:
            if any(word in note for word in BANNED_WORDS):
                problems.append("sample_note 出现全称词")
            for token in self._numbers_in(note, model_names):
                if not self._number_allowed(token, numbers):
                    problems.append(f"sample_note 数字未在证据中登记：{token}")
        # 去重，保留顺序
        return list(dict.fromkeys(problems))

    @staticmethod
    def _numbers_in(text: str, model_names: list[str] | None = None) -> list[str]:
        value = str(text or "")
        # 车名本身带数字（海狮05、铂智3X、V23），先整体抹掉再校验，避免把车名当结论数字。
        for name in sorted(model_names or [], key=len, reverse=True):
            if name:
                value = value.replace(name, " ")
        for pattern in STRIP_NUMBER_PATTERNS:
            value = pattern.sub(" ", value)
        return NUMBER_RE.findall(value)

    @staticmethod
    def _number_allowed(token: str, numbers: set[float]) -> bool:
        try:
            value = float(token)
        except ValueError:
            return True
        return any(abs(value - allowed) <= 0.051 for allowed in numbers)

    # ---------------------------------------------------------------- 结果

    def _ok(
        self,
        target: dict[str, Any],
        question: str,
        route: dict[str, Any],
        composed: dict[str, Any],
        pool: dict[str, Any],
        tools: list[dict[str, Any]],
        warnings: list[str],
    ) -> dict[str, Any]:
        return {
            "status": "ok",
            "template": route["template"],
            "question": question,
            "model": {"key": target["key"], "label": target["label"]},
            "router": route,
            "answer": composed["answer"],
            "pool": pool["data"],
            "tools": [
                {"tool": tool["tool"], "status": tool["status"], "caliber": tool["caliber"]}
                for tool in tools
            ],
            "warnings": warnings,
            "verification": {"attempts": composed["attempts"], "result": "passed"},
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
