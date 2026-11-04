"""Internal current-snapshot oil experiment, independent of strict vintage API.

Fixed lag, fixed SARIMAX order and identical training starts for all comparators.
No network, no changes to pretrained weights or original forecasts.
"""
from __future__ import annotations
import calendar
from datetime import date

from integrations.chronos2_forecast import next_month, metrics
from integrations.gd_oil import load
from integrations.oil_log_model import fit

MODEL = 'SARIMAX + 广东92号月均油价（内部快照试验）'
START = '2020-04'  # Common sample for fixed lag 1 and lag 3 sensitivity.


def inputs(history, monthly, horizon, lag=1):
    if lag not in (1, 3) or not history or not 1 <= horizon <= 12:
        raise ValueError('油价试验仅支持固定滞后 1/3 月、未来 1—12 月。')
    origin = history[-1][0]
    deadline = origin + f'-{calendar.monthrange(*map(int, origin.split("-")))[1]:02d}'
    known = {r['period']: r['value'] for r in monthly
             if r['period'] <= origin and r['available_at'] <= deadline}
    if origin not in known:
        raise ValueError('销量截止月油价缺失，不补零。')
    history = [r for r in history if r[0] >= START]
    if len(history) < 48 or any(next_month(history[i-1][0]) != history[i][0] for i in range(1,len(history))):
        raise ValueError('共同连续训练历史不足 48 月。')
    try:
        training = [[known[next_month(ym, -lag)]] for ym, _ in history]
        future = [[known[next_month(origin, i-lag)] if i <= lag else known[origin]]
                  for i in range(1,horizon+1)]
    except KeyError:
        raise ValueError('油价训练或预测特征缺失。') from None
    return dict(history=history, training_features=training, future_features=future,
                origin=origin, variables=[dict(name='广东92号最高零售价月均',lag=lag,unit='元/升')],
                assumptions={'oil92':dict(period=origin,value=known[origin],lag=lag,
                    scenario='未来未知月份按起点最近月均价保持不变')})


def rows(prediction):
    return [dict(p10=r['lower'],p50=r['mean'],p90=r['upper']) for r in prediction['forecast']]


def calculate(workbook, args, *, snapshot=None, fitter=fit, baseline=None, chronos=None):
    if args['province'] != '广东' or args['energy'] != '插电式混合动力':
        raise ValueError('油价试点仅开放广东插电式混合动力（含增程）。')
    if args['horizon'] > 12:
        raise ValueError('油价试验预测月数最多 12。')
    snapshot = load() if snapshot is None else snapshot
    history = [r for r in workbook.series(args['province'],args['energy'],args.get('cutoff')) if r[0] >= START]
    if len(history) < 72:
        raise ValueError('共同历史不足 72 月，暂不能运行本试点。')
    common = dict(profile='gd_oil',model=MODEL,model_revision='log-constrained-v2-lag1-statsmodels-0.15.0',
        source='月度销量-省份.xlsx',source_sha256=workbook.source_hash,
        province=args['province'],energy=args['energy'],metric='零售',unit='辆',
        history_start=history[0][0],history_months=len(history),data_cutoff=history[-1][0],
        scenario='基准：未来油价最近水平不变；滞后1月',data_status='exploratory_snapshot',
        external_citation_allowed=False,oil_hashes=snapshot['hashes'],
        method='v2：log1p销量、约束可逆的固定阶数SARIMAX；固定滞后；当前快照试验，非因果；已观察旧回测，不是独立留出验证',
        postprocessing='对数正态条件均值与80%分位区间；区间下界截零，未完成校准',
        missing_combination='沿用已确认销量口径；油价缺失拒绝计算',
        decision_meaning='油价v2可完成数值计算，但本试点中长期误差过大，不建议用于正式业务预测；仅用于内部研究。',
                limitations=[snapshot['limitation'],'销量历史修订版本无法核实。','广东油价不能替代全国油价。','v2已参考旧回测失败作修订；当前起点属于开发验证，不是独立留出样本。'])
    if args['operation']=='forecast':
        result=fitter(inputs(history,snapshot['monthly'],args['horizon']))
        common.update(forecast=[dict(month=next_month(history[-1][0],i+1),**r) for i,r in enumerate(rows(result))],
                      coefficients=result['coefficients'],assumptions=result['assumptions'])
        return common
    if baseline is None:
        from integrations.oil_log_model import predict as baseline
    if chronos is None:
        from integrations.chronos2_forecast import model
        chronos=model()
    records={k:[] for k in ('oil_lag1','oil_lag3','sarimax','chronos')}
    failures=[]
    solvers=[]
    for i in range(len(history)-23,len(history)-11):
        past=history[:i]
        def oil(lag):
            result=fitter(inputs(past,snapshot['monthly'],12,lag))
            solvers.append(dict(origin=past[-1][0],lag=lag,solver=result.get('solver','test')))
            return rows(result)
        def cpredict():
            cp=chronos.predict([v for _,v in past],12)
            return [dict(p10=float(cp[.1][j]),p50=float(cp[.5][j]),p90=float(cp[.9][j])) for j in range(12)]
        for key,call in dict(oil_lag1=lambda:oil(1),oil_lag3=lambda:oil(3),
                             sarimax=lambda:baseline([v for _,v in past],12),chronos=cpredict).items():
            try:
                pred=call()
            except ValueError as exc:
                failures.append(dict(model=key,origin=past[-1][0],error=str(exc)))
                continue
            for j,row in enumerate(pred):
                records[key].append(dict(origin=past[-1][0],month=history[i+j][0],horizon=j+1,
                    actual=history[i+j][1],seasonal_naive=history[i+j-12][1],**row))
    # Report failures, then use the identical intersection for scored comparison.
    # This is conditional performance, not a claim that failed origins passed.
    common_origins=set.intersection(*[{r['origin'] for r in v} for v in records.values()])
    if not common_origins:
        raise ValueError('没有四模型均成功的回测起点；油价模型未通过稳定性验证。')
    attempted_scores={k:dict(successful_origins=len({r['origin'] for r in v}),attempted_origins=12) for k,v in records.items()}
    records={k:[r for r in v if r['origin'] in common_origins] for k,v in records.items()}
    def score(recs):
        return dict(**metrics(recs), by_horizon={str(h):metrics([r for r in recs if r['horizon']==h]) for h in (1,3,6,12)})
    common.update(failures=failures,stability=attempted_scores,solvers=solvers,
                  stability_passed=not failures,scored_origins=sorted(common_origins))
    common['backtest']=dict(origins=len(common_origins),attempted_origins=12,horizon=12,records=records['oil_lag1'],
        note=f'四模型共同历史自2020-04开始；尝试12起点，共同成功{len(common_origins)}起点，各预测12月。失败见稳定性记录；评分仅代表成功交集，不代表完整回测通过。滞后3月仅敏感性对照，不按回测结果自动选优。未来油价始终在各起点冻结。'+ ' '.join(common['limitations']),
        **score(records['oil_lag1']))
    common['benchmark']={k:dict(records=v,**score(v)) for k,v in records.items()}
    common['recommendation']='本试点不建议启用油价预测：数值成功不代表预测可靠；模型修订后仍需独立留出验证。'
    return common
