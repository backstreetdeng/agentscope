"""AgentScope 2.0.3 乘用车多智能体业务协作工程入口。

工程定位：
- 根目录 main.py 只负责程序启动、配置加载、多 Agent 调度和日志打印。
- 具体智能体定义放在 agents/。
- 自定义工具放在 tools/。
- 模型适配与模型工厂放在 model_adapters/、utils/。

稳定版约束：
- 本工程严格使用 AgentScope 2.0.3 稳定正式版公开 API。
- 不使用 AgentScope 2.0.4 dev 实验接口、临时参数或未稳定底层 API。
"""

from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv

from agentscope.agent import Agent
from agentscope.message import UserMsg

from agents.market_strategy_agent import build_market_strategy_agent
from agents.user_insight_agent import build_user_insight_agent
from utils.config import ENV_PATH, PROJECT_DIR, expand_env, load_json_config
from utils.text import strip_thinking


def build_agent(config: dict) -> Agent:
    """兼容旧版单 Agent 入口。

    浏览器 Demo 和早期脚本如果仍调用 build_agent，会默认创建市场战略 Agent。
    新的二次开发建议直接调用 agents/ 下的具体构建函数。
    """

    return build_market_strategy_agent(config)


async def run_agent(agent: Agent, task: str) -> str:
    """运行单个 Agent，并在控制台打印完整日志。"""

    print("\n" + "=" * 88)
    print(f"启动智能体：{agent.name}")
    print("-" * 88)
    print(f"任务输入：{task}")
    print("-" * 88)

    reply = await agent.reply(UserMsg(name="业务用户", content=task))
    output = strip_thinking(reply.get_text_content())
    print(output)
    print("=" * 88)
    return output


async def run_independent_agents() -> None:
    """前期 Demo 主流程：两个智能体独立完成各自业务任务。

    当前阶段按用户要求先展示“两个专业智能体独立工作”：
    1. 市场战略性机会决策智能体输出市场研判报告。
    2. 用户洞察与配置定义决策智能体输出配置方案报告。

    后续融合时，可把 market_report 作为上下文传给 user_agent，
    形成“市场结论 -> 用户圈层 -> 配置定义”的上下游闭环。
    """

    load_dotenv(ENV_PATH, override=True)
    config = load_json_config()

    print("AgentScope 2.0.3 多智能体业务协作 Demo")
    print(f"项目目录：{PROJECT_DIR}")
    print(f"配置文件：{PROJECT_DIR / 'model_config' / 'config.json'}")
    print(f"当前模型 provider：{config['active_provider']}")
    print("运行模式：前期独立工作，后期可扩展为上下游联动。")

    market_agent = build_market_strategy_agent(config)
    user_agent = build_user_insight_agent(config)

    market_task = os.getenv("MARKET_TASK") or config["demo_tasks"]["market_strategy"]
    user_task = os.getenv("USER_TASK") or config["demo_tasks"]["user_insight_config"]

    market_report = await run_agent(market_agent, market_task)
    user_report = await run_agent(user_agent, user_task)

    print("\n" + "#" * 88)
    print("前期独立工作结果摘要")
    print("#" * 88)
    print("市场战略性机会决策智能体已输出：市场机会、风险预警、产能调配、进入/暂缓策略。")
    print("用户洞察与配置定义决策智能体已输出：用户圈层、需求配置匹配、配置优先级。")
    print("后续联动方式：将 market_report 作为上下文输入 user_agent，即可形成业务闭环。")
    print(f"市场报告字符数：{len(market_report)}")
    print(f"配置报告字符数：{len(user_report)}")


if __name__ == "__main__":
    asyncio.run(run_independent_agents())

