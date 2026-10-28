"""Forecast-only DeepSeek analysis with a fail-closed outbound boundary.

Only completed future forecast rows and enumerated forecast metadata are
serialized. Historical series, backtest records, free-form questions and
conversation history never enter the outbound request.
"""
from __future__ import annotations

import json
import math
import re

import httpx
from dotenv import dotenv_values

from integrations.chronos2_data import ALL_PROVINCES, FORECAST_ENERGIES, FOUR_TYPES, PROJECT
from integrations.chronos2_forecast import CHRONOS_JOBS, next_month
from integrations.forecast_insights import load_result

DESTINATION = 'https://api.deepseek.com/chat/completions'
MODELS = {'flash': 'deepseek-v4-flash', 'pro': 'deepseek-v4-pro'}
REGIONS = frozenset(('上海','云南','内蒙古','北京','吉林','四川','天津','宁夏',
                     '安徽','山东','山西','广东','广西','新疆','江苏','江西','河北',
                     '河南','浙江','海南','湖北','湖南','甘肃','福建','西藏','贵州',
                     '辽宁','重庆','陕西','青海','黑龙江', ALL_PROVINCES))
INTENTS = {
    'strategy': '依据预测区间分析资源安排、机会和风险，提出审慎的业务建议。',
    'trend': '分析未来预测序列的趋势、波动和可能的业务影响。',
    'risk': '依据预测区间分析不确定性和应对措施。',
}
SYSTEM = ('你是乘用车市场预测分析助手。输入仅包含模型预测，不包含历史实际、'
          '回测、政策、价格或竞争证据。只能根据输入预测做审慎的定性业务判断；'
          '不要编造原因、历史事实、外部证据或假设推演结果。明确预测不等于事实、'
          '区间不构成保证。不要提及具体影响因素、节日或季节性；不要使用阿拉伯数字、'
          '数字编号、月份或百分比，所有数字由本机页面展示。'
          '用中文简洁回答，并区分观察、风险和行动建议。')
UNSUPPORTED_CLAIMS = re.compile(r'[0-9０-９%％]|春节|节假日|节日|季节性|季节规律|'
                                r'政策|补贴|竞品|竞争对手|降价|涨价|价格|宏观经济|'
                                r'消费信心|经济增长|利率|油价|销量实际')


def validate_request(payload):
    if not isinstance(payload, dict) or set(payload) != {'run_id', 'intent', 'model'}:
        raise ValueError('外部分析仅接受任务编号、固定分析类型和模型选项。')
    if not isinstance(payload['run_id'], str) or not re.fullmatch(r'chronos-[a-f0-9]{32}', payload['run_id']):
        raise ValueError('请先运行销量预测。')
    if (not isinstance(payload['intent'], str) or not isinstance(payload['model'], str)
            or payload['intent'] not in INTENTS or payload['model'] not in MODELS):
        raise ValueError('外部分析类型或模型无效。')
    return payload


def build_forecast_projection(job, checked_result):
    """Project and validate the only business data allowed to leave the host."""
    if job.get('status') != 'completed' or job.get('operation') != 'forecast':
        raise ValueError('仅已完成的未来销量预测可用于外部分析。')
    result = job.get('data')
    if not isinstance(result, dict) or result is not checked_result:
        raise ValueError('预测回执未通过本机数据版本校验。')
    region, energy = result.get('province'), result.get('energy')
    if (not isinstance(region, str) or not isinstance(energy, str)
            or region not in REGIONS or energy not in FORECAST_ENERGIES + (FOUR_TYPES,)):
        raise ValueError('预测范围未通过枚举校验。')
    if result.get('metric') != '零售' or result.get('unit') != '辆':
        raise ValueError('预测口径或单位无效。')
    if result.get('model') != 'amazon/chronos-2' or result.get('scenario') != '基准（未叠加事件系数）':
        raise ValueError('预测模型或情景未通过校验。')
    cutoff = result.get('data_cutoff')
    if not isinstance(cutoff, str) or not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', cutoff):
        raise ValueError('预测截止月份无效。')
    rows = result.get('forecast')
    if not isinstance(rows, list) or not 1 <= len(rows) <= 24:
        raise ValueError('预测序列无效。')
    safe = []
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict) or set(row) != {'month', 'p10', 'p50', 'p90'}:
            raise ValueError('预测行包含未知字段或缺少必要字段。')
        if row['month'] != next_month(cutoff, index):
            raise ValueError('预测月份不是截止后的连续未来月份。')
        vals = [row[k] for k in ('p10', 'p50', 'p90')]
        if any(isinstance(v, bool) or not isinstance(v, (int, float))
               or not math.isfinite(v) or v < 0 for v in vals) or not vals[0] <= vals[1] <= vals[2]:
            raise ValueError('预测分位数无效。')
        safe.append({'month': row['month'], 'p10': vals[0], 'p50': vals[1], 'p90': vals[2]})
    return {'region': region, 'energy': energy, 'metric': '零售预测', 'unit': '辆',
            'scenario': '基准（未叠加事件系数）', 'forecast': safe}


