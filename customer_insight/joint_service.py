"""联合洞察服务：组合定性证据 + 战胜战败 + 定量统计，输出配置建议。"""
from __future__ import annotations

from typing import Any

from customer_insight.quant_service import QuantStatService
from customer_insight.retrieval_service import InterviewRetrievalService

# target_type -> 定性过滤字段 / 定量筛选字段
TARGET_MAP: dict[str, dict[str, Any]] = {
    "vehicle_model": {"qual_field": "vehicle_model", "quant_field": "purchase_model", "label": "目标车型"},
    "purchase_type": {"qual_field": "purchase_type", "quant_field": "purchase_type", "label": "购车类型"},
    "age_band": {"qual_field": None, "quant_field": "age_band", "label": "用户圈层（年龄段近似）"},
}

# 群体维度 -> 定性检索过滤字段（访谈库仅支持 city/vehicle_model/purchase_type）
QUAL_FIELD_MAP: dict[str, str] = {
    "purchase_type": "purchase_type",
    "purchase_model": "vehicle_model",
    "city": "city",
}

CONFIG_QUESTION = "用户对车辆配置的关注点、优先级和必备配置有哪些？"
CONFIG_QUANT_QID = "Q3_23__14"  # 智能驾驶关注度（配置关注题）


class JointInsightService:
    """联合洞察：确定性聚合三个既有能力，输出结构化结果供 Agent 归纳 + 前端展示。"""

    def __init__(self) -> None:
        self.retrieval = InterviewRetrievalService()
        self.quant = QuantStatService()

    def joint_insight(
        self,
        target_type: str,
        target_value: str,
        top_k: int = 6,
    ) -> dict[str, Any]:
        target_type = (target_type or "").strip()
        target_value = (target_value or "").strip()
        if target_type not in TARGET_MAP:
            raise ValueError(f"不支持的颗粒度：{target_type}")
        if not target_value:
            raise ValueError("分析对象不能为空。")
        meta = TARGET_MAP[target_type]

        # 1. 定性证据（配置关注）
        filters: dict[str, Any] = {}
        if meta["qual_field"]:
            filters[meta["qual_field"]] = [target_value]
        qualitative = self.retrieval.search(CONFIG_QUESTION, filters, top_k)

        # 2. 战胜战败（仅车型粒度）
        battle = None
        if target_type == "vehicle_model":
            battle = self.retrieval.battle_search(target_value, top_k=top_k)

        # 3. 定量统计（配置关注题，按 target 筛选）
        quant = self.quant.stat_in_group(CONFIG_QUANT_QID, meta["quant_field"], target_value, top=10)

        return {
            "target_type": target_type,
            "target_value": target_value,
            "target_label": meta["label"],
            "qualitative": qualitative,
            "battle": battle,
            "quant": quant,
        }

    def cross_validation(self, group_field: str, group_value: str, top_k: int = 6) -> dict[str, Any]:
        """圈层差异交叉验证：某圈层的定性原声 + 定量关注度/满意度并排展示。"""
        from customer_insight.insight_service import InsightService
        from customer_insight.quant_service import DIMENSIONS

        group_field = (group_field or "").strip()
        group_value = (group_value or "").strip()
        if group_field not in DIMENSIONS:
            raise ValueError(f"不支持的维度：{group_field}")
        if not group_value:
            raise ValueError("群体取值不能为空。")

        insight = InsightService()

        # 1. 定性原声（仅当维度在访谈库有对应过滤字段时检索）
        qual_field = QUAL_FIELD_MAP.get(group_field)
        if qual_field:
            qualitative = self.retrieval.search(CONFIG_QUESTION, {qual_field: [group_value]}, top_k)
        else:
            qualitative = {
                "evidence": [],
                "retrieval": {},
                "warnings": ["访谈库无该维度的过滤字段，仅展示定量分布。"],
            }

        # 2. 定量：16 维度关注度 + 满意度痛点
        matrix = insight.demand_config_matrix(group_field, group_value)
        attention = [
            {"dimension": it["dimension"], "attention_rate": it["attention_rate"],
             "attention_count": it["attention_count"], "quadrant": it["quadrant"]}
            for it in sorted(matrix["items"], key=lambda x: -x["attention_rate"])
        ]
        satisfaction = insight.satisfaction_painpoints(group_field, group_value, top=16)

        return {
            "group_field": group_field,
            "group_label": DIMENSIONS[group_field],
            "group_value": group_value,
            "sample_count": matrix["sample_count"],
            "qualitative": qualitative,
            "attention": attention,
            "satisfaction": satisfaction,
        }
