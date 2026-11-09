"""深度调研智能体（MKT-002）· 确定性编排版。

二次开发边界：
- 本文件只提供两个**无工具、单轮**的受限模型调用：检索计划、报告正文撰写。
- 搜索、精读、来源登记、引用清理、报告组装与验收由
  utils/deep_research_engine.py 确定性执行（模型文字不是完成证据）。
- 调研方法论口径优先改 skills/deep-research/ 下的 SKILL.md 与 references。
- AgentScope API 严格使用 2.0.3 稳定版：Agent、ReActConfig、Toolkit。
"""
from __future__ import annotations

from typing import Any

from agentscope.agent import Agent, ReActConfig
from agentscope.tool import Toolkit

from utils.model_factory import build_model


RESEARCH_PLAN_PROMPT = """
你是深度调研的计划器。针对用户调研主题输出一个严格 JSON 对象（不要 Markdown 围栏、不要解释文字）：
{"intent": "comparison|report", "depth": "L1|L2", "queries": ["...", "..."], "sub_questions": ["..."]}

规则：
1. intent：两个及以上对象比较选 comparison；单一主题系统性研究选 report；单一可核验事实选 L1。
2. queries：4-6 条中文搜索词，覆盖主题的不同子问题；每条 ≤20 字，含关键对象名与核心属性；不重复。
3. sub_questions：2-4 条该调研要回答的子问题。
4. 只输出 JSON，第一个字符必须是 {。
""".strip()


RESEARCH_REPORT_PROMPT = """
你是深度调研的撰写者。只依据下方给出的已取证来源写报告正文，不调用任何工具，不编造任何来源中没有的信息。

结构（按意图二选一）：
- comparison（对比分析）：## 一、结论摘要（≤5 条要点，事实/判断分标）→ ## 二、对比口径 → ## 三、分维度对比（表格，含 来源 列）→ ## 四、冲突与分歧点 → ## 五、判断与建议 → ## 六、缺口声明
- report（研究报告）：## 一、结论摘要 → ## 二、背景与研究问题 → ## 三、现状分析 → ## 四、关键发现 → ## 五、趋势与展望 → ## 六、缺口声明

硬规则：
1. 每条事实句尾用 [cite:N] 引用，N 只能取证据块中已有的编号；不得虚构编号。
2. 来源冲突双边呈现（数值+口径），检索不到的写 [数据不足] 进缺口声明。
3. 判断与事实分离；判断标注（判断｜置信度 高/中/低）。
4. 总长度 1200-2800 个中文字符；不要写「参考来源」章节（由系统追加）；第一个字符必须是 #。
""".strip()


def _light_agent(config: dict[str, Any], name: str, prompt: str) -> Agent:
    return Agent(
        name=name,
        system_prompt=prompt,
        model=build_model(config),
        toolkit=Toolkit(tools=[]),
        react_config=ReActConfig(max_iters=1),
    )


def build_research_plan_agent(config: dict[str, Any]) -> Agent:
    """创建检索计划 Agent：无工具单轮，输出严格 JSON 计划。"""
    return _light_agent(config, "深度调研计划器", RESEARCH_PLAN_PROMPT)


def build_research_report_agent(config: dict[str, Any]) -> Agent:
    """创建报告撰写 Agent：无工具单轮，只基于注入证据写正文。"""
    return _light_agent(config, "深度调研撰写器", RESEARCH_REPORT_PROMPT)