def answer(payload):
    args = validate_request(payload)
    job = CHRONOS_JOBS.get(args['run_id'])
    # load_result checks that the source workbook still matches this receipt;
    # its history and workbook remain on the local side of the boundary.
    checked = load_result(args['run_id'])
    # Each store lookup returns a shallow copy, but its result object may be
    # reloaded from disk independently. Compare only locally, never serialize.
    if job.get('data') != checked['result']:
        raise ValueError('预测回执发生变化，请重新运行预测。')
    return _send_validated(job, job.get('data'), args['intent'], args['model'])


def _send_validated(job, checked_result, intent, model):
    projection = build_forecast_projection(job, checked_result)
    # A second structural gate immediately before HTTP protects this boundary
    # against later accidental additions to the projection.
    if set(projection) != {'region','energy','metric','unit','scenario','forecast'}:
        raise ValueError('出域质量门拒绝了未知字段。')
    if (projection['region'] not in REGIONS or projection['energy'] not in FORECAST_ENERGIES + (FOUR_TYPES,)
            or projection['metric'] != '零售预测' or projection['unit'] != '辆'
            or projection['scenario'] != '基准（未叠加事件系数）'
            or intent not in INTENTS or model not in MODELS):
        raise ValueError('出域质量门拒绝了不允许的内容。')
    for row in projection['forecast']:
        if set(row) != {'month','p10','p50','p90'}:
            raise ValueError('出域质量门拒绝了预测以外的数据。')
    # The shell may contain an older credential. Read the user-designated
    # project file directly instead of inheriting an unrelated process value.
    key = dotenv_values(PROJECT / '.env').get('DASHSCOPE_API_KEY')
    if not key:
        raise ValueError('未配置 DeepSeek API 密钥。')
    body = {'model': MODELS[model], 'stream': False,
            'messages': [{'role':'system', 'content':SYSTEM},
                         {'role':'user', 'content':INTENTS[intent] + '\n' +
                          json.dumps(projection, ensure_ascii=False, allow_nan=False, separators=(',', ':'))}],
            'temperature': 0.3, 'max_tokens': 1400,
            'thinking': {'type':'disabled'}}
    try:
        # Disable environment proxies and redirects: the payload is sent only
        # to the explicitly authorized official HTTPS endpoint.
        with httpx.Client(trust_env=False, follow_redirects=False, timeout=60.0) as client:
            response = client.post(DESTINATION, headers={'Authorization':'Bearer ' + key}, json=body)
        if response.status_code != 200:
            raise ValueError(f'DeepSeek 请求失败（HTTP {response.status_code}），请检查服务和模型配置。')
        message = response.json()['choices'][0]['message']['content']
        if not isinstance(message, str) or not message.strip() or len(message) > 12000:
            raise ValueError('DeepSeek 未返回有效分析。')
        if UNSUPPORTED_CLAIMS.search(message):
            raise ValueError('模型回答含有未经核实的数字或影响因素，已被质量门拦截；请重试。')
    except (httpx.HTTPError, KeyError, IndexError, TypeError, json.JSONDecodeError):
        raise ValueError('DeepSeek 连接或响应失败，请检查网络和模型配置。') from None
    return {'analysis':message.strip(), 'model':MODELS[model], 'mode':'forecast_only_deepseek',
            'message':'仅发送预测区间及范围；历年实际、回测、问题原文和历史对话均未发送。'}
