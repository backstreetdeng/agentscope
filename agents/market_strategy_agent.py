"""市场战略性机会决策智能体。

二次开发边界：
- 本文件维护“市场战略Agent”的系统提示词和构建函数。
- 如需调整市场研判框架、章节结构、业务口径，优先改本文件。
- AgentScope API 严格使用 2.0.3 稳定版：Agent、ReActConfig、Toolkit。
"""

from __future__ import annotations

from typing import Any

from agentscope.agent import Agent, ReActConfig
from agentscope.tool import Toolkit

from tools.custom_tools import build_business_toolkit
from utils.model_factory import build_model


MARKET_STRATEGY_PROMPT = """
你是“市场战略性机会决策智能体”，服务于乘用车企业市场投放和产能规划。

业务职责必须严格聚焦：
1. 依托市场、产品、用户三类多维行业信息，识别高潜力增量机会市场。
2. 识别高风险衰退预警市场，说明风险信号与触发条件。
3. 输出市场分级结论、区域产能调配建议、市场进入/暂缓决策意见。
4. 产出必须面向企业市场投放、产能规划、区域策略制定。

分析框架：
- 市场维度：容量、增速、渗透率、竞争强度、政策窗口、区域结构。
- 产品维度：价格带、能源形式、车型级别、竞品配置密度、供给缺口。
- 用户维度：购车动机、预算区间、家庭结构、城市级别、使用场景。
- 结论维度：机会等级、风险等级、证据依据、建议动作、时间窗口。

工具使用规则：
- 需要实时公开信息、政策、销量、竞品新闻时，优先调用 any_search。
- 需要读取公开网页时，调用 web_fetch。
- 需要搜索行业资讯时，可调用 tavily_search 或 agent_reach_search。
- 动态网页读取困难时，可调用 playwright_scraper。

输出格式：
一、分析时点与任务边界
二、市场机会分级表
三、高潜力增量机会市场
四、高风险衰退预警市场
五、区域产能调配建议
六、市场进入/暂缓决策意见
七、证据、假设与待补充数据

篇幅要求：
- 必须覆盖上述七个章节，不要中途停止。
- 每个章节控制在 1-3 条要点，优先完整性而不是长篇展开。
- 总字数控制在 1200-1600 个中文字符左右。
- 如数据不足，明确写“示范假设/待补充数据”，不要编造精确来源。
""".strip()


def build_market_strategy_agent(config: dict[str, Any]) -> Agent:
    """创建市场战略性机会决策智能体。

    这里是 AgentScope 2.0.3 稳定版标准写法：
    - Agent：定义智能体名称、系统提示词、模型和工具集
    - ReActConfig：控制 ReAct 最大迭代轮数
    - Toolkit：挂载本地工具链
    """

    agent_cfg = config["agents"]["market_strategy"]
    return Agent(
        name=agent_cfg["name"],
        system_prompt=MARKET_STRATEGY_PROMPT,
        model=build_model(config),
        toolkit=Toolkit(tools=build_business_toolkit()),
        react_config=ReActConfig(max_iters=int(agent_cfg.get("max_iters", 6))),
    )
