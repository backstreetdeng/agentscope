"""Independent, local-only SARIMAX baseline jobs for CHRONOS-003.

The web process does not import statsmodels. Jobs use a child process with an
isolated package directory and read the existing workbook locally. No historical
data is sent to a model provider. The baseline has no external regressors.
"""
from __future__ import annotations

from datetime import datetime
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
from threading import Lock, Thread
from uuid import uuid4

from integrations.chronos2_data import ALL_PROVINCES, PROJECT, SOURCE, describe, read_workbook
from integrations.chronos2_forecast import metrics, next_month, validate as validate_chronos

OUTPUTS = PROJECT / 'outputs' / 'chronos-003'
DEPENDENCIES = PROJECT / 'runtime' / 'sarimax-deps'
WORKER = PROJECT / 'scripts' / 'sarimax_worker.py'
MODEL_NAME = 'SARIMAX(0,1,1)(0,1,1,12)'


def validate(payload):
    # An exogenous input is never silently ignored. It requires a separate,
    # future, explicitly validated implementation and business assumptions.
    if isinstance(payload, dict) and payload.get('profile') == 'gd_oil':
        args = validate_chronos({k:v for k,v in payload.items() if k != 'profile'})
        if args['province'] != '广东' or args['energy'] != '插电式混合动力' or args['horizon'] > 12:
            raise ValueError('油价试点仅支持广东插混及未来1—12月。')
        return dict(args, profile='gd_oil')
    return validate_chronos(payload)


def available():
    return (DEPENDENCIES / 'statsmodels' / '__init__.py').is_file() and (DEPENDENCIES / 'patsy' / '__init__.py').is_file()


def status():
    result = describe(read_workbook())
    result.update(model_available=available(), region_all=ALL_PROVINCES)
    return result


def predict(history, horizon):
    """Fit a fixed seasonal specification using only the supplied past."""
    import numpy as np
    from statsmodels.tsa.statespace.sarimax import SARIMAX

    values = np.asarray(history, dtype=float)
    if values.ndim != 1 or len(values) < 48 or not np.isfinite(values).all() or (values < 0).any():
        raise ValueError('需要至少 48 个月有效、非负的连续销量。')
    if np.ptp(values) == 0:
        raise ValueError('历史销量为恒定序列，无法估计该统计模型。')
    scale = float(np.mean(values[-min(60, len(values)):]))
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError('近期销量不足以估计统计模型。')
    fitted = SARIMAX(values / scale, order=(0, 1, 1), seasonal_order=(0, 1, 1, 12),
                     enforce_stationarity=False, enforce_invertibility=False).fit(disp=False, maxiter=100)
    if not bool(fitted.mle_retvals.get('converged')):
        raise ValueError('SARIMAX 拟合未收敛，未生成预测。')
    pred = fitted.get_forecast(steps=horizon)
    means = np.asarray(pred.predicted_mean, dtype=float) * scale
    intervals = np.asarray(pred.conf_int(alpha=0.20), dtype=float) * scale
    if (not np.isfinite(means).all() or not np.isfinite(intervals).all()
            or (means < 0).any() or (intervals[:, 1] < means).any()
            or (intervals[:, 0] > means).any()):
        raise ValueError('SARIMAX 预测出现无效值，未发布结果。')
    return [{'p10': max(0.0, float(bounds[0])), 'p50': float(mean),
             'p90': float(bounds[1]), 'lower_clipped': bool(bounds[0] < 0)}
            for mean, bounds in zip(means, intervals)]


