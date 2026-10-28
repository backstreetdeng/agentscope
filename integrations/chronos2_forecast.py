"""Independent Chronos-2 forecast and chronological validation jobs.

Forecasts are computed from a read-only workbook snapshot. They are provisional
internal results, and no pretrained model weights are modified or fine-tuned.
"""
from __future__ import annotations

from datetime import datetime
import importlib.util
import json
from pathlib import Path
import re
from threading import Lock, Thread
from uuid import uuid4

from integrations.chronos2_data import ALL_PROVINCES, PROJECT, SOURCE, describe, read_workbook

MODEL_DIR = PROJECT / 'forecast-engine' / '_models' / 'amazon__chronos-2'
OUTPUTS = PROJECT / 'outputs' / 'chronos-002'
_model = None
_model_lock = Lock()


def model():
    global _model
    with _model_lock:
        if _model is None:
            path = PROJECT / 'forecast-engine' / 'models' / 'm3_chronos.py'
            spec = importlib.util.spec_from_file_location('chronos2_existing_model', path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            # Explicit path: never download or switch to an unrelated cached model.
            _model = module.M3Chronos(model_name=str(MODEL_DIR))
        return _model


def next_month(ym, n=1):
    year, month = map(int, ym.split('-'))
    year, month = divmod(year * 12 + month - 1 + n, 12)
    return f'{year:04d}-{month + 1:02d}'


def metrics(records):
    errors = [abs(row['p50'] - row['actual']) for row in records]
    baseline_errors = [abs(row['seasonal_naive'] - row['actual']) for row in records]
    positives = [(e, row['actual']) for e, row in zip(errors, records) if row['actual'] > 0]
    actual_sum = sum(row['actual'] for row in records)
    return dict(observations=len(records),
                mae=sum(errors)/len(records),
                wape_pct=100*sum(errors)/actual_sum if actual_sum else None,
                seasonal_naive_wape_pct=100*sum(baseline_errors)/actual_sum if actual_sum else None,
                mape_pct=100*sum(e/a for e, a in positives)/len(positives) if positives else None,
                mape_eligible=len(positives), zero_actual_excluded=len(records)-len(positives),
                interval_coverage_pct=100*sum(r['p10'] <= r['actual'] <= r['p90'] for r in records)/len(records))


def calculate(workbook, payload, predictor):
    province, energy = payload['province'], payload['energy']
    history = workbook.series(province, energy, payload.get('cutoff'))
    if len(history) < 30:
        raise ValueError('连续历史数据不足 30 个月，无法计算。')
    values = [v for _, v in history]
    operation = payload['operation']
    common = dict(source=SOURCE.name, source_sha256=workbook.source_hash, data_status='real_unvalidated',
                  data_cutoff=history[-1][0], history_start=history[0][0], history_months=len(history),
                  province=province, energy=energy, metric='零售', unit='辆',
                  scenario='基准（未叠加事件系数）', external_citation_allowed=False,
                  model='amazon/chronos-2', model_revision='unknown',
                  method='预训练零样本推理，历史数据作为上下文，未进行再训练',
                  postprocessing='沿用现有模型封装：每月输出下限为 1 辆',
                  missing_combination='用户确认已出现月份中缺失组合按零处理，完整缺月不补零',
                  decision_meaning='用于核查该范围销量的变化与资源规划；请先完成口径及回测审核。')
    if operation == 'forecast':
        horizon = payload['horizon']
        predicted = predictor.predict(values, horizon)
        common['forecast'] = [dict(month=next_month(history[-1][0], i+1),
                                   p10=float(predicted[0.1][i]), p50=float(predicted[0.5][i]),
                                   p90=float(predicted[0.9][i])) for i in range(horizon)]
    else:
        # 12 rolling origins, 1-12 months each. At each origin the predictor sees
        # only data available on/before that origin; no later training inputs.
        horizon, origins = 12, 12
        if len(history) < 24 + horizon + origins - 1:
            raise ValueError('连续历史数据不足以执行 12 个滚动起点、12 个月回测。')
        records = []
        for i in range(len(history) - horizon - origins + 1, len(history) - horizon + 1):
            predicted = predictor.predict(values[:i], horizon)
            for j in range(horizon):
                actual = values[i+j]
                lo, mid, hi = (float(predicted[q][j]) for q in (0.1, 0.5, 0.9))
                records.append(dict(origin=history[i-1][0], month=history[i+j][0], horizon=j+1,
                                    actual=actual, p10=lo, p50=mid, p90=hi,
                                    seasonal_naive=values[i+j-12]))
        overall = metrics(records)
        # Recompute the 1-6 month reference with its own latest 12 origins;
        # merely slicing the 12-month cohort would omit the most recent origins.
        reference_records = []
        for i in range(len(history) - 6 - origins + 1, len(history) - 6 + 1):
            predicted = predictor.predict(values[:i], 6)
            for j in range(6):
                reference_records.append(dict(origin=history[i-1][0], month=history[i+j][0], horizon=j+1,
                                              actual=values[i+j], p10=float(predicted[0.1][j]),
                                              p50=float(predicted[0.5][j]), p90=float(predicted[0.9][j]),
                                              seasonal_naive=values[i+j-12]))
        common['backtest'] = dict(origins=origins, horizon=horizon, **overall,
                                  by_horizon={str(h): metrics([r for r in records if r['horizon'] == h]) for h in (1, 3, 6, 12)},
                                  reference_1_6=metrics(reference_records), reference_1_6_records=reference_records,
                                  records=records,
                                  note='12 个起点分别预测未来 12 个月，季节基线采用起点前同期值。1–6 个月参考门槛单独使用可用的最近 12 个起点；两个评估窗口不同。相同实际月份可被不同起点重复预测；覆盖率按预测点计算。使用当前工作簿历史快照，无法核验当时数据修订版本；仅供内部回测，不代表业务验收。')
    return common


def validate(payload):
    if not isinstance(payload, dict) or set(payload) - {'operation', 'province', 'energy', 'cutoff', 'horizon'}:
        raise ValueError('预测参数不正确。')
    operation = payload.get('operation')
    if operation not in {'forecast', 'backtest'}: raise ValueError('不支持的操作。')
    if not isinstance(payload.get('province'), str) or not isinstance(payload.get('energy'), str):
        raise ValueError('请选择省份与动力类别。')
    horizon = payload.get('horizon', 6)
    if isinstance(horizon, bool) or not isinstance(horizon, int) or not 1 <= horizon <= 24:
        raise ValueError('预测月数须为 1 至 24 的整数。')
    return dict(operation=operation, province=payload['province'], energy=payload['energy'],
                cutoff=payload.get('cutoff') or None, horizon=horizon)


def status():
    data = describe(read_workbook())
    data.update(model_available=(MODEL_DIR/'model.safetensors').is_file() and (MODEL_DIR/'config.json').is_file(),
                region_all=ALL_PROVINCES)
    return data


class ChronosJobs:
    def __init__(self):
        self.lock = Lock()
        self.busy = False
        self.jobs = {}

    def start(self, payload):
        args = validate(payload)
        with self.lock:
            if self.busy: raise ValueError('Chronos-2 正在计算另一项任务，请完成后再试。')
            self.busy = True
            run_id = 'chronos-' + uuid4().hex
            job = dict(run_id=run_id, status='running', operation=args['operation'],
                       message='正在读取历史数据和计算，首次加载模型可能需要较长时间。',
                       started_at=datetime.now().astimezone().isoformat())
            self.jobs[run_id] = job
        def work():
            try:
                wb = read_workbook()
                # Validate history before loading the large model.
                wb.series(args['province'], args['energy'], args['cutoff'])
                result = calculate(wb, args, model())
                run_dir = OUTPUTS / run_id
                run_dir.mkdir(parents=True, exist_ok=False)
                receipt = dict(run_id=run_id, operation=args['operation'], arguments=args, result=result,
                               completed_at=datetime.now().astimezone().isoformat(),
                               retention='内部计算证据，需人工确认后清理；不含模型权重。')
                (run_dir/'manifest.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
                with self.lock: job.update(status='completed', message='计算完成，结果仅供内部核验。', data=result)
            except Exception as exc:
                with self.lock: job.update(status='failed', message=f'{type(exc).__name__}: {str(exc)[:350]}')
            finally:
                with self.lock: self.busy = False
        Thread(target=work, daemon=True, name=run_id).start()
        return dict(job)

    def get(self, run_id):
        if not re.fullmatch(r'chronos-[a-f0-9]{32}', run_id): raise ValueError('无效的预测任务编号。')
        with self.lock:
            job = self.jobs.get(run_id)
            if job: return dict(job)
        path = OUTPUTS / run_id / 'manifest.json'
        if not path.is_file(): raise ValueError('未找到预测任务；服务重启可能中断未完成的任务。')
        receipt = json.loads(path.read_text(encoding='utf-8'))
        return dict(run_id=run_id, status='completed', operation=receipt['operation'], data=receipt['result'],
                    message='已从本地回执恢复结果。')


CHRONOS_JOBS = ChronosJobs()
