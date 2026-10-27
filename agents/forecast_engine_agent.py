"""Forecast mode of the market-strategy agent: verbatim engine prompt and four schemas."""
from agentscope.agent import Agent, ReActConfig
from agentscope.tool import Toolkit
from integrations.forecast_engine_runtime import prompt_and_specs, tools_for_session
from utils.model_factory import build_model


def build_forecast_engine_agent(config, session):
    prompt,_=prompt_and_specs()
    prompt += '\n\n【本次运行约束】示例中的数字不是本轮结果。所有预测值来自本次工具回执；原始数据和事件库不可修改。最终数值报告由服务器从工具回执生成。合成或未验收数据必须保持禁止对外引用标识。'
    prompt += '\n最终答复另列【关键假设】【决策含义】【不确定性提示】三个独立标题。这三个解释段只用定性文字，不再写数字、年份、百分比或数量；引用“本次区间”“基准结果”等工具事实即可，数值部分由后端展示。政策影响必须称为情景假设，不得把模板示例或未经核验的政策当作事实。请结合用户问题解释真正的业务决策含义。'
    return Agent(name=config['agents']['market_strategy']['name']+'-市场预测',system_prompt=prompt,
                 model=build_model(config),toolkit=Toolkit(tools=tools_for_session(session)),
                 react_config=ReActConfig(max_iters=8))
