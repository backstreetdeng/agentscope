"""Task-isolated forecast engine tools and server-rendered numeric responses.

Model text never supplies numeric forecasts to the final answer. Engine source,
source CSVs and source database are preserved; private task copies keep evidence.
"""
from __future__ import annotations
import asyncio
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import sys
import time
from uuid import uuid4

from agentscope.message import TextBlock, UserMsg
from agentscope.permission import PermissionBehavior, PermissionDecision
from agentscope.tool import ToolBase, ToolChunk

PROJECT = Path(__file__).resolve().parents[1]
ENGINE = PROJECT/'forecast-engine'
TOOL_NAMES = ('query_indicator','run_forecast','adjust_scenario','explain_forecast')
HYPOTHETICAL = re.compile(r'如果|假设|要是|取消|调整.*(?:系数|补贴)|what\s+if', re.I)


def is_forecast_question(question):
    """Explicit market forecasts enter math tools; ordinary strategy tasks stay unchanged."""
    market = re.search(r'销量|零售|渗透率|纯电|插混|新能源|市场总量',question)
    intent = re.search(r'预测|情景测算|明年|2027|2028|如果.*(?:补贴|购置税)',question)
    return bool(market and intent)


def prompt_and_specs():
    prompt = (ENGINE/'agent/SYSTEM_PROMPT.md').read_text(encoding='utf-8')
    blocks = re.findall(r'```json\s*(.*?)```', prompt, re.S)
    specs = next(json.loads(block)['tools'] for block in blocks if '"tools"' in block)
    if tuple(item['name'] for item in specs) != TOOL_NAMES:
        raise ValueError('Forecast prompt/schema contract changed; review required')
    return prompt, specs


def validate_arguments(spec, arguments):
    schema = spec['parameters']
    if set(arguments)-set(schema['properties']):
        raise ValueError('Unknown tool argument')
    if set(schema.get('required',[]))-set(arguments):
        raise ValueError('Missing required tool argument')
    for key,value in arguments.items():
        rule = schema['properties'][key]
        if rule['type']=='string' and not isinstance(value,str):
            raise ValueError(key+' must be a string')
        if rule['type']=='number' and (isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value)):
            raise ValueError(key+' must be finite')
        if 'enum' in rule and value not in rule['enum']:
            raise ValueError(key+' has an unsupported value')
        if key in {'ym','start','end'} and not re.fullmatch(r'\d{4}-(?:0[1-9]|1[0-2])',value):
            raise ValueError(key+' must be YYYY-MM')
        if key=='mult' and not 0 <= value <= 3:
            raise ValueError('Scenario multiplier must be between zero and three')
        if key=='event_id' and not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',value):
            raise ValueError('Invalid event identifier')
    if 'start' in arguments and 'end' in arguments and arguments['start']>arguments['end']:
        raise ValueError('Start month is later than end month')


