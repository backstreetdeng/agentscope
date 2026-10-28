"""Evidence-bound, local-only forecast analysis with no model or network calls.

Numeric facts and the response are calculated on the user's computer. Previous
questions help select a topic; they are never treated as evidence.
"""
from __future__ import annotations

import re
import ipaddress
from urllib.parse import urlparse

from integrations.forecast_insights import analyze, load_result

SCENARIO = re.compile(r'假设|如果|要是|情景(?:推演|重算|调整|比较|对比)|(?:调整|改变|取消).*(?:补贴|政策|价格|系数)')
CAUSE = re.compile(r'为什么|原因|因果|归因|影响因素|导致|何以|为何')
BACKTEST = re.compile(r'回测|误差|不准|准确|精度|偏差|命中率|覆盖率')
SEASON = re.compile(r'季节|规律|旺季|淡季|波动|异常|历史')
SUPPORTED = re.compile(r'销量|市场|趋势|增长|下降|增长率|环比|同比|月份|回测|误差|偏差|精度|准确|覆盖|季节|规律|旺季|淡季|波动|异常|历史|预测|比较|对比|差异|省份|地区|区域|类别|动力|细分|原因|为什么|为何|归因|影响|机会|风险|战略|决策|启示|资源|产能|库存|假设|情景|分析|怎么办')


def allow_loopback_request(peer, host_header, origin=None):
    """Prevent LAN access and cross-origin browser access to business facts."""
    try:
        host = urlparse('//' + host_header)
        if (not ipaddress.ip_address(peer).is_loopback or host.username or host.password
                or host.hostname not in {'localhost', '127.0.0.1', '::1'}):
            return False
        if not origin:
            return True
        page = urlparse(origin)
        return (page.scheme == 'http' and page.hostname == host.hostname
                and (page.port or 80) == (host.port or 80) and not page.username and not page.password)
    except (ValueError, TypeError):
        return False


def _number(value, digits=0):
    return '无法计算' if value is None else f'{value:,.{digits}f}'


def _percent(value):
    return '无法计算（基数为零或缺失）' if value is None else f'{value:+.1f}%'


def _metric_percent(value):
    return '无法计算' if value is None else f'{value:.1f}%'


