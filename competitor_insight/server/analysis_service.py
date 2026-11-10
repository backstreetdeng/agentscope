"""BCI-006 · 竞品洞察「即时分析」取数与口径。

只读四类数据源，输出四个磁贴 + 一条确定性综合结论：

- 用户画像：`user_insight.quant_sample` 结构化字段 + `user_insight.interview/answer` 逐人引语
- 购车关注：`Q3_13__1..16` 多选勾选率
- 战胜战败：`Q3_23__1..16`（选择本车原因）、`Q3_22_1__1/2/3`（三款对比车型自由文本）、
  `Q3_24_1/3/5__1..16`（对应槽位的放弃原因）
- 战败口径：以当前车型为靶心反查对比过它、最终买了别的车的人，按实际购车车型逐行「XX 胜出」；
  原因按靶心所在槽位取 `Q3_24_1`（第 1 格）/`Q3_24_3`（第 2 格）/`Q3_24_5`（第 3 格）。
- 满意度：`Q5_1` 整体、`Q5_2__1..16` 分维度、`Q5_5` 推荐意愿、口碑正负向

口径约定（与 `docs/analysis-tab-feasibility.md` 一致）：
- 比例一律给分子/分母；分母默认是车型定量总样本，同时给出该题实际作答人数。
- 题目作答人数 <10 时不展示比例，只给人数并说明原因。
- 车型集合只从 `config/analysis_models.json` 读取，不在代码里写死车名。
- 算不出来的指标返回 `status="empty"` 与具体原因，不用 0 或近似值代替。
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import psycopg2
import psycopg2.extras

from competitor_insight.server import db, name_rules, tile_summary

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "analysis_models.json"

# 16 个产品维度：题号后缀与显示名，顺序按 Q3_13 的原始序号。
DIMENSIONS: tuple[tuple[int, str], ...] = (
    (1, "安全性"),
    (2, "操控性"),
    (3, "动力性"),
    (4, "舒适性"),
    (5, "空间"),
    (6, "外观"),
    (7, "内饰"),
    (8, "质量"),
    (9, "使用费用"),
    (10, "购车价格"),
    (11, "品牌"),
    (12, "服务"),
    (13, "智能座舱"),
    (14, "智能驾驶"),
    (15, "纯电续航里程"),
    (16, "电池特性（电池安全/品牌/类型）"),
)

ATTENTION_PREFIX = "Q3_13__"
WIN_PREFIX = "Q3_23__"
ABANDON_PREFIX = "Q3_24_1__"
SCORE_PREFIX = "Q5_2__"

# 画像分段：column 是 quant_sample 列，json 是 answers_text 里的题号。
PROFILE_SEGMENTS: tuple[tuple[str, str, str], ...] = (
    ("age_band", "年龄段", "column"),
    ("gender", "性别", "column"),
    ("city", "城市", "column"),
    ("price_band", "购车价格段", "column"),
    ("purchase_type", "购车类型", "column"),
    ("Q9_1", "婚姻状况", "json"),
    ("Q9_8", "职业类型", "json"),
    ("Q9_11", "家庭税后年收入", "json"),
    ("Q2_5", "家庭购车情形", "json"),
)

INTERVIEW_QUESTION = 85
INTERVIEW_QUESTION_LABEL = "车对用户意味着什么（深访原话）"

# 用户 2026-11-07 确认的定性↔定量映射：Q29 ↔ Q3_23，Q27/Q28 ↔ Q3_24_1。
WIN_QUESTIONS = (29,)
ABANDON_QUESTIONS = (27, 28)

# 定性原话按 16 维关键词确定性归类；仅作对照，不替代定量比例。
DIMENSION_KEYWORDS: dict[int, tuple[str, ...]] = {
    1: ("安全", "碰撞", "气囊"),
    2: ("操控", "好开", "驾驶感受", "底盘", "转弯半径", "掉头"),
    3: ("动力", "加速", "四驱", "双电机", "性能"),
    4: ("舒适", "坐着", "座椅", "减震", "悬架", "隔音"),
    5: ("空间", "后排", "后备箱", "储物", "前备箱"),
    6: ("外观", "外形", "造型", "颜值", "方盒子", "设计"),
    7: ("内饰", "用料", "做工", "氛围灯"),
    8: ("质量", "品控", "故障", "可靠", "耐用"),
    9: ("使用成本", "用车成本", "电费", "电耗", "油耗", "保养", "省电"),
    10: ("价格", "性价比", "预算", "优惠", "万元", "贵", "便宜"),
    11: ("品牌", "口碑", "保有量"),
    12: ("服务", "售后", "销售", "4S", "质保", "网点"),
    13: ("座舱", "车机", "屏幕", "语音", "车联网"),
    14: ("智驾", "智能驾驶", "辅助驾驶", "自动驾驶", "领航", "L2", "天神之眼"),
    15: ("续航", "公里", "km", "度电"),
    16: ("电池", "三电", "快充", "800V", "充电"),
}


def tag_dimensions(text: str) -> list[str]:
    """按关键词把一条定性原话归入 16 维；命中多个就返回多个，不强行补全。"""
    normalized = str(text or "")
    hits: list[str] = []
    for index, label in DIMENSIONS:
        if any(keyword.casefold() in normalized.casefold() for keyword in DIMENSION_KEYWORDS.get(index, ())):
            hits.append(label)
    return hits

# 用户 2026-11-10 确认：只有画像、购车关注、战胜战败三块生成 AI 结论，满意度不生成。
TILE_ORDER = ("profile", "attention", "winloss")


class AnalysisError(RuntimeError):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status

    def to_payload(self) -> dict[str, Any]:
        return {"ok": False, "error": {"code": self.code, "message": str(self)}}


def load_config(path: Path | None = None) -> dict[str, Any]:
    config_path = Path(path or CONFIG_PATH)
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AnalysisError("config_missing", f"缺少车型配置：{config_path.name}", 500) from exc
    except ValueError as exc:
        raise AnalysisError("config_invalid", f"车型配置不是合法 JSON：{exc}", 500) from exc

    models = config.get("models")
    if not isinstance(models, list) or not models:
        raise AnalysisError("config_invalid", "车型配置缺少 models", 500)
    keys = [str(item.get("key") or "") for item in models if isinstance(item, dict)]
    if not all(keys) or len(keys) != len(models) or len(set(keys)) != len(keys):
        raise AnalysisError("config_invalid", "车型 key 必须非空且唯一", 500)
    return config


def sample_flag(n: int) -> str:
    if n < 10:
        return "insufficient"
    if n < 30:
        return "small"
    return "ok"


def ratio_payload(count: int, total: int, answered: int | None = None) -> dict[str, Any]:
    """比例统一出口：n<10 不出比例；题目作答 <10 也不出比例。"""
    flag = sample_flag(total)
    payload: dict[str, Any] = {
        "count": int(count),
        "n": int(total),
        "sample_flag": flag,
    }
    if answered is not None:
        payload["answered"] = int(answered)
    if total < 10:
        payload["ratio"] = None
        payload["ratio_hidden_reason"] = f"车型样本仅 {total} 人，低于 10 人展示门槛"
    elif answered is not None and answered < 10:
        payload["ratio"] = None
        payload["ratio_hidden_reason"] = f"本题仅 {answered} 人作答，低于 10 人展示门槛"
    else:
        payload["ratio"] = round(count / total * 100, 1) if total else None
    return payload


def parse_recommendation(value: Any) -> tuple[int, str] | None:
    """Q5_5 是「9十分推荐」这类文本打分，取前置数字作为 1–10 分。"""
    text = str(value or "").strip()
    match = re.match(r"^(\d{1,2})(?:\.\d+)?\s*(.*)$", text)
    if not match:
        return None
    score = int(match.group(1))
    if not 1 <= score <= 10:
        return None
    return score, match.group(2).strip()


def _name_key(value: Any) -> str:
    """车型名归一键：去空白、统一大小写，用于别名与反查匹配。"""
    return re.sub(r"\s+", "", str(value or "")).casefold()


def normalize_competitor(value: str, aliases: dict[str, str]) -> str:
    """对比车型归一到车系标准名：先按别名改写，再去动力/能源后缀。

    去后缀保证「宋PLUS新能源 / 宋PLUS EV」与「宋PLUS」在战胜战败里是同一行（车系整体出数），
    动力形式的拆分由问卷题项另给，不从名称推断。
    """
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return ""
    merged = {_name_key(k): v for k, v in (aliases or {}).items()}
    return name_rules.strip_power_suffix(merged.get(_name_key(text), text))


def display_purchase_type(value: str) -> str:
    text = str(value or "").strip()
    if text.startswith("首购"):
        return "首购"
    if text.startswith("增购"):
        return "增购"
    if text.startswith("换购") and "报废" in text:
        return "换购（报废旧车）"
    if text.startswith("换购"):
        return "换购（卖掉旧车）"
    return text or "(空)"


def _top_with_other(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if limit <= 0 or len(items) <= limit:
        return items
    head, tail = items[:limit], items[limit:]
    n = int(items[0]["n"])
    count = sum(int(item["count"]) for item in tail)
    other = {
        "label": "其他",
        "count": count,
        "n": n,
        "sample_flag": sample_flag(n),
        "ratio": round(count / n * 100, 1) if n >= 10 else None,
    }
    return head + [other]


class PostgresReader:
    """四源只读访问。问卷/深访/配置用 loader，口碑用 NEW_CAR 账号。"""

    def __init__(self, cfg: dict[str, str], power_form: str | None = None) -> None:
        self._cfg = cfg
        self._loader = None
        self._catalog = None
        # 动力形式按受访燃料题项 Q2_2 逐样本取，不用名称推断；None 表示不切分。
        self.power_form = power_form or None
        if self.power_form:
            # 购买侧 Q2_2 只有纯电动/插电混动/增程式三个取值；纯燃油、油电混动没有对应值，
            # 按本类名匹配即 0 行，返回空样本而不是报错。
            prefix = name_rules.SURVEY_POWER_FORM.get(self.power_form, self.power_form)
            self._power_sql = " AND answers_text->>'Q2_2' LIKE %s"
            self._power_params: tuple[Any, ...] = (f"{prefix}%",)
        else:
            self._power_sql = ""
            self._power_params = ()

    def _connect(self, *, catalog: bool = False):
        if catalog:
            if self._catalog is None:
                self._catalog = psycopg2.connect(
                    host=self._cfg.get("NEW_CAR_PG_HOST", ""),
                    port=int(self._cfg.get("NEW_CAR_PG_PORT", "5432")),
                    dbname=self._cfg.get("NEW_CAR_PG_DATABASE", ""),
                    user=self._cfg.get("NEW_CAR_PG_USER", ""),
                    password=self._cfg.get("NEW_CAR_PG_PASSWORD", ""),
                    connect_timeout=10,
                )
                self._catalog.set_session(readonly=True, autocommit=True)
            return self._catalog
        if self._loader is None:
            self._loader = db.connect(self._cfg)
            self._loader.set_session(readonly=True, autocommit=True)
        return self._loader

    def _fetch(self, sql: str, params: Iterable[Any] = (), *, catalog: bool = False) -> list[dict[str, Any]]:
        conn = self._connect(catalog=catalog)
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, tuple(params))
            return [dict(row) for row in cur.fetchall()]

    def close(self) -> None:
        for conn in (self._loader, self._catalog):
            if conn is not None:
                conn.close()
        self._loader = None
        self._catalog = None

    # ------------------------------------------------------------------ 计数

    def source_counts(self, model: dict[str, Any]) -> dict[str, int]:
        quant = self._fetch(
            "SELECT count(*) AS n FROM user_insight.quant_sample "
            f"WHERE purchase_model = ANY(%s){self._power_sql}",
            (model["quant_models"], *self._power_params),
        )
        interview = self._fetch(
            "SELECT count(*) AS n FROM user_insight.interview WHERE vehicle_model = ANY(%s)",
            (model["interview_models"],),
        )
        reputation = self._fetch(
            "SELECT coalesce(sum(mention_count), 0) AS n FROM public.new_car_reputation_summary "
            "WHERE model = ANY(%s)",
            (model["reputation_models"],),
            catalog=True,
        )
        miit = self._fetch(
            "SELECT count(DISTINCT type_name) AS n FROM miit.ods_pz_base_info "
            "WHERE model_name = ANY(%s)",
            (model["miit_models"],),
        )
        return {
            "quant": int(quant[0]["n"] or 0),
            "interview": int(interview[0]["n"] or 0),
            "reputation": int(reputation[0]["n"] or 0),
            "miit": int(miit[0]["n"] or 0),
        }

    def quant_answered(self, model: dict[str, Any]) -> dict[str, int]:
        answer_keys = {
            "q313": [f"{ATTENTION_PREFIX}{i}" for i, _ in DIMENSIONS],
            "q323": [f"{WIN_PREFIX}{i}" for i, _ in DIMENSIONS],
            "q3241": [f"{ABANDON_PREFIX}{i}" for i, _ in DIMENSIONS],
            "q52": [f"{SCORE_PREFIX}{i}" for i, _ in DIMENSIONS],
        }
        select = ", ".join(
            f"count(*) FILTER (WHERE answers_text ?| ARRAY[{', '.join(repr(k) for k in keys)}]::text[]) AS {name}"
            for name, keys in answer_keys.items()
        )
        rows = self._fetch(
            f"SELECT count(*) AS n, {select} FROM user_insight.quant_sample "
            f"WHERE purchase_model = ANY(%s){self._power_sql}",
            (model["quant_models"], *self._power_params),
        )
        row = rows[0] if rows else {}
        return {
            "n": int(row.get("n") or 0),
            "Q3_13": int(row.get("q313") or 0),
            "Q3_23": int(row.get("q323") or 0),
            "Q3_24_1": int(row.get("q3241") or 0),
            "Q5_2": int(row.get("q52") or 0),
            "Q5_1": 0,
            "Q5_5": 0,
        }

    def quant_answered_full(self, model: dict[str, Any]) -> dict[str, int]:
        base = self.quant_answered(model)
        extra = self._fetch(
            "SELECT count(*) FILTER (WHERE answers_text ? 'Q5_1') AS q51, "
            "count(*) FILTER (WHERE answers_text ? 'Q5_5') AS q55 "
            f"FROM user_insight.quant_sample WHERE purchase_model = ANY(%s){self._power_sql}",
            (model["quant_models"], *self._power_params),
        )
        row = extra[0] if extra else {}
        base["Q5_1"] = int(row.get("q51") or 0)
        base["Q5_5"] = int(row.get("q55") or 0)
        return base

    # ------------------------------------------------------------------ 画像

    def distribution(self, model: dict[str, Any], field: str, kind: str) -> list[dict[str, Any]]:
        if kind == "column":
            if field not in {"age_band", "gender", "city", "price_band", "purchase_type"}:
                raise AnalysisError("invalid_field", f"不支持的画像字段：{field}", 500)
            expr = field
        else:
            if not re.fullmatch(r"Q\d+_\d+", field):
                raise AnalysisError("invalid_field", f"不支持的画像题号：{field}", 500)
            expr = f"answers_text->>'{field}'"
        rows = self._fetch(
            f"SELECT {expr} AS value, count(*) AS count FROM user_insight.quant_sample "
            f"WHERE purchase_model = ANY(%s){self._power_sql} GROUP BY 1 ORDER BY count DESC, value",
            (model["quant_models"], *self._power_params),
        )
        items = []
        for row in rows:
            label = row.get("value")
            label = str(label).strip() if label is not None and str(label).strip() else "(空)"
            if field == "purchase_type":
                label = display_purchase_type(label)
            items.append({"label": label, "count": int(row["count"])})
        # purchase_type 归一后可能重名，合并计数。
        if field == "purchase_type":
            merged: dict[str, int] = {}
            for item in items:
                merged[item["label"]] = merged.get(item["label"], 0) + item["count"]
            items = [{"label": key, "count": value} for key, value in merged.items()]
            items.sort(key=lambda item: -item["count"])
        return items

    def budget_values(self, model: dict[str, Any]) -> list[float]:
        rows = self._fetch(
            "SELECT answers_text->>'Q3_1' AS value FROM user_insight.quant_sample "
            f"WHERE purchase_model = ANY(%s) AND answers_text ? 'Q3_1'{self._power_sql}",
            (model["quant_models"], *self._power_params),
        )
        values: list[float] = []
        for row in rows:
            try:
                values.append(float(str(row.get("value") or "").strip()))
            except ValueError:
                continue
        return values

    def interview_quotes(self, model: dict[str, Any], question_id: int) -> list[dict[str, Any]]:
        return self._fetch(
            "SELECT i.interview_id, coalesce(i.respondent_code, i.interview_id) AS respondent_code, "
            "i.city, i.purchase_type, a.question_text, a.answer_text "
            "FROM user_insight.interview i "
            "LEFT JOIN user_insight.answer a ON a.interview_id = i.interview_id AND a.question_id = %s "
            "WHERE i.vehicle_model = ANY(%s) ORDER BY i.interview_id",
            (question_id, model["interview_models"]),
        )

    def interview_reason_answers(
        self, model: dict[str, Any], question_ids: tuple[int, ...]
    ) -> list[dict[str, Any]]:
        return self._fetch(
            "SELECT i.interview_id, coalesce(i.respondent_code, i.interview_id) AS respondent_code, "
            "a.question_id, a.question_text, a.answer_text "
            "FROM user_insight.answer a JOIN user_insight.interview i USING (interview_id) "
            "WHERE i.vehicle_model = ANY(%s) AND a.question_id = ANY(%s) "
            "AND length(trim(coalesce(a.answer_text, ''))) > 5 "
            "ORDER BY i.interview_id, a.question_id",
            (model["interview_models"], list(question_ids)),
        )

    # -------------------------------------------------------------- 多选维度

    def multi_counts(self, model: dict[str, Any], prefix: str) -> dict[str, Any]:
        keys = [f"{prefix}{index}" for index, _ in DIMENSIONS]
        select = ", ".join(
            f"count(*) FILTER (WHERE answers_text ? '{key}') AS c{index}"
            for (index, _), key in zip(DIMENSIONS, keys)
        )
        rows = self._fetch(
            f"SELECT count(*) FILTER (WHERE answers_text ?| ARRAY[{', '.join(repr(k) for k in keys)}]::text[]) AS answered, "
            f"{select} FROM user_insight.quant_sample WHERE purchase_model = ANY(%s){self._power_sql}",
            (model["quant_models"], *self._power_params),
        )
        return rows[0] if rows else {"answered": 0}

    # -------------------------------------------------------------- 满意度

    def score_stats(self, model: dict[str, Any]) -> dict[str, Any]:
        blocks = []
        for index, _ in DIMENSIONS:
            key = f"{SCORE_PREFIX}{index}"
            blocks.append(
                f"count(*) FILTER (WHERE answers_text->>'{key}' ~ '^[0-9]+$') AS a{index}, "
                f"avg(CASE WHEN answers_text->>'{key}' ~ '^[0-9]+$' "
                f"THEN (answers_text->>'{key}')::numeric END) AS m{index}, "
                f"count(*) FILTER (WHERE answers_text->>'{key}' ~ '^[0-9]+$' "
                f"AND (answers_text->>'{key}')::numeric <= 6) AS l{index}"
            )
        rows = self._fetch(
            "SELECT " + ", ".join(blocks) + " FROM user_insight.quant_sample "
            f"WHERE purchase_model = ANY(%s){self._power_sql}",
            (model["quant_models"], *self._power_params),
        )
        return rows[0] if rows else {}

    def overall_score(self, model: dict[str, Any]) -> dict[str, Any]:
        rows = self._fetch(
            "SELECT avg(CASE WHEN answers_text->>'Q5_1' ~ '^[0-9]+$' "
            "THEN (answers_text->>'Q5_1')::numeric END) AS mean, "
            "count(*) FILTER (WHERE answers_text->>'Q5_1' ~ '^[0-9]+$') AS answered "
            f"FROM user_insight.quant_sample WHERE purchase_model = ANY(%s){self._power_sql}",
            (model["quant_models"], *self._power_params),
        )
        return rows[0] if rows else {}

    def recommendation_values(self, model: dict[str, Any]) -> list[str]:
        rows = self._fetch(
            "SELECT answers_text->>'Q5_5' AS value FROM user_insight.quant_sample "
            f"WHERE purchase_model = ANY(%s) AND answers_text ? 'Q5_5'{self._power_sql}",
            (model["quant_models"], *self._power_params),
        )
        return [str(row.get("value") or "") for row in rows]

    # -------------------------------------------------------------- 对比车型

    def loss_rows(self, model: dict[str, Any]) -> list[dict[str, Any]]:
        """全量反查行：实际购车车型 + 三格对比车型 + 三套 16 维放弃原因勾选。

        反查不按当前车型过滤，靶心由服务层用别名归一做等值匹配；
        原因按槽位取：第 1 格 Q3_24_1、第 2 格 Q3_24_3、第 3 格 Q3_24_5。
        """
        compare_keys = ("Q3_22_1__1", "Q3_22_1__2", "Q3_22_1__3")
        fuel_keys = ("Q3_22_2_1", "Q3_22_2_2", "Q3_22_2_3")
        reason_prefixes = ("Q3_24_1__", "Q3_24_3__", "Q3_24_5__")
        select = ["purchase_model"]
        # 「无」是问卷里的没填占位，业务 2026-11-10 定稿按空值处理：不参与分组、不产生未匹配。
        select += [
            f"CASE WHEN btrim(coalesce(answers_text->>'{key}', '')) IN ('', '无') THEN NULL "
            f"ELSE answers_text->>'{key}' END AS c{index}"
            for index, key in enumerate(compare_keys)
        ]
        # 三格对比车型各自的燃料类型（矩单），与分析同槽位配对，用于动力构成，不从名称推断。
        select += [
            f"answers_text->>'{key}' AS f{index}" for index, key in enumerate(fuel_keys)
        ]
        for slot, prefix in enumerate(reason_prefixes):
            select += [
                f"answers_text ? '{prefix}{index}' AS r{slot}_{index}"
                for index, _ in DIMENSIONS
            ]
        return self._fetch(
            "SELECT " + ", ".join(select) + f" FROM user_insight.quant_sample WHERE TRUE{self._power_sql}",
            self._power_params,
        )

    def power_breakdown(self, model: dict[str, Any]) -> dict[str, int]:
        """靶心动力构成：按 Q2_2 受访燃料类型逐样本统计，覆盖 1380/1380。"""
        rows = self._fetch(
            "SELECT answers_text->>'Q2_2' AS value, count(*) AS n FROM user_insight.quant_sample "
            f"WHERE purchase_model = ANY(%s){self._power_sql} GROUP BY 1",
            (model["quant_models"], *self._power_params),
        )
        bucket = {form: 0 for form in name_rules.POWER_FORMS}
        bucket[name_rules.UNLABELED] = 0
        for row in rows:
            form = name_rules.normalize_power_form(row.get("value")) or name_rules.UNLABELED
            bucket[form] += int(row["n"])
        return bucket

    def reputation(self, model: dict[str, Any]) -> list[dict[str, Any]]:
        return self._fetch(
            "SELECT direction, primary_label, mention_count "
            "FROM public.new_car_reputation_summary WHERE model = ANY(%s) "
            "ORDER BY direction, mention_count DESC",
            (model["reputation_models"],),
            catalog=True,
        )


class AnalysisService:
    """对外只暴露 models() 与 analyze()；取数全部只读。"""

    def __init__(self, reader_factory=None, config_path: Path | None = None) -> None:
        self._config_path = Path(config_path or CONFIG_PATH)
        self._reader_factory = reader_factory

    def config(self) -> dict[str, Any]:
        return load_config(self._config_path)

    def _reader(self, power_form: str | None = None):
        if self._reader_factory is not None:
            return self._reader_factory()
        return PostgresReader(db.load_env(), power_form)

    # ------------------------------------------------------------------ 车型

    def models(self) -> dict[str, Any]:
        config = self.config()
        reader = self._reader()
        try:
            items = []
            for model in config["models"]:
                sources = reader.source_counts(model)
                items.append(self._model_brief(model, sources))
        except AnalysisError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise AnalysisError("database_unavailable", f"车型数据源查询失败：{exc.__class__.__name__}", 503) from exc
        finally:
            reader.close()
        return {
            "version": config.get("version", 1),
            "updated": config.get("updated", ""),
            "default_model": config.get("default_model") or items[0]["key"],
            "models": items,
        }

    @staticmethod
    def _model_brief(model: dict[str, Any], sources: dict[str, int]) -> dict[str, Any]:
        missing = [label for key, label in (
            ("quant", "定量"), ("interview", "深访"), ("reputation", "口碑"), ("miit", "配置"),
        ) if not sources.get(key)]
        return {
            "key": model["key"],
            "label": model["label"],
            "price_note": model.get("price_note", ""),
            "body_note": model.get("body_note", ""),
            "sources": sources,
            "missing_sources": missing,
            "available": not missing,
        }

    def _model(self, key: str) -> dict[str, Any]:
        config = self.config()
        models = config["models"]
        if not key:
            key = config.get("default_model") or models[0]["key"]
        for model in models:
            if model["key"] == key or model["label"] == key:
                return model
        raise AnalysisError("model_not_found", f"车型不在配置清单中：{key}", 404)

    # ------------------------------------------------------------------ 分析

    def analyze(self, model_key: str, power_form: str | None = None) -> dict[str, Any]:
        """即时分析。`power_form` 可选：不传＝车系整体；传五类之一只算该动力形式的样本。

        五类为 纯电 / 插混 / 增程 / 纯燃油 / 油电混动（`name_rules.POWER_FORMS`）。
        切分依据是问卷题项 Q2_2「受访燃料类型」（逐样本有值，覆盖 1380/1380），
        不从车名推断；购买侧没有纯燃油/油电混动取值，传这两类时定量样本为 0。
        前端暂不接入，仅后端能力。
        """
        config = self.config()
        model = self._model(model_key)
        selected = None
        if str(power_form or "").strip():
            selected = name_rules.normalize_power_form(power_form)
            if not selected:
                raise AnalysisError(
                    "invalid_power_form",
                    f"power_form 只支持 {' / '.join(name_rules.POWER_FORMS)}，收到：{power_form}",
                    400,
                )
        reader = self._reader(selected)
        try:
            sources = reader.source_counts(model)
            counts = reader.quant_answered_full(model)
            fuel_breakdown = reader.power_breakdown(model)
            tiles = {
                "profile": self._profile(reader, model, counts, sources),
                "attention": self._attention(reader, model, counts),
                "winloss": self._winloss(reader, model, counts, config),
                "satisfaction": self._satisfaction(reader, model, counts, sources),
            }
        except AnalysisError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise AnalysisError("database_unavailable", f"即时分析取数失败：{exc.__class__.__name__}", 503) from exc
        finally:
            reader.close()

        summary = self._summary(model, sources, tiles)
        return {
            "model": self._model_brief(model, sources),
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "power_form": selected,
            "power_form_source": "Q2_2 受访燃料类型（逐样本）",
            "power_forms": fuel_breakdown,
            "sources": sources,
            "tiles": tiles,
            "summary": summary,
        }

    def summaries(self, model_key: str, llm=None) -> dict[str, Any]:
        """三个磁贴底部的块内 AI 结论（画像 / 关注 / 战胜战败，满意度不生成）。

        只吃各磁贴已经算出的数字与深访原话（不重新查库、不跨磁贴取数），
        按「车型 key + 磁贴 + 提示词哈希 + 本块数据哈希」缓存；
        模型失败时返回 error，由页面如实展示，不用模板句顶替。
        """
        data = self.analyze(model_key)
        label = data["model"]["label"]
        key = data["model"]["key"]
        tiles = {
            name: tile_summary.summarize_tile(
                name, data["tiles"].get(name) or {}, label, key, llm=llm
            )
            for name in TILE_ORDER
        }
        return {
            "model": data["model"],
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "prompt_version": tile_summary.PROMPT_VERSION,
            "tiles": tiles,
        }

    # ------------------------------------------------------------------ 磁贴①

    def _profile(self, reader, model, counts, sources) -> dict[str, Any]:
        total = counts["n"]
        metrics: list[dict[str, Any]] = []
        if total:
            for field, label, kind in PROFILE_SEGMENTS:
                rows = reader.distribution(model, field, kind)
                items = [ratio_payload(item["count"], total) | {"label": item["label"]} for item in rows]
                metrics.append({
                    "key": field,
                    "label": label,
                    "kind": "distribution",
                    "status": "ok",
                    "n": total,
                    "answered": total,
                    "sample_flag": sample_flag(total),
                    "items": _top_with_other(items, 8) if field in {"city", "Q9_8"} else items,
                })

            budget = reader.budget_values(model)
            if budget:
                buckets = [
                    ("10 万以下", sum(1 for value in budget if value < 10)),
                    ("10–15 万", sum(1 for value in budget if 10 <= value < 15)),
                    ("15–20 万", sum(1 for value in budget if 15 <= value < 20)),
                    ("20 万及以上", sum(1 for value in budget if value >= 20)),
                ]
                ordered = sorted(budget)
                median = ordered[len(ordered) // 2] if len(ordered) % 2 else (
                    ordered[len(ordered) // 2 - 1] + ordered[len(ordered) // 2]
                ) / 2
                metrics.append({
                    "key": "Q3_1",
                    "label": "购车预算",
                    "kind": "numeric",
                    "status": "ok",
                    "n": total,
                    "answered": len(budget),
                    "sample_flag": sample_flag(total),
                    "median": round(median, 1),
                    "items": [ratio_payload(count, total, len(budget)) | {"label": label} for label, count in buckets],
                    "note": "Q3_1 为预算数值（万元），按区间汇总；中位数基于实际作答值。",
                })

        quotes = reader.interview_quotes(model, INTERVIEW_QUESTION)
        answered_quotes = [row for row in quotes if str(row.get("answer_text") or "").strip()]
        interview_metric = {
            "key": "interview",
            "label": INTERVIEW_QUESTION_LABEL,
            "kind": "qualitative",
            "people": len(quotes),
            "answered": len(answered_quotes),
            "question_id": f"Q{INTERVIEW_QUESTION}",
            "items": [
                {
                    "interview_id": row["interview_id"],
                    "respondent_code": row.get("respondent_code") or row["interview_id"],
                    "city": row.get("city") or "",
                    "purchase_type": row.get("purchase_type") or "",
                    "quote": str(row.get("answer_text") or "").strip()[:240],
                }
                for row in answered_quotes
            ],
            "note": f"深访 {len(quotes)} 人，逐人原话，不做比例，不能外推为群体结论。",
        }
        if not answered_quotes:
            interview_metric["status"] = "empty"
            interview_metric["reason"] = f"深访库中该车型 {len(quotes)} 人，Q{INTERVIEW_QUESTION} 无有效作答。"
        else:
            interview_metric["status"] = "ok"

        status = "ok" if total else "empty"
        reason = "" if total else "该车型在定量库中没有样本，画像无法计算。"
        return {
            "key": "profile",
            "title": "用户画像",
            "subtitle": "结构化问卷 + 深访逐人引语；比例分母为车型定量总样本",
            "status": status,
            "reason": reason,
            "n": total,
            "sources": sources,
            "metrics": metrics + [interview_metric],
        }

    # ------------------------------------------------------------------ 磁贴②

    def _attention(self, reader, model, counts) -> dict[str, Any]:
        total = counts["n"]
        answered = counts["Q3_13"]
        raw = reader.multi_counts(model, ATTENTION_PREFIX)
        items = [
            ratio_payload(int(raw.get(f"c{index}") or 0), total, answered) | {
                "key": f"{ATTENTION_PREFIX}{index}",
                "label": label,
            }
            for index, label in DIMENSIONS
        ]
        items.sort(key=lambda item: (-item["count"], item["label"]))
        ranked = [item for item in items if item["count"] > 0]
        metric = {
            "key": "attention",
            "label": "购车关注（16 维多选勾选率）",
            "question": "Q3_13__1..16",
            "kind": "distribution",
            "n": total,
            "answered": answered,
            "answer_rate": round(answered / total * 100, 1) if total else 0,
            "sample_flag": sample_flag(total),
            "items": items,
            "top": ranked[:5],
        }
        if not total:
            metric["status"] = "empty"
            metric["reason"] = "该车型在定量库中没有样本。"
        elif answered < 10:
            metric["status"] = "insufficient"
            metric["reason"] = f"本题仅 {answered} 人作答，低于 10 人展示门槛，不展示比例。"
        else:
            metric["status"] = "ok"
            metric["note"] = (
                f"多选勾选题，可多选，不等同于第一关注；本题实际作答 {answered}/{total}。"
                "分母为车型定量总样本，未作答者不计入分子但计入分母（沿用 quant_service 口径）。"
            )

        first_ranking = {
            "key": "first_ranking",
            "label": "产品 / 品牌 / 服务 第一排序",
            "kind": "empty",
            "status": "empty",
            "reason": (
                "库内无排序题：quant_question 检索「排序」0 条；Q3_13 为多选勾选，"
                "答案不含第一顺位权重，无法计算三类第一排序占比。"
            ),
        }
        status = "partial" if metric["status"] == "ok" else metric["status"]
        return {
            "key": "attention",
            "title": "购车关注",
            "subtitle": "关注什么；多选勾选率，非排序",
            "status": status,
            "n": total,
            "metrics": [metric, first_ranking],
        }

    # ------------------------------------------------------------------ 磁贴③

    def _qualitative(
        self,
        reader,
        model,
        question_ids: tuple[int, ...],
        label: str,
        scope_note: str,
    ) -> dict[str, Any]:
        """深访原话按 16 维关键词归类；未命中的原话单独列出，不硬套。"""
        rows = reader.interview_reason_answers(model, question_ids)
        items: list[dict[str, Any]] = []
        unmatched: list[dict[str, Any]] = []
        people: set[str] = set()
        dimension_ids: dict[str, set[str]] = {name: set() for _, name in DIMENSIONS}
        for row in rows:
            text = str(row.get("answer_text") or "").strip()
            tags = tag_dimensions(text)
            item = {
                "interview_id": row["interview_id"],
                "respondent_code": row.get("respondent_code") or row["interview_id"],
                "question_id": f"Q{row['question_id']}",
                "dimensions": tags,
                "quote": text[:300],
            }
            people.add(str(row["interview_id"]))
            items.append(item)
            if tags:
                for tag in tags:
                    dimension_ids[tag].add(str(row["interview_id"]))
            else:
                unmatched.append(item)
        metric: dict[str, Any] = {
            "key": f"{scope_note}_quotes",
            "label": label,
            "kind": "qualitative",
            "question_ids": [f"Q{qid}" for qid in question_ids],
            "people": len(people),
            "answered": len(items),
            "sample_flag": sample_flag(len(people)),
            "items": items,
            "unmatched": unmatched,
            "dimension_people": [
                {
                    "label": name,
                    "people": len(dimension_ids[name]),
                    "interview_ids": sorted(dimension_ids[name]),
                }
                for _, name in DIMENSIONS
                if dimension_ids[name]
            ],
            "note": (
                f"深访 {len(people)} 人，逐人原话，不做比例；按维度关键词自动归类，"
                "一条原话可命中多个维度。未命中任何维度的原话单独列在下方，不强行匹配。"
            ),
        }
        if not items:
            metric["status"] = "empty"
            metric["reason"] = f"该车型在深访库中 {'/'.join(metric['question_ids'])} 无有效作答。"
        elif len(people) < 3:
            metric["status"] = "insufficient"
            metric["reason"] = f"仅 {len(people)} 人作答，只能作为个体原话，不能当作群体结论。"
        else:
            metric["status"] = "ok"
        return metric

    def _reason_metric(
        self,
        reader,
        model,
        total: int,
        answered: int,
        prefix: str,
        label: str,
        qualitative: dict[str, Any],
        *,
        extra_note: str = "",
    ) -> dict[str, Any]:
        raw = reader.multi_counts(model, prefix)
        qual_map = {entry["label"]: entry for entry in qualitative.get("dimension_people", [])}
        items = []
        for index, name in DIMENSIONS:
            payload = ratio_payload(int(raw.get(f"c{index}") or 0), total, answered) | {
                "key": f"{prefix}{index}",
                "label": name,
                "qual_people": int(qual_map.get(name, {}).get("people") or 0),
                "qual_interview_ids": qual_map.get(name, {}).get("interview_ids", []),
            }
            items.append(payload)
        ranked = sorted(
            [item for item in items if item["count"] > 0],
            key=lambda item: (-item["count"], item["label"]),
        )
        metric = {
            "key": prefix.rstrip("_").lower(),
            "label": label,
            "question": f"{prefix}1..16",
            "kind": "distribution",
            "n": total,
            "answered": answered,
            "answer_rate": round(answered / total * 100, 1) if total else 0,
            "sample_flag": sample_flag(total),
            "items": items,
            "top": ranked[:5],
        }
        if not total:
            metric["status"] = "empty"
            metric["reason"] = "该车型在定量库中没有样本。"
        elif answered < 10:
            metric["status"] = "insufficient"
            metric["reason"] = f"本题仅 {answered} 人作答，低于 10 人展示门槛，不展示比例。"
        else:
            metric["status"] = "ok"
        notes = [f"本题实际作答 {answered}/{total}；分母为车型定量总样本。"]
        if extra_note:
            notes.append(extra_note)
        metric["note"] = "".join(notes)
        return metric

    def _loss_split(self, reader, model, config) -> dict[str, Any]:
        """战败：以当前车型为靶心反查对比过它的人，按实际购车车型逐行「XX 胜出」。

        口径（用户 2026-11-10 确认）：
        - 靶心 = 当前目标车型；Q3_22_1__1/2/3 任一列归一后等于靶心即「对比过」。
        - 按 purchase_model 分组，不设人数门槛、不合并「其他」、不删行。
        - 原因按槽位取：靶心在第 1 格用 Q3_24_1、第 2 格用 Q3_24_3、第 3 格用 Q3_24_5。
        - 买了靶心自己的人不算战败。
        """
        alias_map = config.get("competitor_aliases") or {}
        target = model["label"]
        target_key = _name_key(normalize_competitor(target, alias_map))

        groups: dict[str, dict[str, Any]] = {}
        compared = 0
        for row in reader.loss_rows(model):
            bought = normalize_competitor(row.get("purchase_model") or "", alias_map)
            if _name_key(bought) == target_key:
                continue
            slot = next(
                (
                    index for index in range(3)
                    if _name_key(normalize_competitor(row.get(f"c{index}") or "", alias_map)) == target_key
                ),
                None,
            )
            if slot is None:
                continue
            compared += 1
            group = groups.setdefault(
                _name_key(bought),
                {"label": bought or "(未填写)", "count": 0, "dims": {}, "fuels": Counter()},
            )
            group["count"] += 1
            # 动力构成取同槽位的 Q3_22_2 矩单，不按车名推断。
            fuel = name_rules.normalize_power_form(row.get(f"f{slot}")) or name_rules.UNLABELED
            group["fuels"][fuel] += 1
            for index, name in DIMENSIONS:
                if row.get(f"r{slot}_{index}"):
                    group["dims"][name] = group["dims"].get(name, 0) + 1

        def ratio_of(count: int) -> dict[str, Any]:
            if count >= 5 and compared >= 10:
                return {"ratio": round(count / compared * 100, 1)}
            # 两条门槛分开写，只输出真实命中的原因，避免「总数 35 人不足 10 人」这类自相矛盾的提示。
            blockers = []
            if compared < 10:
                blockers.append(f"对比总数 {compared} 人，不足 10 人")
            if count < 5:
                blockers.append(f"该行 {count} 人，不足 5 人")
            return {
                "ratio": None,
                "ratio_hidden_reason": "；".join(blockers) + "，只给人数",
            }

        items = []
        for group in sorted(groups.values(), key=lambda item: (-item["count"], item["label"])):
            count = group["count"]
            reasons = [
                {"label": name, "count": hits, "n": count, **ratio_of(hits)}
                for name, hits in sorted(group["dims"].items(), key=lambda pair: (-pair[1], pair[0]))[:3]
            ]
            items.append(
                {
                    "label": group["label"],
                    "count": count,
                    "n": compared,
                    "sample_flag": sample_flag(compared),
                    "power_forms": {
                        form: group["fuels"].get(form, 0)
                        for form in (*name_rules.POWER_FORMS, name_rules.UNLABELED)
                    },
                    "reasons": reasons,
                    **ratio_of(count),
                }
            )

        metric = {
            "key": "loss_split",
            "label": f"战败：对比过{target}后买了别的车",
            "kind": "loss_split",
            "target": target,
            "question": "Q3_22_1__1/2/3 × Q3_24_1/3/5",
            "basis": (
                "靶心落在 Q3_22_1__1 → 取 Q3_24_1__1..16；落在 __2 → 取 Q3_24_3__1..16；"
                "落在 __3 → 取 Q3_24_5__1..16"
            ),
            "n": compared,
            "answered": compared,
            "sample_flag": sample_flag(compared),
            "items": items,
            "note": (
                f"共 {compared} 人在 Q3_22_1 三格里对比过{target}、最终买了别的车；"
                "行内人数为真实人数，不设门槛、不合并「其他」；行内百分比分母为对比过总人数，"
                "该行不足 5 人或总数不足 10 人时只给人数。"
            ),
        }
        if not compared:
            metric["status"] = "empty"
            metric["reason"] = f"定量库中没有对比过{target}且买了别的车的样本。"
        elif compared < 10:
            metric["status"] = "insufficient"
            metric["reason"] = f"仅 {compared} 人对比过{target}，行内只给人数，不出百分比。"
        else:
            metric["status"] = "ok"
        return metric

    def _winloss(self, reader, model, counts, config) -> dict[str, Any]:
        total = counts["n"]

        win_quotes = self._qualitative(
            reader, model, WIN_QUESTIONS, "深访原话：选择当前车辆的原因（Q29）", "win"
        )
        abandon_quotes = self._qualitative(
            reader, model, ABANDON_QUESTIONS, "深访原话：放弃核心对比车型的原因（Q27/Q28）", "abandon"
        )
        win = self._reason_metric(
            reader, model, total, counts["Q3_23"], WIN_PREFIX,
            "选择当前车辆的原因（Q3_23）", win_quotes,
            extra_note="与深访 Q29 使用同一套 16 维标签。",
        )
        loss = self._loss_split(reader, model, config)

        return {
            "key": "winloss",
            "title": "战胜战败原因洞察",
            "subtitle": "战胜战败：选择当前车辆的原因（Q3_23）/ 对比过当前车辆后实际买了哪款车（Q3_22 反查 + Q3_24 槽位取因）",
            "status": "partial",
            "n": total,
            "banner": (
                f"战败＝在 Q3_22_1 三格里对比过{model['label']}、最终买了别的车的人，"
                "按实际购车车型分行，行标题为「XX 胜出」；战胜（Q3_23）与战败原因是两套题项，不混算。"
            ),
            "metrics": [win, win_quotes, loss, abandon_quotes],
        }

    # ------------------------------------------------------------------ 磁贴④

    def _satisfaction(self, reader, model, counts, sources) -> dict[str, Any]:
        total = counts["n"]
        raw = reader.score_stats(model)
        items = []
        for index, label in DIMENSIONS:
            answered = int(raw.get(f"a{index}") or 0)
            mean = raw.get(f"m{index}")
            low = int(raw.get(f"l{index}") or 0)
            item = {
                "key": f"{SCORE_PREFIX}{index}",
                "label": label,
                "n": total,
                "answered": answered,
                "mean": round(float(mean), 2) if mean is not None else None,
                "low_count": low,
                "sample_flag": sample_flag(answered),
            }
            if mean is None:
                item["status"] = "empty"
                item["reason"] = "本维度无有效打分。"
            elif answered < 10:
                item["status"] = "insufficient"
                item["low_rate"] = None
                item["reason"] = f"本维度仅 {answered} 人打分，低于 10 人展示门槛。"
            else:
                item["status"] = "ok"
                item["low_rate"] = round(low / answered * 100, 1)
            items.append(item)

        ranked = [item for item in items if item["mean"] is not None]
        best = sorted(ranked, key=lambda item: (-item["mean"], item["label"]))[:5]
        worst = sorted(ranked, key=lambda item: (item["mean"], item["label"]))[:5]

        overall_raw = reader.overall_score(model)
        overall_answered = int(overall_raw.get("answered") or 0)
        overall_mean = overall_raw.get("mean")
        overall = {
            "key": "overall",
            "label": "整体使用满意度（Q5_1，2–10 分）",
            "kind": "score",
            "n": total,
            "answered": overall_answered,
            "mean": round(float(overall_mean), 2) if overall_mean is not None else None,
            "sample_flag": sample_flag(overall_answered),
            "status": "ok" if overall_answered else "empty",
        }
        if not overall_answered:
            overall["reason"] = "Q5_1 无有效打分。"

        rec_values = [parse_recommendation(value) for value in reader.recommendation_values(model)]
        rec_values = [value for value in rec_values if value]
        rec_answered = len(rec_values)
        rec_buckets = [
            ("9–10 分 十分推荐", sum(1 for score, _ in rec_values if score >= 9)),
            ("7–8 分 比较推荐", sum(1 for score, _ in rec_values if 7 <= score <= 8)),
            ("5–6 分 说不好", sum(1 for score, _ in rec_values if 5 <= score <= 6)),
            ("4 分及以下 不推荐", sum(1 for score, _ in rec_values if score <= 4)),
        ]
        recommendation = {
            "key": "recommendation",
            "label": "推荐意愿（Q5_5，1–10 分）",
            "kind": "score",
            "n": total,
            "answered": rec_answered,
            "mean": round(sum(score for score, _ in rec_values) / rec_answered, 2) if rec_answered else None,
            "sample_flag": sample_flag(rec_answered),
            "items": [ratio_payload(count, total, rec_answered) | {"label": label} for label, count in rec_buckets],
            "note": "Q5_5 原值为「9十分推荐」这类文本，按前置数字折算 1–10 分。",
        }
        if rec_answered:
            recommendation["status"] = "ok"
        else:
            recommendation["status"] = "empty"
            recommendation["reason"] = "Q5_5 在该车型无有效作答。"

        reputation_rows = reader.reputation(model)
        positive = [row for row in reputation_rows if row.get("direction") == "positive"]
        negative = [row for row in reputation_rows if row.get("direction") == "negative"]
        reputation = {
            "key": "reputation",
            "label": "外部口碑正/负向标签",
            "kind": "reputation",
            "positive": [
                {"label": row["primary_label"], "count": int(row["mention_count"] or 0)}
                for row in positive[:5]
            ],
            "negative": [
                {"label": row["primary_label"], "count": int(row["mention_count"] or 0)}
                for row in negative[:5]
            ],
            "positive_total": sum(int(row["mention_count"] or 0) for row in positive),
            "negative_total": sum(int(row["mention_count"] or 0) for row in negative),
            "note": "外部评论标签，与问卷满意度不同源，不合并成单一分数。",
        }
        if reputation_rows:
            reputation["status"] = "ok"
        else:
            reputation["status"] = "empty"
            reputation["reason"] = "该车型在口碑表无记录。"

        dims = {
            "key": "dimensions",
            "label": "16 维使用满意度（Q5_2，1–10 分）",
            "kind": "score_list",
            "n": total,
            "answered": counts["Q5_2"],
            "items": items,
            "top": best,
            "bottom": worst,
            "status": "ok" if any(item["mean"] is not None for item in items) else "empty",
        }
        if dims["status"] == "empty":
            dims["reason"] = "Q5_2 在該车型无有效打分。"

        status = "ok" if dims["status"] == "ok" else "empty"
        if status == "ok" and (recommendation["status"] != "ok" or reputation["status"] != "ok"):
            status = "partial"
        return {
            "key": "satisfaction",
            "title": "产品满意度评价",
            "subtitle": "使用后打分 + 推荐意愿 + 外部口碑；分数均附样本数",
            "status": status,
            "n": total,
            "sources": sources,
            "metrics": [overall, dims, recommendation, reputation],
        }

    # ------------------------------------------------------------------ 结论

    def _summary(self, model, sources, tiles) -> list[str]:
        label = model["label"]
        bullets: list[str] = [
            f"{label}：定量样本 {sources['quant']} 人，深访 {sources['interview']} 人，"
            f"口碑提及 {sources['reputation']} 条，配置 {sources['miit']} 个款型。"
        ]
        profile = tiles["profile"]
        if profile["metrics"]:
            parts = []
            for metric in profile["metrics"][:3]:
                if metric["kind"] == "distribution" and metric["items"]:
                    top = metric["items"][0]
                    parts.append(f"{metric['label']}以「{top['label']}」为主（{top['count']}/{metric['n']}）")
            if parts:
                bullets.append("画像：" + "；".join(parts) + "。")

        attention = tiles["attention"]["metrics"][0]
        if attention["status"] == "ok" and attention.get("top"):
            parts = [f"{item['label']} {item['count']}/{item['n']}（{item['ratio']}%）" for item in attention["top"][:3]]
            bullets.append("购车关注 TOP3：" + "、".join(parts) + f"；本题实际作答 {attention['answered']}/{attention['n']}。")
        elif attention["status"] == "insufficient":
            bullets.append(f"购车关注：本题仅 {attention['answered']} 人作答，低于展示门槛，只给人数不计算比例。")

        win = tiles["winloss"]["metrics"][0]
        if win["status"] == "ok" and win.get("top"):
            parts = [f"{item['label']} {item['count']}/{item['n']}（{item['ratio']}%）" for item in win["top"][:3]]
            bullets.append(
                "选择当前车辆的原因 TOP3：" + "、".join(parts)
                + f"；本题实际作答 {win['answered']}/{win['n']}。"
            )
        elif win["status"] == "insufficient":
            bullets.append(f"选择当前车辆的原因：本题仅 {win['answered']} 人作答，低于展示门槛，只给人数不计算比例。")

        win_quotes = next((m for m in tiles["winloss"]["metrics"] if m["key"] == "win_quotes"), None)
        abandon_quotes = next((m for m in tiles["winloss"]["metrics"] if m["key"] == "abandon_quotes"), None)
        if win_quotes and win_quotes["status"] != "empty":
            bullets.append(
                f"深访定性：Q29 选择原因 {win_quotes['people']} 人、"
                f"Q27/Q28 放弃原因 {abandon_quotes['people'] if abandon_quotes else 0} 人；"
                "逐人原话，不做比例。"
            )

        loss = next((m for m in tiles["winloss"]["metrics"] if m["key"] == "loss_split"), None)
        if loss and loss["status"] != "empty" and loss.get("items"):
            top = loss["items"][0]
            ratio = f"（{top['ratio']}%）" if top.get("ratio") is not None else ""
            bullets.append(
                f"战败：{loss['n']} 人对比过{loss['target']}后买了别的车；"
                f"{top['label']} 胜出 {top['count']} 人{ratio}，共分 {len(loss['items'])} 行列出。"
            )

        satisfaction = tiles["satisfaction"]["metrics"]
        overall, dims, recommendation = satisfaction[0], satisfaction[1], satisfaction[2]
        if overall.get("mean") is not None:
            text = f"整体满意度 {overall['mean']} 分（{overall['answered']}/{overall['n']}）"
            if dims["status"] == "ok" and dims.get("top") and dims.get("bottom"):
                best, worst = dims["top"][0], dims["bottom"][0]
                text += (
                    f"；最高维度 {best['label']} {best['mean']} 分（n={best['answered']}），"
                    f"最低维度 {worst['label']} {worst['mean']} 分（n={worst['answered']}）"
                )
            if recommendation["status"] == "ok":
                text += f"；推荐意愿均分 {recommendation['mean']} 分（n={recommendation['answered']}）"
            bullets.append(text + "。")
        return bullets
