"""Offline contracts and anti-fabrication gates for the new forecast bridge."""
import asyncio
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from integrations.forecast_engine_runtime import (ForecastEngineSession, prompt_and_specs,
    render_answer, tools_for_session, validate_arguments, is_forecast_question, validated_explanation)


def receipt(name='run_forecast'):
    return dict(seq=1,name=name,result=dict(ok=True,data=dict(source='SAMPLE_PLACEHOLDER',
        model_version='test',data_cutoff='2026-09',scenario='base',data_status='synthetic',
        input_sha256='abc',annual_by_powertrain={'total':dict(p10=180,p50=200,p90=230)},
        y2027_nev_penetration_pct=50,adjustment_chain=[])))


class ForecastContractTests(unittest.TestCase):
    def test_exact_prompt_and_schema_registration(self):
        prompt,specs=prompt_and_specs()
        path=Path(__file__).resolve().parents[1]/'forecast-engine/agent/SYSTEM_PROMPT.md'
        self.assertEqual(prompt,path.read_text(encoding='utf-8'))
        tools=tools_for_session(ForecastEngineSession())
        self.assertEqual([t.name for t in tools],['query_indicator','run_forecast','adjust_scenario','explain_forecast'])
        for tool,spec in zip(tools,specs): self.assertEqual(tool.input_schema,spec['parameters'])

    def test_model_examples_cannot_supply_rendered_numbers(self):
        session=SimpleNamespace(results=[receipt()],run_id='test')
        answer,ok=render_answer(session,'预测市场')
        self.assertTrue(ok)
        self.assertIn('200',answer)
        self.assertNotIn('2056',answer)
        self.assertIn('禁止对外引用',answer)
        self.assertIn('决策含义',answer)
        self.assertIn('数据截止',answer)

    def test_hypothesis_requires_actual_adjust_tool(self):
        answer,ok=render_answer(SimpleNamespace(results=[receipt()],run_id='test'),'如果补贴取消呢')
        self.assertFalse(ok)
        self.assertNotIn('200',answer)

    def test_no_receipt_cannot_publish_forecast(self):
        answer,ok=render_answer(SimpleNamespace(results=[],run_id='test'),'2027预测')
        self.assertFalse(ok)

    def test_untrusted_arguments_rejected_before_worker(self):
        specs={s['name']:s for s in prompt_and_specs()[1]}
        for args in [dict(event_id='x',mult=float('nan')),dict(event_id='../x',mult=1),dict(event_id='x',mult=-1),dict(event_id='x',mult=True)]:
            with self.subTest(args=args), self.assertRaises(ValueError): validate_arguments(specs['adjust_scenario'],args)
        for args in [dict(scenario='fake'),dict(scenario='base',database='C:/private.db')]:
            with self.subTest(args=args), self.assertRaises(ValueError): validate_arguments(specs['run_forecast'],args)
        with self.assertRaises(ValueError): validate_arguments(specs['query_indicator'],dict(powertrain='total',start='2026-13'))

    def test_forecast_agent_uses_entire_file(self):
        from agents.forecast_engine_agent import build_forecast_engine_agent
        with patch('agents.forecast_engine_agent.Agent') as agent, patch('agents.forecast_engine_agent.build_model'):
            build_forecast_engine_agent({'agents':{'market_strategy':{'name':'test'}}},ForecastEngineSession())
        self.assertTrue(agent.call_args.kwargs['system_prompt'].startswith(prompt_and_specs()[0]))
        self.assertEqual(agent.call_args.kwargs['react_config'].max_iters,8)

    def test_explicit_market_forecast_routing(self):
        self.assertTrue(is_forecast_question('2027年纯电零售大概什么水平'))
        self.assertTrue(is_forecast_question('新能源销量预测'))
        self.assertFalse(is_forecast_question('请总结政策风险和市场进入建议'))

    def test_historical_receipt_is_not_forecast(self):
        answer,ok=render_answer(SimpleNamespace(results=[receipt('query_indicator')],run_id='test'),'预测市场')
        self.assertFalse(ok)

    def test_preserve_qualitative_interpretation_and_reject_new_numbers(self):
        text='### 关键假设\n事件系数仅是本轮情景假设，需要持续核验。\n### 决策含义\n应结合区间检查排产弹性，避免依赖单点结果。\n### 不确定性提示\n真实数据尚未接入，当前不能形成正式经营结论。'
        self.assertIn('检查排产弹性',validated_explanation(text))
        self.assertEqual(validated_explanation(text.replace('排产弹性','排产增长99%')),'')

    def test_deepseek_policy_and_credential_host_guard(self):
        import json
        from utils.config import CONFIG_PATH
        from utils.model_routing import route_model
        from utils.model_factory import build_model
        cfg=json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
        self.assertEqual(route_model(cfg)['active_provider'],'deepseek_flash')
        self.assertEqual(route_model(cfg,question='多情景对比')['active_provider'],'deepseek_pro')
        self.assertFalse(cfg['providers']['minimax']['enabled'])
        wrong={'active_provider':'wrong','providers':{'wrong':{'model':'test','type':'openai_compatible','base_url':'https://dashscope.aliyuncs.com','api_key_env':'DASHSCOPE_API_KEY'}}}
        with self.assertRaisesRegex(RuntimeError,'DeepSeek'): build_model(wrong)


class ForecastRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_forecast_chat_enters_new_bridge(self):
        import app
        expected={'answer':'tool verified','agent':'market_strategy'}
        with patch.object(app,'load_dotenv'), patch.object(app,'load_json_config',return_value={}), \
             patch('integrations.forecast_engine_runtime.run_forecast_engine_agent',AsyncMock(return_value=expected)) as run:
            result=await app.run_agent_once('market_strategy','预测问题','market_forecast')
        self.assertEqual(result,expected)
        run.assert_awaited_once()


if __name__=='__main__': unittest.main()
