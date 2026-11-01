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
