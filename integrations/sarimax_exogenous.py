"""Local, as-of validated exogenous inputs for SARIMAX; no external network.

Inputs are curated and independently verified records. A current data snapshot
alone does not prove that its historical vintages were available at the time.
This module is not connected to the webpage until real source coverage and
publication-time evidence have been reviewed.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date
import math
import re

from integrations.chronos2_forecast import next_month


def _month(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])',value):
        raise ValueError('月份必须为 YYYY-MM。')
    return value


def _end_of_month(value):
    year, month = map(int,_month(value).split('-'))
    return date(year,month,monthrange(year,month)[1])


def prepare(history, variables, horizon, *, as_of_date):
    """Build as-of training features and approved last-known future scenario.

    History ends at the prediction origin. Variables is a list of dictionaries
    with name, lag, unit and records. Records require period, available_at,
    value, verified=True and vintage_verified=True. The latter means its
    vintage was independently verified, not merely observed in a current file.
    """
    if not isinstance(history,list) or not history or not isinstance(variables,list) or not variables:
        raise ValueError('缺少销量或已核验外部变量。')
    if isinstance(horizon,bool) or not isinstance(horizon,int) or not 1 <= horizon <= 12:
        raise ValueError('外生情景预测期须为 1 至 12 个月。')
    months=[_month(row[0]) for row in history]
    if any(next_month(months[i-1]) != months[i] for i in range(1,len(months))):
        raise ValueError('销量月份必须连续。')
    if any(isinstance(row[1],bool) or not isinstance(row[1],(float,int))
           or not math.isfinite(row[1]) or row[1] < 0 for row in history):
        raise ValueError('销量数据无效。')
    origin=months[-1]
    try:
        deadline=date.fromisoformat(as_of_date)
    except (TypeError,ValueError):
        raise ValueError('必须提供真实预测日期 as_of_date。') from None
    if deadline < _end_of_month(origin):
        raise ValueError('预测日期早于销量截止月末。')
    lookup={}; chosen={}; specs=[]
    for variable in variables:
        if not isinstance(variable,dict) or set(variable) != {'name','lag','unit','records'}:
            raise ValueError('外部变量字段无效。')
        name,lag,unit=variable['name'],variable['lag'],variable['unit']
        if not isinstance(name,str) or not name.strip() or name in lookup or not isinstance(unit,str) or not unit.strip():
            raise ValueError('外部变量名称或单位无效。')
        if isinstance(lag,bool) or not isinstance(lag,int) or not 0 <= lag <= 12:
            raise ValueError('变量滞后期须为 0 至 12 个月。')
        if not isinstance(variable['records'],list): raise ValueError('变量记录无效。')
        vintages={}
        for item in variable['records']:
            if not isinstance(item,dict) or set(item) != {'period','available_at','value','verified','vintage_verified'}:
                raise ValueError('变量记录字段无效。')
            period=_month(item['period'])
            try: published=date.fromisoformat(item['available_at'])
            except (TypeError,ValueError): raise ValueError('变量可获得日期无效。') from None
            value=item['value']
            if (isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value)):
                raise ValueError('变量数值无效。')
            if item['verified'] is not True or item['vintage_verified'] is not True:
                continue
            if period > origin or published > deadline:
                continue
            prior=vintages.get(period)
            if prior and prior[0] == published and prior[1] != value:
                raise ValueError('同日变量版本冲突，无法确认。')
            if not prior or published > prior[0]: vintages[period]=(published,float(value))
        if not vintages: raise ValueError('预测时没有可核验的变量历史。')
        lookup[name]={k:v[1] for k,v in vintages.items()}
        latest_period=max(vintages)
        chosen[name]={'period':latest_period,'value':vintages[latest_period][1],
                      'available_at':vintages[latest_period][0].isoformat(),'unit':unit}
        specs.append((name,lag))
    features=[]
    for ym in months:
        features.append([lookup[name].get(next_month(ym,-lag)) for name,lag in specs])
    start=len(features)
    while start and all(value is not None for value in features[start-1]): start-=1
    if len(features)-start < 48:
        raise ValueError('已核验变量与销量连续重叠不足 48 个月。')
    future=[]; details=[]
    for n in range(1,horizon+1):
        ym=next_month(origin,n); row=[]
        for name,lag in specs:
            period=next_month(ym,-lag)
            if period <= origin:
                value=lookup[name].get(period)
                if value is None: raise ValueError('预测所需的历史变量缺失，无法补零。')
                kind='已核验历史'
            else:
                value=chosen[name]['value']; kind='业务确认：最近已核验水平保持不变'
            row.append(value)
            details.append({'forecast_month':ym,'variable':name,'input_period':period,'kind':kind})
        future.append(row)
    return {'origin':origin,'as_of_date':deadline.isoformat(),'history':history[start:],'training_features':features[start:],
            'future_features':future,'variables':[{'name':n,'lag':l,'unit':chosen[n]['unit']} for n,l in specs],
            'assumptions':chosen,'future_details':details,'discarded_months':start}


def fit(prepared):
    """Fit conditional SARIMAX and return forecasts plus associative coefficients."""
    import numpy as np
    from statsmodels.tsa.statespace.sarimax import SARIMAX
    y=np.asarray([r[1] for r in prepared['history']],dtype=float)
    x=np.asarray(prepared['training_features'],dtype=float)
    future=np.asarray(prepared['future_features'],dtype=float)
    if x.ndim != 2 or x.shape[0] != len(y) or future.ndim != 2 or future.shape[1] != x.shape[1]:
        raise ValueError('外部变量矩阵维度不匹配。')
    scale=float(np.mean(y[-min(60,len(y)):]))
    means=x.mean(axis=0); widths=x.std(axis=0)
    if scale <= 0 or not np.isfinite(scale) or not np.isfinite(x).all() or not np.isfinite(future).all() or (widths == 0).any():
        raise ValueError('销量或变量缺少有效变化，无法估计。')
    model=SARIMAX(y/scale,exog=(x-means)/widths,order=(0,1,1),
                  seasonal_order=(0,1,1,12),enforce_stationarity=False,enforce_invertibility=False)
    result=model.fit(disp=False,maxiter=500)
    solver='lbfgs'
    if not bool(result.mle_retvals.get('converged')):
        # Fixed numerical fallback based only on the supplied training data;
        # never choose a solver/order/lag using held-out prediction errors.
        result=model.fit(disp=False,method='powell',maxiter=500)
        solver='powell'
    if not bool(result.mle_retvals.get('converged')):
        raise ValueError('带变量的 SARIMAX 未收敛。')
    pred=result.get_forecast(steps=len(future),exog=(future-means)/widths)
    forecast=np.asarray(pred.predicted_mean,dtype=float)*scale
    bounds=np.asarray(pred.conf_int(alpha=.2),dtype=float)*scale
    if (not np.isfinite(forecast).all() or not np.isfinite(bounds).all() or (forecast<0).any()
            or (bounds[:,0] > forecast).any() or (forecast > bounds[:,1]).any()):
        raise ValueError('模型预测无效。')
    coefficients=[{'name':item['name'],'lag':item['lag'],'unit':item['unit'],
                   'coefficient':float(result.params[i]*scale/widths[i])}
                  for i,item in enumerate(prepared['variables'])]
    return {'forecast':[{'month':next_month(prepared['origin'],i+1),'mean':float(v),
                         'lower':max(0.0,float(bounds[i,0])),'upper':float(bounds[i,1])}
                        for i,v in enumerate(forecast)],
            'coefficients':coefficients,'assumptions':prepared['assumptions'],'solver':solver,
            'note':'模型条件下的统计关系，非因果；未来变量按业务确认的最近已核验水平保持不变。'}