def calculate(workbook, payload, predictor=predict):
    args = validate(payload)
    history = workbook.series(args['province'], args['energy'], args['cutoff'])
    if len(history) < 72:
        raise ValueError('连续历史不足 72 个月，无法稳定开展滚动评估。')
    values = [value for _, value in history]
    common = dict(source=SOURCE.name, source_sha256=workbook.source_hash,
                  data_status='real_unvalidated', data_cutoff=history[-1][0],
                  history_start=history[0][0], history_months=len(history),
                  province=args['province'], energy=args['energy'], metric='零售', unit='辆',
                  scenario='基准（无外部变量）', external_citation_allowed=False,
                  model=MODEL_NAME, model_revision='statsmodels-0.15.0',
                  method='固定季节阶数的统计模型；每个回测起点仅拟合该起点之前销量；未加入外部变量',
                  postprocessing='条件 80% 预测区间；负的区间下限截为零；均值为点预测',
                  missing_combination='用户确认已出现月份中缺失组合按零处理，完整缺月不补零',
                  decision_meaning='仅用于内部统计预测和模型比较，业务精度尚待验收。')
    if args['operation'] == 'forecast':
        pred = predictor(values, args['horizon'])
        common['forecast'] = [dict(month=next_month(history[-1][0], i+1), **row)
                              for i, row in enumerate(pred)]
        return common
    # Match Chronos-2's 12 origins, each with 12 future targets.
    records = []
    for i in range(len(history)-23, len(history)-11):
        predicted = predictor(values[:i], 12)
        for j, row in enumerate(predicted):
            records.append(dict(origin=history[i-1][0], month=history[i+j][0],
                                horizon=j+1, actual=values[i+j], seasonal_naive=values[i+j-12], **row))
    common['backtest'] = dict(origins=12, horizon=12, **metrics(records),
        by_horizon={str(h): metrics([r for r in records if r['horizon'] == h]) for h in (1,3,6,12)},
        records=records,
        note='12 个相同起点各预测 12 月；季节基线使用起点前同期值。'
             '使用当前工作簿快照，无法复原历史修订版本。统计区间为模型条件预测区间。')
    return common


def _run_child(args):
    if not available():
        raise ValueError('SARIMAX 独立依赖尚未安装，请按 requirements-sarimax.txt 配置。')
    env = os.environ.copy()
    env['PYTHONPATH'] = str(DEPENDENCIES) + os.pathsep + str(PROJECT)
    env['OPENBLAS_NUM_THREADS'] = '1'
    env['OMP_NUM_THREADS'] = '1'
    env['PYTHONIOENCODING'] = 'utf-8'
    try:
        completed = subprocess.run([sys.executable, '-B', str(WORKER)], input=json.dumps(args, ensure_ascii=False),
                                   capture_output=True, text=True, encoding='utf-8', env=env,
                                   cwd=str(PROJECT), timeout=600, check=False)
    except subprocess.TimeoutExpired:
        raise ValueError('SARIMAX 计算超时，请缩小范围或稍后重试。') from None
    try:
        response = json.loads(completed.stdout)
    except (ValueError, TypeError):
        raise ValueError('SARIMAX 计算进程异常，未生成结果。') from None
    if completed.returncode or not response.get('ok'):
        raise ValueError(str(response.get('error') or 'SARIMAX 计算失败。')[:300])
    return response['result']


