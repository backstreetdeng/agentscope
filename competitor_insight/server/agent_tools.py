"""BCI-006 · 智能化分析工具层。

只做三件事：按车型取数、按既有口径聚合、为每个数字登记来源（numeric_index）。
不做算术结论、不调用模型；工作流与合成在 `agent_analysis.py`。

复用 `analysis_service` 的既有方法，不重写 SQL；连接只读。
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from competitor_insight.server.analysis_service import (
    ABANDON_PREFIX,
    ABANDON_QUESTIONS,
    ATTENTION_PREFIX,
    DIMENSIONS,
    REPUTATION_LABEL_ALIAS,
    REPUTATION_MIN_DENOMINATOR,
    REPUTATION_TOP_N,
    SCORE_PREFIX,
    WIN_PREFIX,
    WIN_QUESTIONS,
    AnalysisError,
    AnalysisService,
    normalize_competitor,
    parse_recommendation,
    ratio_payload,
    sample_flag,
    _name_key,
)

CIRCULATION_REASON = "流通数据未接入"
PROFILE_COMPARE_SEGMENTS = (
    ("age_band", "年龄段", "column"),
    ("gender", "性别", "column"),
    ("city", "城市", "column"),
    ("price_band", "购车价格段", "column"),
    ("purchase_type", "购车类型", "column"),
)


def _walk_numbers(node: Any, path: str, sink: list[dict[str, Any]]) -> None:
    if isinstance(node, bool) or node is None:
        return
    if isinstance(node, dict):
        for key, value in node.items():
            _walk_numbers(value, f"{path}.{key}", sink)
    elif isinstance(node, (list, tuple)):
        for index, value in enumerate(node):
            _walk_numbers(value, f"{path}[{index}]", sink)
    elif isinstance(node, (int, float)):
        sink.append({"value": float(node), "path": path})


class Toolbox:
    """一次请求内复用一个只读连接；所有工具返回统一信封。"""

    def __init__(self, service: AnalysisService, reader, power_form: str | None = None) -> None:
        self.service = service
        self.reader = reader
        self.config = service.config()
        self.power_form = power_form
        self.index: list[dict[str, Any]] = []
        self.as_of = datetime.now().astimezone().isoformat(timespec="seconds")

    # ---------------------------------------------------------------- 信封

    def _collect(self, data: Any, tool: str) -> None:
        found: list[dict[str, Any]] = []
        _walk_numbers(data, tool, found)
        for item in found:
            item["tool"] = tool
            self.index.append(item)

    def _envelope(
        self,
        tool: str,
        args: dict[str, Any],
        status: str,
        data: dict[str, Any],
        caliber: dict[str, Any],
        hidden: list[str] | None = None,
    ) -> dict[str, Any]:
        self._collect(data, tool)
        return {
            "tool": tool,
            "args": args,
            "status": status,
            "data": data,
            "caliber": caliber,
            "hidden": hidden or [],
        }

    def _register_quote_numbers(self, ref: str, text: str) -> None:
        for token in re.findall(r"\d+(?:\.\d+)?", text):
            self.index.append({"value": float(token), "path": ref, "tool": "bci_interview_quotes"})

    def _caliber(self, n: int, question: str, table: str = "user_insight.quant_sample") -> dict[str, Any]:
        return {
            "n": int(n),
            "denominator": int(n),
            "unit": "人",
            "question": question,
            "table": table,
            "as_of": self.as_of,
        }

    # ---------------------------------------------------------------- T1

    def context(self, model: dict[str, Any]) -> dict[str, Any]:
        sources = self.reader.source_counts(model)
        missing = [
            label
            for key, label in (("quant", "定量"), ("interview", "深访"), ("reputation", "口碑"))
            if not sources.get(key)
        ]
        data = {
            "model": model["label"],
            "sources": sources,
            "missing": missing,
            "dimensions": len(DIMENSIONS),
            "circulation": {"status": "not_available", "reason": CIRCULATION_REASON},
        }
        return self._envelope(
            "bci_model_context",
            {"model": model["label"]},
            "ok" if sources.get("quant") else "empty",
            data,
            self._caliber(sources.get("quant", 0), "多源样本量", "user_insight.quant_sample / interview"),
        )

    # ---------------------------------------------------------------- T2

    def quant_distribution(self, model: dict[str, Any], metric: str) -> dict[str, Any]:
        counts = self.reader.quant_answered_full(model)
        n = int(counts.get("n") or 0)
        if metric == "profile":
            items: list[dict[str, Any]] = []
            for field, label, kind in PROFILE_COMPARE_SEGMENTS:
                for row in self.reader.distribution(model, field, kind)[:4]:
                    items.append(
                        ratio_payload(int(row["count"]), n)
                        | {"segment": label, "segment_key": field, "label": row["label"]}
                    )
            data = {"metric": metric, "n": n, "answered": n, "items": items}
            question = "age_band / gender / city / price_band / purchase_type"
        else:
            spec = {
                "attention": (ATTENTION_PREFIX, "Q3_13", "Q3_13__1..16"),
                "win": (WIN_PREFIX, "Q3_23", "Q3_23__1..16"),
                "abandon": (ABANDON_PREFIX, "Q3_24_1", "Q3_24_1__1..16"),
            }.get(metric)
            if not spec:
                raise AnalysisError("invalid_metric", f"不支持的定量指标：{metric}", 400)
            prefix, answered_key, question = spec
            answered = int(counts.get(answered_key) or 0)
            raw = self.reader.multi_counts(model, prefix)
            items = [
                ratio_payload(int(raw.get(f"c{index}") or 0), n, answered)
                | {"key": f"{prefix}{index}", "label": label}
                for index, label in DIMENSIONS
            ]
            items.sort(key=lambda item: (-item["count"], item["label"]))
            data = {"metric": metric, "n": n, "answered": answered, "items": items}
        status = "ok" if n and (data["answered"] >= 10) else ("empty" if not n else "insufficient")
        return self._envelope(
            "bci_quant_distribution",
            {"model": model["label"], "metric": metric},
            status,
            data,
            self._caliber(n, question),
            hidden=[item.get("ratio_hidden_reason", "") for item in data.get("items", []) if item.get("ratio") is None][:3],
        )

    # ---------------------------------------------------------------- T3

    def winloss(self, model: dict[str, Any]) -> dict[str, Any]:
        counts = self.reader.quant_answered_full(model)
        n = int(counts.get("n") or 0)
        answered = int(counts.get("Q3_23") or 0)
        raw = self.reader.multi_counts(model, WIN_PREFIX)
        win_items = [
            ratio_payload(int(raw.get(f"c{index}") or 0), n, answered)
            | {"key": f"{WIN_PREFIX}{index}", "label": label}
            for index, label in DIMENSIONS
        ]
        win_items.sort(key=lambda item: (-item["count"], item["label"]))
        loss = self.service._loss_split(self.reader, model, self.config)
        rows = [
            {
                "model": item["label"],
                "people": item["count"],
                "total_compared": item["n"],
                "ratio": item.get("ratio"),
                "ratio_hidden_reason": item.get("ratio_hidden_reason"),
                "reasons": [
                    {"label": reason["label"], "count": reason["count"], "ratio": reason.get("ratio")}
                    for reason in item.get("reasons", [])[:3]
                ],
            }
            for item in loss.get("items", [])
        ]
        data = {
            "n": n,
            "win": {"answered": answered, "items": win_items[:5]},
            "loss": {
                "target": loss.get("target"),
                "total_compared": loss.get("n", 0),
                "all_rows": len(rows),
                "rows": rows[:5],
            },
        }
        status = "ok" if n and answered >= 10 else ("empty" if not n else "insufficient")
        return self._envelope(
            "bci_winloss",
            {"model": model["label"]},
            status,
            data,
            self._caliber(n, "Q3_23__1..16 × Q3_22_1__1/2/3 × Q3_24_1/3/5"),
        )

    # ---------------------------------------------------------------- T4

    def satisfaction(self, model: dict[str, Any]) -> dict[str, Any]:
        counts = self.reader.quant_answered_full(model)
        n = int(counts.get("n") or 0)
        raw = self.reader.score_stats(model)
        dims = []
        for index, label in DIMENSIONS:
            answered = int(raw.get(f"a{index}") or 0)
            mean = raw.get(f"m{index}")
            low = int(raw.get(f"l{index}") or 0)
            item = {
                "key": f"{SCORE_PREFIX}{index}",
                "label": label,
                "n": n,
                "answered": answered,
                "mean": round(float(mean), 2) if mean is not None else None,
                "low_count": low,
                "low_rate": round(low / answered * 100, 1) if answered >= 10 else None,
                "sample_flag": sample_flag(answered),
            }
            if answered < 10:
                item["ratio_hidden_reason"] = f"本维度仅 {answered} 人打分，低于 10 人门槛"
            dims.append(item)
        overall_raw = self.reader.overall_score(model)
        overall = {
            "mean": round(float(overall_raw["mean"]), 2) if overall_raw.get("mean") is not None else None,
            "answered": int(overall_raw.get("answered") or 0),
            "n": n,
        }
        recommendations = [parse_recommendation(value) for value in self.reader.recommendation_values(model)]
        recommendations = [value for value in recommendations if value]
        bands = [
            ("9–10 分 十分推荐", sum(1 for score, _ in recommendations if score >= 9)),
            ("7–8 分 比较推荐", sum(1 for score, _ in recommendations if 7 <= score <= 8)),
            ("5–6 分 说不好", sum(1 for score, _ in recommendations if 5 <= score <= 6)),
            ("4 分及以下 不推荐", sum(1 for score, _ in recommendations if score <= 4)),
        ]
        data = {
            "n": n,
            "overall": overall,
            "dims": dims,
            "recommendation": {
                "answered": len(recommendations),
                "items": [ratio_payload(count, n, len(recommendations)) | {"label": label} for label, count in bands],
            },
        }
        status = "ok" if overall["answered"] and any(item["mean"] is not None for item in dims) else "empty"
        return self._envelope(
            "bci_satisfaction",
            {"model": model["label"]},
            status,
            data,
            self._caliber(n, "Q5_1 / Q5_2__1..16 / Q5_5"),
        )

    # ---------------------------------------------------------------- T5

    def reputation(self, model: dict[str, Any], direction: str) -> dict[str, Any]:
        raw = self.reader.reputation(model)
        denominator = int(raw["denominators"].get(direction) or 0)
        rows = [row for row in raw["points"] if row.get("direction") == direction][:REPUTATION_TOP_N]
        items = [
            {
                "label": row["tertiary_label"],
                "l1": REPUTATION_LABEL_ALIAS.get(row["primary_label"], row["primary_label"]),
                "count": int(row["n"] or 0),
                "denominator": denominator,
                "ratio": round(int(row["n"] or 0) * 100 / denominator, 1) if denominator else None,
                "ratio_hidden_reason": None if denominator >= REPUTATION_MIN_DENOMINATOR else f"分母 {denominator} 条，低于 {REPUTATION_MIN_DENOMINATOR} 条门槛",
            }
            for row in rows
        ]
        data = {
            "model": model["label"],
            "direction": direction,
            "denominator": denominator,
            "batch": raw.get("batch"),
            "batch_reviews": raw.get("batch_reviews", 0),
            "items": items,
            "note": "外部评论标签，仅本车自身分布；不与问卷满意度合并，不做跨车差值。",
        }
        return self._envelope(
            "bci_reputation",
            {"model": model["label"], "direction": direction},
            "ok" if items else "empty",
            data,
            {
                "n": denominator,
                "denominator": denominator,
                "unit": "条",
                "question": "new_car_reputation_review_tag / autohome_koubei",
                "table": "public.new_car_reputation_review_tag",
                "as_of": self.as_of,
            },
        )

    # ---------------------------------------------------------------- T6

    def interview_quotes(self, model: dict[str, Any], topic: str = "all", top_k: int = 6) -> dict[str, Any]:
        if topic == "win":
            question_ids = WIN_QUESTIONS
            label = "选择当前车辆的原因（Q29）"
        elif topic == "abandon":
            question_ids = ABANDON_QUESTIONS
            label = "放弃对比车型的原因（Q27/Q28）"
        else:
            question_ids = tuple(WIN_QUESTIONS) + tuple(ABANDON_QUESTIONS)
            label = "选择与放弃原因（Q29 + Q27/Q28）"
        rows = self.reader.interview_reason_answers(model, question_ids)
        buckets: dict[str, list[dict[str, Any]]] = {}
        order: list[str] = []
        for row in rows:
            text = str(row.get("answer_text") or "").strip()
            if len(text) <= 5:
                continue
            interview_id = str(row["interview_id"])
            if interview_id not in buckets:
                buckets[interview_id] = []
                order.append(interview_id)
            buckets[interview_id].append(row | {"_text": text})

        people = set(buckets)
        quotes: list[dict[str, Any]] = []
        # 轮流取：先保证每个受访者出现一次，再补第二、第三条，避免 6 条原话都来自同一个人。
        for round_index in range(3):
            for interview_id in order:
                if len(quotes) >= top_k:
                    break
                bucket = buckets[interview_id]
                if round_index >= len(bucket):
                    continue
                row = bucket[round_index]
                text = row["_text"]
                ref = f"E{len(quotes) + 1}"
                quotes.append(
                    {
                        "ref": ref,
                        "interview_id": row["interview_id"],
                        "respondent_code": row.get("respondent_code") or row["interview_id"],
                        "question_id": f"Q{row['question_id']}",
                        "text": text[:300],
                    }
                )
                self._register_quote_numbers(ref, text)
        data = {
            "model": model["label"],
            "topic": topic,
            "label": label,
            "question_ids": [f"Q{qid}" for qid in question_ids],
            "people": len(people),
            "quotes": quotes,
            "note": f"深访 {len(people)} 人，逐人原话；仅作动机线索，不做比例、不外推群体。",
        }
        return self._envelope(
            "bci_interview_quotes",
            {"model": model["label"], "topic": topic, "top_k": top_k},
            "ok" if quotes else "empty",
            data,
            {
                "n": len(people),
                "denominator": len(people),
                "unit": "人",
                "question": "/".join(f"Q{qid}" for qid in question_ids),
                "table": "user_insight.interview / answer",
                "as_of": self.as_of,
            },
        )

    # ---------------------------------------------------------------- T7

    def circulation(self, models: list[dict[str, Any]]) -> dict[str, Any]:
        data = {
            "models": [model["label"] for model in models],
            "status": "not_available",
            "reason": CIRCULATION_REASON,
        }
        return self._envelope(
            "bci_market_circulation",
            {"models": data["models"]},
            "not_available",
            data,
            {"n": 0, "denominator": 0, "unit": "辆", "question": "未接入", "table": "", "as_of": self.as_of},
        )

    # ---------------------------------------------------------------- T8

    def _pool_rows(self, model: dict[str, Any], loss: dict[str, Any] | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        loss = loss or self.service._loss_split(self.reader, model, self.config)
        rows = [
            {
                "model": item["label"],
                "people": item["count"],
                "total_compared": item["n"],
                "ratio": item.get("ratio"),
                "ratio_hidden_reason": item.get("ratio_hidden_reason"),
                "reasons": [
                    {"label": reason["label"], "count": reason["count"], "ratio": reason.get("ratio")}
                    for reason in item.get("reasons", [])[:3]
                ],
            }
            for item in loss.get("items", [])
        ]
        return loss, rows

    def competitor_candidates(
        self, model: dict[str, Any], top_k: int = 3, loss: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        loss_data, rows = self._pool_rows(model, loss)
        pool = [{"rank": index + 1, **row} for index, row in enumerate(rows[:top_k])]
        data = {
            "target": model["label"],
            "total_compared": int(loss_data.get("n") or 0),
            "pool_size": len(rows),
            "top_k": top_k,
            "pool": pool,
            "all_models": [row["model"] for row in rows],
        }
        return self._envelope(
            "bci_competitor_candidates",
            {"model": model["label"], "top_k": top_k},
            "ok" if pool else "empty",
            data,
            self._caliber(int(loss_data.get("n") or 0), "Q3_22_1__1/2/3 × purchase_model"),
        )

    # ---------------------------------------------------------------- T9

    def head_to_head(self, a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
        aliases = self.config.get("competitor_aliases") or {}
        loss_a = self.service._loss_split(self.reader, a, self.config)
        loss_b = self.service._loss_split(self.reader, b, self.config)
        target_b = _name_key(normalize_competitor(b["label"], aliases))
        target_a = _name_key(normalize_competitor(a["label"], aliases))

        def side(loss: dict[str, Any], target_key: str) -> dict[str, Any]:
            for item in loss.get("items", []):
                if _name_key(item["label"]) != target_key:
                    continue
                return {
                    "people": item["count"],
                    "total_compared": item["n"],
                    "ratio": item.get("ratio"),
                    "ratio_hidden_reason": item.get("ratio_hidden_reason"),
                    "reasons": [
                        {"label": reason["label"], "count": reason["count"], "ratio": reason.get("ratio")}
                        for reason in item.get("reasons", [])[:3]
                    ],
                }
            return {
                "people": 0,
                "total_compared": int(loss.get("n") or 0),
                "ratio": None,
                "ratio_hidden_reason": "该方向无对比样本",
                "reasons": [],
            }

        a_to_b = side(loss_a, target_b)
        b_to_a = side(loss_b, target_a)
        if not a_to_b["people"] or not b_to_a["people"]:
            level = "L2"
        elif a_to_b["people"] >= 5 and b_to_a["people"] >= 5 and a_to_b["total_compared"] >= 10 and b_to_a["total_compared"] >= 10:
            level = "L0"
        else:
            level = "L1"
        data = {"a": a["label"], "b": b["label"], "a_to_b": a_to_b, "b_to_a": b_to_a, "level": level}
        return self._envelope(
            "bci_head_to_head",
            {"a": a["label"], "b": b["label"]},
            "ok" if level != "L2" else "empty",
            data,
            self._caliber(max(a_to_b["total_compared"], b_to_a["total_compared"]), "Q3_22_1__1/2/3 × Q3_24_1/3/5"),
        )

    # ---------------------------------------------------------------- T10

    @staticmethod
    def _compare_side(count: int, total: int, answered: int) -> dict[str, Any]:
        payload = {
            "count": int(count),
            "n": int(total),
            "answered": int(answered),
            "ratio": None,
            "sample_flag": sample_flag(total),
        }
        blockers = []
        if total < 10:
            blockers.append(f"车型样本仅 {total} 人")
        if answered < 10:
            blockers.append(f"本题仅 {answered} 人作答")
        if count < 5:
            blockers.append(f"该行 {count} 人，不足 5 人")
        if blockers:
            payload["ratio_hidden_reason"] = "；".join(blockers) + "，只给人数"
        else:
            payload["ratio"] = round(count / total * 100, 1)
        return payload

    def _compare_rows(
        self, a: dict[str, Any], b: dict[str, Any], metric: str
    ) -> list[dict[str, Any]]:
        counts_a = self.reader.quant_answered_full(a)
        counts_b = self.reader.quant_answered_full(b)
        rows: list[dict[str, Any]] = []

        if metric in {"attention", "win", "abandon"}:
            prefix, answered_key = {
                "attention": (ATTENTION_PREFIX, "Q3_13"),
                "win": (WIN_PREFIX, "Q3_23"),
                "abandon": (ABANDON_PREFIX, "Q3_24_1"),
            }[metric]
            raw_a = self.reader.multi_counts(a, prefix)
            raw_b = self.reader.multi_counts(b, prefix)
            for index, label in DIMENSIONS:
                side_a = self._compare_side(
                    int(raw_a.get(f"c{index}") or 0), int(counts_a["n"]), int(counts_a.get(answered_key) or 0)
                )
                side_b = self._compare_side(
                    int(raw_b.get(f"c{index}") or 0), int(counts_b["n"]), int(counts_b.get(answered_key) or 0)
                )
                rows.append(self._row(f"{prefix}{index}", label, side_a, side_b, unit="pp"))
            return rows

        if metric == "profile":
            for field, segment_label, kind in PROFILE_COMPARE_SEGMENTS:
                dist_a = {row["label"]: int(row["count"]) for row in self.reader.distribution(a, field, kind)}
                dist_b = {row["label"]: int(row["count"]) for row in self.reader.distribution(b, field, kind)}
                labels = sorted(
                    {label for label in (*dist_a, *dist_b) if label and label != "(空)"},
                    key=lambda label: (-max(dist_a.get(label, 0), dist_b.get(label, 0)), label),
                )[:5]
                for label in labels:
                    side_a = self._compare_side(dist_a.get(label, 0), int(counts_a["n"]), int(counts_a["n"]))
                    side_b = self._compare_side(dist_b.get(label, 0), int(counts_b["n"]), int(counts_b["n"]))
                    rows.append(self._row(f"profile.{field}.{label}", f"{segment_label}·{label}", side_a, side_b, unit="pp"))
            return rows

        if metric == "satisfaction":
            stats_a = self.reader.score_stats(a)
            stats_b = self.reader.score_stats(b)
            for index, label in DIMENSIONS:
                answered_a = int(stats_a.get(f"a{index}") or 0)
                answered_b = int(stats_b.get(f"a{index}") or 0)
                mean_a = stats_a.get(f"m{index}")
                mean_b = stats_b.get(f"m{index}")
                side_a = {
                    "mean": round(float(mean_a), 2) if mean_a is not None else None,
                    "answered": answered_a,
                    "n": int(counts_a["n"]),
                }
                side_b = {
                    "mean": round(float(mean_b), 2) if mean_b is not None else None,
                    "answered": answered_b,
                    "n": int(counts_b["n"]),
                }
                delta = None
                if side_a["mean"] is not None and side_b["mean"] is not None:
                    delta = round(side_a["mean"] - side_b["mean"], 2)
                level = "L0" if answered_a >= 10 and answered_b >= 10 and delta is not None else "L1"
                rows.append(
                    {
                        "key": f"{SCORE_PREFIX}{index}",
                        "label": label,
                        "a": side_a,
                        "b": side_b,
                        "delta": delta,
                        "unit": "分",
                        "gap_flag": "insufficient" if delta is None else ("significant" if abs(delta) >= 0.5 else "flat"),
                        "level": level,
                    }
                )
            return rows

        raise AnalysisError("invalid_metric", f"不支持的对比指标：{metric}", 400)

    @staticmethod
    def _row(key: str, label: str, side_a: dict[str, Any], side_b: dict[str, Any], unit: str) -> dict[str, Any]:
        delta = None
        if side_a.get("ratio") is not None and side_b.get("ratio") is not None:
            delta = round(side_a["ratio"] - side_b["ratio"], 1)
        level = "L0" if delta is not None and side_a["count"] >= 5 and side_b["count"] >= 5 else "L1"
        return {
            "key": key,
            "label": label,
            "a": side_a,
            "b": side_b,
            "delta_pp": delta,
            "unit": unit,
            "gap_flag": "insufficient" if delta is None else ("significant" if abs(delta) >= 5 else "flat"),
            "level": level,
        }

    def compare_metric(self, a: dict[str, Any], b: dict[str, Any], metric: str) -> dict[str, Any]:
        rows = self._compare_rows(a, b, metric)
        data = {
            "metric": metric,
            "a": a["label"],
            "b": b["label"],
            "rows": rows,
            "comparable": sum(1 for row in rows if row["level"] == "L0"),
        }
        return self._envelope(
            "bci_compare_metric",
            {"a": a["label"], "b": b["label"], "metric": metric},
            "ok" if rows else "empty",
            data,
            self._caliber(min(int(self.reader.quant_answered_full(a)["n"]), int(self.reader.quant_answered_full(b)["n"])), f"{metric} 双侧同题"),
        )
