"""Fixed log-scale constrained SARIMAX for the experimental oil comparison.

Both the baseline and oil variant use identical differencing and constraints.
No order search or held-out-error selection. Fail on invalid outputs rather
than clipping negative point predictions into apparently valid sales.
"""
import math


def fit_log(history, horizon, training=None, future=None):
    import numpy as np
    from statsmodels.tsa.statespace.sarimax import SARIMAX
    y=np.asarray(history,dtype=float)
    if y.ndim!=1 or len(y)<48 or not np.isfinite(y).all() or (y<0).any() or np.ptp(y)==0:
        raise ValueError('对数统计模型需要至少48月有效且变化的非负销量。')
    if isinstance(horizon,bool) or not isinstance(horizon,int) or not 1<=horizon<=12:
        raise ValueError('预测期必须为1—12月。')
    x=xf=None
    if training is not None:
        x=np.asarray(training,dtype=float);xf=np.asarray(future,dtype=float)
        if x.ndim!=2 or x.shape[0]!=len(y) or xf.shape!=(horizon,x.shape[1]) or not np.isfinite(x).all() or not np.isfinite(xf).all():
            raise ValueError('油价特征矩阵无效。')
        mean=x.mean(axis=0);scale=x.std(axis=0)
        if (scale<=1e-10).any():raise ValueError('油价缺少变化。')
        x=(x-mean)/scale;xf=(xf-mean)/scale
    model=SARIMAX(np.log1p(y),exog=x,order=(0,1,1),seasonal_order=(0,1,1,12),
                  enforce_stationarity=True,enforce_invertibility=True)
    result=model.fit(disp=False,maxiter=500)
    solver='lbfgs'
    if not result.mle_retvals.get('converged'):
        result=model.fit(disp=False,maxiter=500,method='powell');solver='powell'
    if not result.mle_retvals.get('converged'):raise ValueError('对数约束模型未收敛。')
    pred=result.get_forecast(steps=horizon,exog=xf)
    mu=np.asarray(pred.predicted_mean);var=np.asarray(pred.var_pred_mean)
    bounds=np.asarray(pred.conf_int(alpha=.2))
    if not np.isfinite(mu).all() or not np.isfinite(var).all() or (var<0).any():raise ValueError('对数预测分布无效。')
    with np.errstate(over='ignore',invalid='ignore'):
        point=np.expm1(mu+var/2)  # conditional mean, not exp(mu) labelled as mean
        interval=np.expm1(bounds)
    if (not np.isfinite(point).all() or not np.isfinite(interval).all()
            or (point<0).any() or (point<interval[:,0]).any() or (point>interval[:,1]).any()):
        raise ValueError('对数反变换结果无效，不发布预测。')
    return dict(forecast=[dict(mean=float(v),lower=max(0.,float(interval[i,0])),upper=float(interval[i,1])) for i,v in enumerate(point)],
        solver=solver,converged=True,parameters=[float(p) for p in result.params],
        note='log1p销量；约束MA可逆；点为对数正态条件均值；80%分位区间；下界截零，未校准。')


def fit(prepared):
    result=fit_log([r[1] for r in prepared['history']],len(prepared['future_features']),
                   prepared['training_features'],prepared['future_features'])
    # Nonlinear model: do not expose log coefficients as vehicles per yuan.
    result.update(coefficients=[],assumptions=prepared['assumptions'])
    return result


def predict(history,horizon):
    result=fit_log(history,horizon)
    return [dict(p10=r['lower'],p50=r['mean'],p90=r['upper']) for r in result['forecast']]
