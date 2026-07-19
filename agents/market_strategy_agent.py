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


MARKET_MONTHLY_REPORT_PROMPT = """
你是“乘用车市场月报分析智能体”，负责把已验数的月度市场数据转为正式月报。

本轮已由市场月报 Skill 注入数据边界、固定报告标题和可引用的数据摘要。你必须完全
遵循该 Skill 的月报结构，不使用市场战略 Agent 的七章机会决策短模板，也不要输出
“分析时点与任务边界”“市场进入/暂缓”等与月报无关的通用章节。

输出要求：
1. 只输出完整、独立的 Markdown 月报；从总标题开始，到“数据来源与数据缺口”结束。
2. Skill 给出的每一个固定标题都必须出现，不得合并 2.3、2.4、2.5；先完成全部章节，
   再补充修辞，不要在中途结束。
3. 每节保持数据事实、结构解释、业务意义三层表达；只使用已注入的可验证数据，
   缺少车型、品牌、区域明细时必须如实披露，禁止编造。
4. 结构解读只能解释表内已出现的销量、同比、环比和份额变化。新能源/燃油、价格带、
   具体产品、经销商、库存、促销、投放、政策等未在输入数据中出现的原因，一律不得写成
   事实；确有必要时只能单独标注为“待核验假设”。
5. 每个固定小节最多 2 个紧凑段落，目标篇幅为 2,100-2,700 个中文字符；优先保证
   标题、展望的确定性/风险变量、数据来源与缺口全部完整。
6. 未被用户明确要求时，不调用外部检索工具；不要展示模型推理、写作过程或修订说明。
""".strip()


def build_market_strategy_agent(
    config: dict[str, Any],
    skill_instruction: str = "",
    monthly_report: bool = False,
    max_tokens_override: int | None = None,
) -> Agent:
    """创建市场战略性机会决策智能体。

    这里是 AgentScope 2.0.3 稳定版标准写法：
    - Agent：定义智能体名称、系统提示词、模型和工具集
    - ReActConfig：控制 ReAct 最大迭代轮数
    - Toolkit：挂载本地工具链
    """

    agent_cfg = config["agents"]["market_strategy"]
    # 月报与机会决策采用不同的交付结构。这里显式切换提示词，避免通用的
    # “七章、1200-1600 字”约束与月报 Skill 的十段结构发生冲突。
    system_prompt = MARKET_MONTHLY_REPORT_PROMPT if monthly_report else MARKET_STRATEGY_PROMPT
    if skill_instruction:
        # 月报 Skill 在运行时传入经数据门禁处理的上下文。它只覆盖本轮任务的
        # 报告结构，不改变 AgentScope 2.0.3 的 Agent/ReAct/Toolkit 稳定 API。
        system_prompt += "\n\n" + skill_instruction
    return Agent(
        name=agent_cfg["name"],
        system_prompt=system_prompt,
        model=build_model(config, max_tokens_override=max_tokens_override),
        toolkit=Toolkit(tools=build_business_toolkit()),
        react_config=ReActConfig(max_iters=int(agent_cfg.get("max_iters", 6))),
    )
