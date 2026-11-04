"""用户洞察 AgentScope 工具：把访谈检索、定量统计与专题洞察服务包装为只读业务工具。

- InterviewEvidenceSearchTool 沿用既有局部编号（供市场战略 Agent 复用），
  可通过 ``register=True`` 切换为全局编号（供 agentic 自由问答使用）。
- 其余新增工具（battle / quant / insight）仅面向 agentic 自由问答，
  一律走全局证据注册，保证多轮工具调用后的 [E#] 引用可被请求结束后统一校验。
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from agentscope.message import TextBlock
from agentscope.tool import ToolChunk

from customer_insight.insight_service import InsightService
from customer_insight.quant_service import QuantStatService
from customer_insight.retrieval_service import InterviewRetrievalService
from tools.custom_tools import (
    ReadOnlyBusinessTool,
    TavilySearchTool,
    WebFetchTool,
    record_tool_call,
    register_evidence,
)


def _as_toolchunk(result: Any) -> ToolChunk:
    """把结构化结果序列化为工具返回文本。"""

    return ToolChunk(content=[TextBlock(text=json.dumps(result, ensure_ascii=False, default=str))])


class InterviewEvidenceSearchTool(ReadOnlyBusinessTool):
    """从 63 位受访者的真实访谈证据库检索可引用原话。

    返回结构化证据：匿名受访者编号、城市、车型、购车类型、题号、说话人、
    秒级/段落时间、原文、置信度和来源校验和。原话只来自数据库，不生成或改写。
    """

    name = "interview_evidence_search"
    description = (
        "从 63 位乘用车受访者的真实访谈证据库中检索可引用的原话证据，"
        "返回受访者匿名编号、城市、车型、购车类型、题号、说话人、时间戳和原文。"
        "用于需要真实用户原声佐证的问题；没有命中时返回空证据，不得编造访谈观点。"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "要检索的访谈问题或关注点。"},
            "filters": {
                "type": "object",
                "description": "可选结构化过滤，键限 city/vehicle_model/purchase_type/question_ids/tag_names/tag_values/respondent_codes，值为字符串或字符串数组。",
            },
            "top_k": {"type": "integer", "description": "返回证据条数，默认 6，最大 8。", "default": 6},
        },
        "required": ["question"],
    }

    def __init__(self, register: bool = False) -> None:
        super().__init__()
        self._register = register

    async def call(
        self,
        question: str,
        filters: dict[str, Any] | None = None,
        top_k: int = 6,
    ) -> ToolChunk:
        try:
            service = InterviewRetrievalService()
            result = await asyncio.to_thread(service.search, question, filters, top_k)
            if self._register:
                result["evidence"] = register_evidence(result.get("evidence", []))
            record_tool_call(
                self.name,
                "success",
                f"question={question[:80]}; evidence={len(result.get('evidence', []))}",
            )
            return _as_toolchunk(result)
        except Exception as exc:
            record_tool_call(
                self.name,
                "error",
                f"question={question[:80]}; error={type(exc).__name__}: {exc}",
            )
            raise


class BattleSearchTool(ReadOnlyBusinessTool):
    """战胜战败决策链群体分析：对比车型/选购原因/弃购原因/能源形式取舍的结构化归因。"""

    name = "battle_search"
    description = (
        "对购买某目标车型的受访者做战胜战败决策链结构化归因："
        "对比了哪些车型、放弃了哪些（原因）、最终选购原因和能源形式取舍。"
        "只陈述受访者原话归因，不强行因果推断。"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "vehicle_model": {"type": "string", "description": "目标车型名称，例如：唐L。"},
            "filters": {
                "type": "object",
                "description": "可选结构化过滤，键限 city/purchase_type，值为字符串或字符串数组。",
            },
            "top_k": {"type": "integer", "description": "返回证据条数，默认 6，最大 8。", "default": 6},
        },
        "required": ["vehicle_model"],
    }

    async def call(
        self,
        vehicle_model: str,
        filters: dict[str, Any] | None = None,
        top_k: int = 6,
    ) -> ToolChunk:
        try:
            service = InterviewRetrievalService()
            result = await asyncio.to_thread(service.battle_search, vehicle_model, filters, top_k)
            result["evidence"] = register_evidence(result.get("evidence", []))
            record_tool_call(
                self.name,
                "success",
                f"vehicle_model={vehicle_model}; buyers={result.get('battle', {}).get('buyer_count', 0)}",
            )
            return _as_toolchunk(result)
        except Exception as exc:
            record_tool_call(
                self.name,
                "error",
                f"vehicle_model={vehicle_model}; error={type(exc).__name__}: {exc}",
            )
            raise


class QuantListQuestionsTool(ReadOnlyBusinessTool):
    """列出定量问卷题目，用于确定某业务问题对应的题目编号。"""

    name = "quant_list_questions"
    description = (
        "列出定量问卷题目（question_id + 题干），支持关键词过滤。"
        "先用它确定题目编号，再调用 quant_stat / quant_stat_in_group 统计分布。"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "keyword": {"type": "string", "description": "题目关键词，例如：后排空间、续航、智驾。"},
        },
    }

    async def call(self, keyword: str = "") -> ToolChunk:
        try:
            svc = QuantStatService()
            questions = await asyncio.to_thread(svc.list_questions, keyword, 2000)
            record_tool_call(self.name, "success", f"keyword={keyword[:40]}; count={len(questions)}")
            return _as_toolchunk(questions)
        except Exception as exc:
            record_tool_call(self.name, "error", f"keyword={keyword[:40]}; error={type(exc).__name__}: {exc}")
            raise


class QuantStatTool(ReadOnlyBusinessTool):
    """定量问卷：按群体维度统计某题分布。"""

    name = "quant_stat"
    description = (
        "统计定量问卷某题在某个群体维度下的选项分布与占比。"
        "group_by 可选：purchase_type(购车类型)/price_band(价格段)/age_band(年龄段)/"
        "gender(性别)/city(城市)/purchase_model(车型)。勾选题占比按群体总样本算。"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "question_id": {"type": "string", "description": "题目编号，例如：Q3_13__14。"},
            "group_by": {"type": "string", "description": "切分维度，见工具描述白名单。"},
            "top": {"type": "integer", "description": "返回分组数，默认 20。", "default": 20},
        },
        "required": ["question_id", "group_by"],
    }

    async def call(self, question_id: str, group_by: str, top: int = 20) -> ToolChunk:
        try:
            svc = QuantStatService()
            result = await asyncio.to_thread(svc.stat, question_id, group_by, top)
            record_tool_call(self.name, "success", f"question_id={question_id}; group_by={group_by}")
            return _as_toolchunk(result)
        except Exception as exc:
            record_tool_call(self.name, "error", f"question_id={question_id}; error={type(exc).__name__}: {exc}")
            raise


class QuantInGroupTool(ReadOnlyBusinessTool):
    """定量问卷：筛选某群体后统计某题分布（不按维度切分）。"""

    name = "quant_stat_in_group"
    description = (
        "筛选 filter_field=filter_value 的样本后，统计某题的选项分布。"
        "用于回答「某群体在某题上的分布」；filter_field 白名单同 quant_stat 的 group_by。"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "question_id": {"type": "string", "description": "题目编号，例如：Q3_13__14。"},
            "filter_field": {"type": "string", "description": "筛选维度，同 group_by 白名单。"},
            "filter_value": {"type": "string", "description": "筛选维度取值，例如：唐L / 增换购。"},
            "top": {"type": "integer", "description": "返回选项数，默认 10。", "default": 10},
        },
        "required": ["question_id", "filter_field", "filter_value"],
    }

    async def call(self, question_id: str, filter_field: str, filter_value: str, top: int = 10) -> ToolChunk:
        try:
            svc = QuantStatService()
            result = await asyncio.to_thread(svc.stat_in_group, question_id, filter_field, filter_value, top)
            record_tool_call(self.name, "success", f"question_id={question_id}; filter={filter_field}={filter_value}")
            return _as_toolchunk(result)
        except Exception as exc:
            record_tool_call(self.name, "error", f"question_id={question_id}; error={type(exc).__name__}: {exc}")
            raise


class SegmentClustersTool(ReadOnlyBusinessTool):
    """圈层画像聚类。"""

    name = "segment_clusters"
    description = "圈层画像聚类：按购车类型聚类，输出每个圈层的价格段/年龄段/性别/车型画像与样本量。"
    input_schema = {
        "type": "object",
        "properties": {
            "min_samples": {"type": "integer", "description": "圈层最小样本量，默认 30。", "default": 30},
        },
    }

    async def call(self, min_samples: int = 30) -> ToolChunk:
        try:
            svc = InsightService()
            result = await asyncio.to_thread(svc.segment_clusters, min_samples)
            record_tool_call(self.name, "success", f"min_samples={min_samples}; segments={len(result.get('segments', []))}")
            return _as_toolchunk(result)
        except Exception as exc:
            record_tool_call(self.name, "error", f"error={type(exc).__name__}: {exc}")
            raise


class SatisfactionPainpointsTool(ReadOnlyBusinessTool):
    """满意度痛点洞察。"""

    name = "satisfaction_painpoints"
    description = (
        "满意度痛点：统计某群体在 16 个产品维度（安全/操控/动力/舒适/空间/外观/内饰/"
        "质量/使用费用/购车价格/品牌/服务/智能座舱/智能驾驶/纯电续航/电池特性）上的"
        "低分率（打分≤6）与均分，定位最不满意维度。group_field 白名单同 quant_stat。"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "group_field": {"type": "string", "description": "群体维度，白名单同 quant_stat 的 group_by。"},
            "group_value": {"type": "string", "description": "群体取值，例如：唐L / 增换购。"},
            "top": {"type": "integer", "description": "返回维度数，默认 10。", "default": 10},
        },
        "required": ["group_field", "group_value"],
    }

    async def call(self, group_field: str, group_value: str, top: int = 10) -> ToolChunk:
        try:
            svc = InsightService()
            result = await asyncio.to_thread(svc.satisfaction_painpoints, group_field, group_value, top)
            record_tool_call(self.name, "success", f"group={group_field}={group_value}")
            return _as_toolchunk(result)
        except Exception as exc:
            record_tool_call(self.name, "error", f"group={group_field}={group_value}; error={type(exc).__name__}: {exc}")
            raise


class RepurchaseIntentTool(ReadOnlyBusinessTool):
    """再购意愿与品牌忠诚。"""

    name = "repurchase_intent"
    description = (
        "再购意愿与品牌忠诚：统计某群体再次购车的时间、技术类型、意向品牌及是否同品牌。"
        "用于判断谁会流失、为什么。group_field 白名单同 quant_stat。"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "group_field": {"type": "string", "description": "群体维度，白名单同 quant_stat 的 group_by。"},
            "group_value": {"type": "string", "description": "群体取值，例如：唐L / 增换购。"},
        },
        "required": ["group_field", "group_value"],
    }

    async def call(self, group_field: str, group_value: str) -> ToolChunk:
        try:
            svc = InsightService()
            result = await asyncio.to_thread(svc.repurchase_intent, group_field, group_value)
            record_tool_call(self.name, "success", f"group={group_field}={group_value}")
            return _as_toolchunk(result)
        except Exception as exc:
            record_tool_call(self.name, "error", f"group={group_field}={group_value}; error={type(exc).__name__}: {exc}")
            raise


class DemandConfigMatrixTool(ReadOnlyBusinessTool):
    """需求×配置匹配矩阵。"""

    name = "demand_config_matrix"
    description = (
        "需求×配置匹配矩阵：16 个产品维度的购车关注度 × 满意度，用固定阈值划分四象限"
        "（优先诊断/重点维持/局部痛点/保持监测）。高关注=关注率≥25%，高不满=低分率≥5.7%。"
        "只看 16 个维度层；问「哪些具体配置」时再用 config_detail 下钻明细项。"
        "group_field 白名单同 quant_stat；group_value 可传聚合词（如增换购），工具返回实际展开值。"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "group_field": {"type": "string", "description": "群体维度，白名单同 quant_stat 的 group_by。"},
            "group_value": {"type": "string", "description": "群体取值，例如：唐L / 增换购。"},
        },
        "required": ["group_field", "group_value"],
    }

    async def call(self, group_field: str, group_value: str) -> ToolChunk:
        try:
            svc = InsightService()
            result = await asyncio.to_thread(svc.demand_config_matrix, group_field, group_value)
            record_tool_call(self.name, "success", f"group={group_field}={group_value}")
            return _as_toolchunk(result)
        except Exception as exc:
            record_tool_call(self.name, "error", f"group={group_field}={group_value}; error={type(exc).__name__}: {exc}")
            raise


class ConfigDetailTool(ReadOnlyBusinessTool):
    """具体配置项关注度下钻。"""

    name = "config_detail"
    description = (
        "具体配置项下钻：在 16 个产品维度（Q3_13__N）之下，按群体统计 94 个具体配置项"
        "（Q3_13_1__NN，如车身强度/预防事故主动安全配置/刹车距离）的勾选率并降序返回。"
        "问题问「最看重哪些配置」时应调用本工具，不要只停在 16 个维度层。"
        "group_field 白名单同 quant_stat；group_value 可直接传聚合词（如增换购），工具会返回实际展开值。"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "group_field": {"type": "string", "description": "群体维度，白名单同 quant_stat 的 group_by。"},
            "group_value": {"type": "string", "description": "群体取值，例如：唐L / 增换购。"},
            "top": {"type": "integer", "description": "返回配置项数量，默认 15。", "default": 15},
        },
        "required": ["group_field", "group_value"],
    }

    async def call(self, group_field: str, group_value: str, top: int = 15) -> ToolChunk:
        try:
            svc = InsightService()
            result = await asyncio.to_thread(svc.config_detail, group_field, group_value, top)
            record_tool_call(self.name, "success", f"group={group_field}={group_value}; top={top}")
            return _as_toolchunk(result)
        except Exception as exc:
            record_tool_call(self.name, "error", f"group={group_field}={group_value}; error={type(exc).__name__}: {exc}")
            raise


class CompetitorCompareTool(ReadOnlyBusinessTool):
    """竞品横向对比。"""

    name = "competitor_compare"
    description = (
        "竞品横向对比：按车型分组计算各产品维度的关注度/满意度低分率，识别差异最大的维度。"
        "focus 可选 attention(关注度)/satisfaction(满意度低分率)。"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "focus": {"type": "string", "description": "对比口径，attention 或 satisfaction，默认 attention。"},
            "min_samples": {"type": "integer", "description": "车型最小样本量，默认 20。", "default": 20},
            "top_models": {"type": "integer", "description": "返回车型数，默认 8。", "default": 8},
            "top_dims": {"type": "integer", "description": "返回差异最大维度数，默认 5。", "default": 5},
        },
    }

    async def call(
        self,
        focus: str = "attention",
        min_samples: int = 20,
        top_models: int = 8,
        top_dims: int = 5,
    ) -> ToolChunk:
        try:
            svc = InsightService()
            result = await asyncio.to_thread(
                svc.competitor_compare, focus, min_samples, top_models, top_dims
            )
            record_tool_call(self.name, "success", f"focus={focus}; models={len(result.get('models', []))}")
            return _as_toolchunk(result)
        except Exception as exc:
            record_tool_call(self.name, "error", f"error={type(exc).__name__}: {exc}")
            raise


class CarSpecWebSearchTool(TavilySearchTool):
    """联网搜索公开车型信息（续航、参数、价格等访谈库未覆盖的外部事实）。"""

    name = "web_search"
    description = (
        "联网搜索公开网页，用于查询访谈库和问卷没有的第三方事实，"
        "例如某车型的纯电续航里程、电池容量、指导价、上市时间。"
        "返回摘要与来源 URL；引用时必须标注来源，不要把它当成受访者原话或问卷比例。"
    )


class CarSpecWebFetchTool(WebFetchTool):
    """读取指定公开网页正文，用于核对搜索结果中的车型参数。"""

    name = "web_fetch"
    description = (
        "读取 http/https 公开网页正文，用于核对搜索到的车型参数细节。"
        "只用于公开信息取证，不能访问需要登录的页面。"
    )


def build_user_insight_toolkit() -> list[ReadOnlyBusinessTool]:
    """用户洞察自由问答 Agent 专用工具集（独立于市场战略 Agent 的共用 toolkit）。"""

    return [
        InterviewEvidenceSearchTool(register=True),
        BattleSearchTool(),
        QuantListQuestionsTool(),
        QuantStatTool(),
        QuantInGroupTool(),
        SegmentClustersTool(),
        SatisfactionPainpointsTool(),
        RepurchaseIntentTool(),
        DemandConfigMatrixTool(),
        ConfigDetailTool(),
        CompetitorCompareTool(),
        CarSpecWebSearchTool(),
        CarSpecWebFetchTool(),
    ]
