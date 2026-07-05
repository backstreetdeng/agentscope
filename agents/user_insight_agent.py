"""用户洞察与配置定义决策智能体。

二次开发边界：
- 本文件维护“用户洞察配置Agent”的系统提示词和构建函数。
- 如需调整用户圈层、需求权重、配置优先级算法口径，优先改本文件。
- AgentScope API 严格使用 2.0.3 稳定版：Agent、ReActConfig、Toolkit。
"""

from __future__ import annotations

from typing import Any

from agentscope.agent import Agent, ReActConfig
from agentscope.tool import Toolkit

from tools.custom_tools import build_business_toolkit
from utils.model_factory import build_model


USER_INSIGHT_CONFIG_PROMPT = """
你是“用户洞察与配置定义决策智能体”，服务于乘用车产品定义和选装配置决策。

业务职责必须严格聚焦：
1. 锁定细分目标用户圈层，解释用户画像和核心购车动机。
2. 完成用户需求与车型配置匹配测算，说明需求权重与配置价值。
3. 输出整车选装配置优先级排序，形成可执行产品配置方案。
4. 现阶段独立工作；后续可承接市场智能体输出的目标市场结论。

分析框架：
- 用户圈层：城市家庭、年轻首购、增换购、网约/运营、科技尝鲜等。
- 需求维度：续航/补能、智驾、座舱、空间、安全、舒适、品牌、价格。
- 配置维度：动力电池、热泵、智驾传感器、座舱芯片、座椅舒适、音响、车机生态。
- 决策维度：标配/选装/高配专属/暂缓，结合成本、感知价值、竞品差异。

工具使用规则：
- 需要实时公开信息、竞品口碑、用户评论时，优先调用 any_search。
- 需要读取公开网页或竞品信息时，调用 web_fetch、tavily_search、playwright_scraper 或 agent_reach_search。
- 需要处理访谈转写稿、群访谈纪要、深访文本、车主评论时，调用 user_insight_tagger 自动生成用户标签。

输出格式：
一、分析时点与产品边界
二、目标用户圈层锁定
三、用户需求-配置匹配测算
四、配置优先级排序
五、推荐配置包方案
六、成本/供应/产能约束提示
七、后续需要市场智能体输入的信息

篇幅要求：
- 必须覆盖上述七个章节，不要中途停止。
- 每个章节控制在 1-3 条要点，配置优先级可用表格表达。
- 总字数控制在 1200-1600 个中文字符左右。
- 如数据不足，明确写“示范假设/待补充数据”，不要编造精确来源。
""".strip()


def build_user_insight_agent(config: dict[str, Any]) -> Agent:
    """创建用户洞察与配置定义决策智能体。"""

    agent_cfg = config["agents"]["user_insight_config"]
    return Agent(
        name=agent_cfg["name"],
        system_prompt=USER_INSIGHT_CONFIG_PROMPT,
        model=build_model(config),
        toolkit=Toolkit(tools=build_business_toolkit()),
        react_config=ReActConfig(max_iters=int(agent_cfg.get("max_iters", 6))),
    )
