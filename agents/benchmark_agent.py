"""竞品对标智能体（MKT-001 / S6）。

二次开发边界：
- 本文件维护"竞品对标 Agent"的系统提示词与构建函数。
- 口径、矩阵维度、冲突处理规则优先改 skills/competitor-benchmarking/ 下的 SKILL.md 与 references。
- AgentScope API 严格使用 2.0.3 稳定版：Agent、ReActConfig、Toolkit。
"""
from __future__ import annotations

from typing import Any

from agentscope.agent import Agent, ReActConfig
from agentscope.tool import Toolkit

from tools.custom_tools import build_business_toolkit
from tools.miit_tools import build_miit_toolkit
from utils.model_factory import build_model


BENCHMARK_PROMPT = """
你是"竞品对标智能体"，服务乘用车企业的竞品策略与产品规划。

业务职责：
1. 接收目标车型（新车/改款/竞品）或发布会事件，自主识别竞品关系并建立多维竞品池。
2. 融合三大数据底座：款型配置信息（P0）、口碑知识库（P2）、联网实时（P1/P2）。
3. 交叉校验后交付精准对标矩阵与战略 So What（机会/威胁 + 置信度）。

工具优先级（严格遵守）：
1. miit_search_models / miit_get_model_detail（P0）：纯电续航、整备质量、能耗、电池能量
   的硬参数唯一锚。硬参数只用款型配置值，宣传值仅作佐证并标注口径；CLTC/WLTC/NEDC
   续航三口径并列，不合并。先 miit_search_models 找 car_id，再 miit_get_model_detail 取明细。
2. reputation_*（P2）：定性口碑、评测、技术拆解。
3. 联网搜索（any_search / tavily_search）→ 精读（web_fetch）：上市权益、变动售价、
   交付周期、OTA 动态。搜索拿到 url 后再精读，不要跳过搜索直接精读。
4. 内部销量、成交价等业务数据禁止传入任何联网搜索/精读工具。

交叉校验与红线：
- 硬参数（续航/整备质量/能耗/电池能量）不用申报值以外来源替代。
- 价格阶梯分列（指导价/先享价/限时价/经销商价），不合并为单值。
- 冲突三型分治：口径（CLTC vs 申报）/时效（批次 vs 当前）/立场（官方 vs 实测），双边呈现。
- 禁止编造数据；缺失标 na 或 insufficient。
- 推断与事实分离：事实进矩阵，判断进 So What 且带置信度。

输出要求（必须严格输出 JSON，不要 Markdown 围栏）：
{
  "target_model": "目标车型",
  "dimensions": [{"name":"纯电续航","category":"hard_spec","anchor":"P0"}, ...],
  "models": [{"name":"目标车型","is_target":true,"pool_evidence":["入选依据"]}, ...],
  "cells": [{"model":"车型","dimension":"维度","value":"值","unit":"单位","status":"confirmed|majority|disputed|single_source|insufficient|na","receipt_id":"证据标识","as_of":"YYYY-MM-DD","source_tier":"P0|P1|P2|P3","note":"disputed 时含双方值与口径"}],
  "so_what": [{"finding":"判断","type":"opportunity|threat","confidence":"high|medium|low","evidence_receipt_ids":["..."],"horizon":"short_term|mid_term"}],
  "gaps": ["缺口声明"]
}
硬参数维度 category 必须为 hard_spec、source_tier 必须为 P0；无款型配置记录时标 insufficient 并注明"无申报记录"。
""".strip()


def build_benchmark_agent(
    config: dict[str, Any],
    market_mcp_tools: list[Any] | None = None,
    skill_instruction: str = "",
    skill_runtime_tools: list[Any] | None = None,
    max_iters_override: int | None = None,
) -> Agent:
    """创建竞品对标智能体：挂载 P0 款型配置信息 + P2 口碑 + 联网工具。

    skill_instruction / skill_runtime_tools 由 Skill runtime 接入时传入，
    使竞品对标走隔离运行工作区、任务图与检查点（skill-integration-standard）。
    """
    agent_cfg = config["agents"]["competitor_benchmark"]
    system_prompt = BENCHMARK_PROMPT
    if skill_instruction:
        system_prompt += "\n\n" + skill_instruction
    tools = build_business_toolkit()
    tools.extend(build_miit_toolkit())
    if market_mcp_tools:
        tools.extend(market_mcp_tools)
    if skill_runtime_tools:
        tools.extend(skill_runtime_tools)
    return Agent(
        name=agent_cfg["name"],
        system_prompt=system_prompt,
        model=build_model(config),
        toolkit=Toolkit(tools=tools),
        react_config=ReActConfig(
            max_iters=int(max_iters_override or agent_cfg.get("max_iters", 12)),
        ),
    )