def factual_summary(data, question):
    """Render facts calculated by Python, including their scope and limitations."""
    scope, forecast, history = data['scope'], data['forecast'], data['history']
    lines = [f"任务范围：{scope['province']} / {scope['energy']}；{scope['metric']}，单位{scope['unit']}；数据截止 {scope['data_cutoff']}；模型 {scope['model']}；情景 {scope['scenario']}。"]
    if history:
        last = history[-1]
        lines.append(f"最近历史实际：{last['month']} 为 {_number(last['actual'])} 辆；环比 {_percent(last['mom_pct'])}，同比 {_percent(last['yoy_pct'])}。")
    if forecast:
        first, last = forecast[0], forecast[-1]
        net = None if not first['p50'] else 100*(last['p50']-first['p50'])/first['p50']
        direction = '上升' if net is not None and net > 0 else '下降' if net is not None and net < 0 else '持平' if net is not None else '无法计算'
        lines.append(f"预测期：{first['month']} 至 {last['month']}，共 {len(forecast)} 个月；首月至末月 P50 {direction} {_percent(net)}。")
        lines.append(f"首月预测：{first['month']} P50 {_number(first['p50'])} 辆，P10–P90 {_number(first['p10'])}–{_number(first['p90'])} 辆。")
        eligible = [row for row in forecast if row['mom_pct'] is not None]
        for row in sorted(eligible, key=lambda x:x['mom_pct'], reverse=True)[:3]:
            lines.append(f"月度变化：{row['month']} P50 {_number(row['p50'])} 辆，环比 {_percent(row['mom_pct'])}（参照{row['mom_reference']}），同比 {_percent(row['yoy_pct'])}（参照{row['yoy_reference']}）。")
        turns = [forecast[i] for i in range(1,len(forecast)-1)
                 if (forecast[i]['p50'] > forecast[i-1]['p50'] and forecast[i]['p50'] > forecast[i+1]['p50'])
                 or (forecast[i]['p50'] < forecast[i-1]['p50'] and forecast[i]['p50'] < forecast[i+1]['p50'])]
        if turns:
            lines.append('预测序列中的局部转折月份：' + '、'.join(row['month'] for row in turns[:4]) + '；这是相邻月份比较，不代表已经验证的市场转折。')
        requested = re.search(r'(?:未来|接下来|往后)\s*(\d{1,2})\s*(?:个)?月', question)
        if requested and int(requested.group(1)) > len(forecast):
            lines.append(f"本任务只有 {len(forecast)} 个月预测，无法分析更长时间范围；请调整预测月数并重新运行。")
    elif re.search(r'未来|预测|趋势|增长最快', question) and not BACKTEST.search(question):
        lines.append('当前任务只有历史回测，没有未来预测；请先运行销量预测。')
    if SEASON.search(question):
        season = data['seasonality']
        if season:
            ordered = sorted(season['monthly_index'].items(), key=lambda item:item[1], reverse=True)
            labels = '；'.join(f'{int(month)} 月 {index:.1f}' for month,index in ordered[:3])
            lines.append(f"历史季节性：基于 {season['years'][0]}–{season['years'][-1]} 完整年度，月度季节指数较高的月份为 {labels}（每年平均月销量设为 100）。")
        else:
            lines.append('完整年度不足或年销量为零，无法计算历史季节性。')
        if data['anomalies']:
            for row in data['anomalies'][:3]:
                lines.append(f"历史波动：{row['month']} 与此前同期中位数相比 {_percent(row['difference_pct'])}；这只标记波动，不证明原因。")
        else:
            lines.append('最近 12 个月没有达到本工具设定阈值的同期异常；这不代表不存在其他异常。')
    if BACKTEST.search(question):
        back = data.get('backtest')
        if back:
            lines.append(f"回测：{back['origins']} 个起点、{back['observations']} 个预测点；MAPE {_metric_percent(back['mape_pct'])}，WAPE {_metric_percent(back['wape_pct'])}，区间覆盖率 {_metric_percent(back['interval_coverage_pct'])}。")
            for row in back['worst_months'][:3]:
                lines.append(f"误差较大的月份：{row['month']}，跨 {row['observations']} 个预测起点的平均绝对百分比误差 {_metric_percent(row['mean_abs_error_pct'])}；该月历史实际环比 {_percent(row['actual_mom_pct'])}、同比 {_percent(row['actual_yoy_pct'])}。这些历史特征不证明误差原因。")
            lines.append('同一实际月份可能对应不同预测起点；月度误差为这些预测点的平均值。')
        else:
            lines.append('当前没有同一地区、类别、截止月与数据版本的回测结果；请先运行匹配的历史回测。')
    comparison = data.get('comparison')
    if comparison:
        lines.append(f"{comparison['kind']}：比较 {comparison['recent_start']}–{comparison['recent_end']} 与上一同期，共 {comparison['groups_eligible']} 个可比范围。")
        seen = set()
        for row in comparison['top'][:3] + comparison['bottom'][:3]:
            key = (row['province'],row['energy'])
            if key in seen: continue
            seen.add(key)
            lines.append(f"历史对比：{row['province']} / {row['energy']}，近 12 个月合计 {_number(row['recent_12m'])} 辆，同比 {_percent(row['yoy_pct'])}。")
    if CAUSE.search(question):
        lines.append('原因边界：当前数据没有价格、政策、竞品等变量；只能描述销量变化，不能确认下降或增长的原因。')
    if re.search(r'战略|决策|启示|机会|风险|资源|产能|库存', question):
        if forecast and forecast[-1]['p50'] < forecast[0]['p50']:
            action = '首末月预测中位数下降，可优先检查库存和排产弹性'
        elif forecast and forecast[-1]['p50'] > forecast[0]['p50']:
            action = '首末月预测中位数上升，可优先检查产能与资源安排'
        else:
            action = '可将预测区间与现有排产、库存及区域资源计划对照'
        lines.append(f'决策参考：{action}，并核查区间上下沿的应对空间；结果未经过业务验收，不宜单独作为经营决策依据。')
    if SCENARIO.search(question):
        lines.append('当前 Chronos-2 尚无假设变量重算接口，不能估算该情景影响；本次不会调用模拟数据代替。')
    lines.append('结果与精度尚待业务验收，不应对外引用。')
    return lines


def validate_request(payload):
    if not isinstance(payload, dict) or set(payload) - {'run_id','related_run_id','question','prior_questions'}:
        raise ValueError('分析请求参数不正确。')
    run_id = payload.get('run_id')
    if not isinstance(run_id, str) or not re.fullmatch(r'chronos-[a-f0-9]{32}', run_id):
        raise ValueError('请先在本页面运行一次销量预测或历史回测。')
    related = payload.get('related_run_id') or None
    if related is not None and (not isinstance(related, str) or not re.fullmatch(r'chronos-[a-f0-9]{32}', related)):
        raise ValueError('关联任务编号无效。')
    question = payload.get('question')
    if not isinstance(question, str) or not 1 <= len(question.strip()) <= 2000:
        raise ValueError('请输入不超过 2000 字的问题。')
    prior = payload.get('prior_questions') or []
    if not isinstance(prior, list) or len(prior) > 6 or any(not isinstance(x,str) or len(x)>2000 for x in prior):
        raise ValueError('对话上下文无效。')
    return {'run_id':run_id, 'related_run_id':related, 'question':question.strip(), 'prior_questions':prior[-6:]}


def answer(payload):
    args = validate_request(payload)
    context = load_result(args['run_id'], args['related_run_id'])
    question = args['question']
    if args['prior_questions'] and (len(question) <= 12 or re.search(r'刚才|前面|上次|那些|这个|它们|其中|呢', question)):
        question = args['prior_questions'][-1] + '\n' + question
    data = analyze(context, question)
    if not SUPPORTED.search(question):
        return {'run_id':args['run_id'],
                'facts':['本机规则分析暂不能理解这个问题。请围绕当前任务询问销量趋势、季节性、地区对比或回测误差。'],
                'analysis':data, 'mode':'local_deterministic',
                'message':'本机程序分析；未调用大模型或外部服务。'}
    return {'run_id':args['run_id'], 'facts':factual_summary(data, question),
            'analysis':data, 'mode':'local_deterministic',
            'message':'本机程序分析；未调用大模型或外部服务。'}