def compare_backtests(chronos_job, sarimax_job):
    """Only compare the same task scope, source and forecast-origin targets."""
    if (chronos_job.get('status') != 'completed' or chronos_job.get('operation') != 'backtest'
            or sarimax_job.get('status') != 'completed' or sarimax_job.get('operation') != 'backtest'):
        raise ValueError('请先完成同范围的 Chronos-2 与 SARIMAX 历史回测。')
    c, s = chronos_job.get('data'), sarimax_job.get('data')
    if not isinstance(c, dict) or not isinstance(s, dict):
        raise ValueError('回测结果不完整。')
    keys = ('source_sha256','data_cutoff','history_start','province','energy','metric','unit')
    if any(not c.get(k) or c.get(k) != s.get(k) for k in keys):
        raise ValueError('两个回测的数据版本、截止或范围不同，不能比较。')
    if c.get('model') != 'amazon/chronos-2' or s.get('model') != MODEL_NAME:
        raise ValueError('回测模型不匹配。')
    try:
        cr, sr = c['backtest']['records'], s['backtest']['records']
        def keyed(rows):
            out = {(r['origin'],r['month'],r['horizon']):r for r in rows}
            if len(out) != len(rows): raise ValueError('回测包含重复起点与目标月。')
            return out
        cm, sm = keyed(cr), keyed(sr)
        if len(cm) != 144 or set(cm) != set(sm):
            raise ValueError('回测起点或预测期不一致，不能比较。')
        for key in cm:
            if cm[key]['actual'] != sm[key]['actual'] or cm[key]['seasonal_naive'] != sm[key]['seasonal_naive']:
                raise ValueError('回测实际值或季节基线不一致，不能比较。')
        rows = []
        for horizon in (1,3,6,12):
            cmetric = metrics([r for r in cr if r['horizon'] == horizon])
            smetric = metrics([r for r in sr if r['horizon'] == horizon])
            rows.append(dict(horizon=horizon, observations=cmetric['observations'],
                chronos={k:cmetric[k] for k in ('mae','wape_pct','interval_coverage_pct')},
                sarimax={k:smetric[k] for k in ('mae','wape_pct','interval_coverage_pct')},
                seasonal_naive_mae=sum(abs(r['actual']-r['seasonal_naive']) for r in cr if r['horizon'] == horizon) / cmetric['observations'],
                seasonal_naive_wape_pct=cmetric['seasonal_naive_wape_pct']))
    except (KeyError, TypeError, ZeroDivisionError):
        raise ValueError('回测记录不完整，不能比较。') from None
    return {'province':c['province'], 'energy':c['energy'], 'data_cutoff':c['data_cutoff'],
            'source_sha256':c['source_sha256'], 'rows':rows,
            'note':'按同一数据版本及 12 个相同起点比较各预测期；'
                   'Chronos 分位区间与 SARIMAX 条件区间分别评价覆盖，不代表同等校准。'}


class SarimaxJobs:
    def __init__(self):
        self.lock = Lock()
        self.busy = False
        self.jobs = {}

    def start(self, payload):
        args = validate(payload)
        with self.lock:
            if self.busy:
                raise ValueError('SARIMAX 正在计算另一项任务。')
            self.busy = True
            run_id = 'sarimax-' + uuid4().hex
            job = dict(run_id=run_id, status='running', operation=args['operation'],
                       message='正在本机读取销量并计算统计模型。',
                       started_at=datetime.now().astimezone().isoformat())
            self.jobs[run_id] = job
        def work():
            try:
                result = _run_child(args)
                run_dir = OUTPUTS / run_id
                run_dir.mkdir(parents=True, exist_ok=False)
                receipt = dict(run_id=run_id, operation=args['operation'], arguments=args,
                               result=result, completed_at=datetime.now().astimezone().isoformat(),
                               retention='内部回测证据，需人工确认后清理；无外部数据发送。')
                (run_dir / 'manifest.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2,
                                                                 allow_nan=False), encoding='utf-8')
                with self.lock:
                    job.update(status='completed', message='计算完成，仅供内部核验。', data=result)
            except Exception as exc:
                with self.lock:
                    job.update(status='failed', message=f'{type(exc).__name__}: {str(exc)[:300]}')
            finally:
                with self.lock:
                    self.busy = False
        Thread(target=work, daemon=True, name=run_id).start()
        return dict(job)

    def get(self, run_id):
        if not isinstance(run_id, str) or not re.fullmatch(r'sarimax-[a-f0-9]{32}', run_id):
            raise ValueError('无效的统计模型任务编号。')
        with self.lock:
            job = self.jobs.get(run_id)
            if job:
                return dict(job)
        path = OUTPUTS / run_id / 'manifest.json'
        if not path.is_file():
            raise ValueError('未找到统计模型任务。')
        receipt = json.loads(path.read_text(encoding='utf-8'))
        return dict(run_id=run_id, status='completed', operation=receipt['operation'],
                    data=receipt['result'], message='已从本机回执恢复结果。')


SARIMAX_JOBS = SarimaxJobs()