class ForecastEngineSession:
    def __init__(self, *, run_id=None):
        self.run_id = run_id or 'forecast-'+uuid4().hex
        if not re.fullmatch(r'forecast-[a-f0-9]{32}',self.run_id):
            raise ValueError('Invalid private forecast run id')
        self.root = PROJECT/'runtime/forecast-engine-runs'/self.run_id
        self.results = []
        self.lock = asyncio.Lock()
        self.started = time.monotonic()
        self.calls = 0

    def prepare(self):
        if self.root.exists():
            return
        self.root.mkdir(parents=True)
        shutil.copytree(ENGINE,self.root/'engine',ignore=shutil.ignore_patterns('__pycache__','*.pyc','market.db','outputs'))
        (self.root/'README.md').write_text('Private forecast task: '+self.run_id+'\nContains source/data snapshot, isolated DB and tool receipts. Keep for evidence/recovery. No source data or original DB is modified.\n',encoding='utf-8')

    async def call(self, name, arguments):
        specs = {s['name']:s for s in prompt_and_specs()[1]}
        if name not in specs: raise ValueError('Unsupported tool')
        validate_arguments(specs[name],arguments)
        async with self.lock:
            if self.calls>=8 or time.monotonic()-self.started>=175:
                raise RuntimeError('Forecast task call/time budget exhausted')
            self.calls+=1
            await asyncio.to_thread(self.prepare)
            request=self.root/'request.json'
            request.write_text(json.dumps(dict(name=name,arguments=arguments),ensure_ascii=False,allow_nan=False),encoding='utf-8')
            import os
            env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',HF_HUB_OFFLINE='1',OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2')
            process=await asyncio.create_subprocess_exec(sys.executable,'-B',str(PROJECT/'scripts/forecast_engine_worker.py'),
                '--request',str(request),cwd=PROJECT,env=env,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
            try:
                stdout,stderr=await asyncio.wait_for(process.communicate(),timeout=max(1,175-(time.monotonic()-self.started)))
            except BaseException:
                if process.returncode is None:
                    process.kill(); await process.wait()
                raise
            if process.returncode:
                raise RuntimeError('Forecast worker failed; inspect task receipt')
            result=json.loads(stdout.decode('utf-8'))
            receipt=dict(seq=len(self.results)+1,name=name,arguments=arguments,result=result,
                         run_id=self.run_id,completed_at=datetime.now().astimezone().isoformat())
            self.results.append(receipt)
            (self.root/f'tool-{receipt["seq"]}.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
            return result


class ForecastEngineTool(ToolBase):
    is_concurrency_safe=False
    is_read_only=False  # Calculations create private evidence/forecast archives.

    def __init__(self, spec, session):
        self.name=spec['name']; self.description=spec['description']
        self.input_schema=deepcopy(spec['parameters']); self.session=session

    async def check_permissions(self, tool_input, context):
        return PermissionDecision(behavior=PermissionBehavior.ALLOW,message='Only this forecast task workspace is written; source data and event coefficients are unchanged.')

    async def call(self, **arguments):
        try:
            result=await self.session.call(self.name,arguments)
        except Exception as exc:
            result=dict(ok=False,error=type(exc).__name__+': '+str(exc)[:350])
        return ToolChunk(content=[TextBlock(text=json.dumps(result,ensure_ascii=False,allow_nan=False))])


def tools_for_session(session):
    return [ForecastEngineTool(spec,session) for spec in prompt_and_specs()[1]]


def render_answer(session, question):
    receipts=[r for r in session.results if r['result'].get('ok')]
    if not receipts:
        return '本轮没有成功的预测工具回执，无法提供预测数值。请检查任务错误后重试。',False
    if HYPOTHETICAL.search(question) and not any(r['name']=='adjust_scenario' for r in receipts):
        return '假设推演尚未通过 adjust_scenario 重算，本轮不提供假设影响数值。',False
    if re.search(r'预测|2027|明年',question) and not any(r['name'] in {'run_forecast','adjust_scenario','explain_forecast'} for r in receipts):
        return '本轮只有历史指标回执，尚未执行预测；不把历史数据当作未来预测。',False
    chosen=receipts[-1]
    data=chosen['result']['data']
    label='模拟占位数据，仅供内部管道自检，禁止对外引用。' if data['data_status']=='synthetic' else '真实数据尚未通过完整回测与业务审核，禁止对外引用。'
    lines=['## 市场预测工具结果',label,
           f"口径：零售；单位：辆；情景：{data['scenario']}；数据截止：{data['data_cutoff']}；模型：{data['model_version']}。"]
    if 'annual_by_powertrain' in data:
        lines+=['| 2027 年序列 | P10 | P50 | P90 |','|---|---:|---:|---:|']
        for name,values in data['annual_by_powertrain'].items():
            lines.append(f"| {name} | {values['p10']:,.0f} | {values['p50']:,.0f} | {values['p90']:,.0f} |")
        lines.append(f"新能源渗透率 P50：{data['y2027_nev_penetration_pct']:.1f}%。")
        if 'delta' in data:
            lines.append(f"事件 {data['event_id']} 的基准系数改为 {data['new_mult_base']} 后，2027 年总量 P50 变化 {data['delta']:+,.0f} 辆；只调整本项假设，未修改原始事件库。")
        lines.append('年度上下界沿用迁移引擎的月度分位数加总方法，尚不代表已校准的年度覆盖率。')
    elif 'p50' in data:
        lines.append(f"{data['ym']} / {data['powertrain']}：P50 {data['p50']:,.0f}，P10 {data['p10']:,.0f}，P90 {data['p90']:,.0f}。")
    elif 'data' in data:
        lines+=['| 月份 | 数值 |','|---|---:|']
        lines += [f'| {month} | {value:,.0f} |' for month,value in data['data'].items()]
        lines.append('历史指标不附带预测区间，未把历史值包装为预测。')
    chain=data.get('adjustment_chain',[])
    if chain:
        assumptions={(r['event_id'],r['factor']) for r in chain}
        lines.append('关键假设（工具回执）：'+'；'.join(f'{name} × {factor}' for name,factor in sorted(assumptions)))
    else: lines.append('关键假设：本回执未提供完整事件链，不补写原因。')
    lines+=['决策含义：可用于核查排产、动力产品线或预算的情景敏感性；当前数据/验收状态不支持形成正式排产或投资结论。',
            '不确定性：真实数据版本、事件系数评审、年度区间覆盖及发布时间可得性仍需核验。',
            f'任务回执：{session.run_id} / tool-{chosen["seq"]}；输入 SHA256：{data["input_sha256"]}。']
    return '\n\n'.join(lines),True


async def run_forecast_engine_agent(config, question):
    from agents.forecast_engine_agent import build_forecast_engine_agent
    from utils.model_routing import route_model
    config=route_model(config,question=question,requested=config.get('_requested_provider'))
    session=ForecastEngineSession()
    agent=build_forecast_engine_agent(config,session)
    # Model chooses tools and qualitative interpretation; only engine receipts render numbers.
    reply=await asyncio.wait_for(agent.reply(UserMsg(name='业务用户',content=question)),timeout=180)
    answer,passed=render_answer(session,question)
    explanation=validated_explanation(reply.get_text_content())
    if passed and explanation:
        # Keep model's task-specific interpretation; numeric facts remain engine-rendered.
        answer=answer.split('\n\n关键假设（工具回执）')[0] if '\n\n关键假设（工具回执）' in answer else answer.split('\n\n关键假设：')[0]
        answer+='\n\n'+explanation+'\n\n任务回执：'+session.run_id+'。'
    elif passed:
        answer+='\n\n助手解释未通过结构与数值边界校验；以上为数学工具事实，专业解释仍待复核。'
    events=[dict(name=r['name'],status='success' if r['result'].get('ok') else 'error',
                 detail=f"run_id={session.run_id}; receipt=tool-{r['seq']}",time=r['completed_at']) for r in session.results]
    return dict(answer=answer,agent='market_strategy',model_provider=config.get('active_provider',''),tool_events=events,
                forecast_engine=dict(run_id=session.run_id,numeric_source='engine_receipts_only',explanation_validated=bool(explanation),external_citation_allowed=False),
                quality=dict(overall_status='待核验' if passed else '阻断',formal_delivery_allowed=False),
                business_status='incomplete',formal_delivery_allowed=False,skill=None,skill_run=None,mcp_plugins={})


def validated_explanation(text):
    """Retain qualitative explanation only; reject copied sample/new numeric claims."""
    labels=('关键假设','决策含义','不确定性提示')
    sections=[]
    for label in labels:
        match=re.search(r'(?:^|\n)[#*\s【]*'+label+r'[】*：:\s]*(.*?)(?=\n\s*(?:#{1,6}\s|【|\*\*[^*]+\*\*)|\Z)',text,re.S)
        if not match: return ''
        body=match.group(1).strip()
        # No numeric additions in the interpretive section, including Chinese quantities.
        if not 8<=len(body)<=1200 or re.search(r'\d|[一二三四五六七八九十百千万]+(?:成|倍|辆|亿元|万元|百分点)',body): return ''
        sections.append('### '+label+'\n'+body)
    return '\n\n'.join(sections)
