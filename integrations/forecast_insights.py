"""Deterministic analysis of a version-checked forecast result.

The normalized input is independent of the forecasting implementation. The
current adapter accepts Chronos-2 receipts; future models can supply the same
history, forecast and backtest fields without coupling the analyzer to them.
"""
from __future__ import annotations

from collections import defaultdict
from statistics import mean, median
import re

from integrations.chronos2_data import FORECAST_ENERGIES, read_workbook
from integrations.chronos2_forecast import CHRONOS_JOBS


def _previous(ym, months=1):
    year, month = map(int, ym.split('-'))
    year, month = divmod(year * 12 + month - 1 - months, 12)
    return f'{year:04d}-{month + 1:02d}'


def _change(value, previous):
    return None if previous is None or previous == 0 else (value - previous) / previous * 100


def load_result(run_id, related_run_id=None, *, job_store=CHRONOS_JOBS, workbook_loader=read_workbook):
    job = job_store.get(run_id)
    if job.get('status') != 'completed' or not isinstance(job.get('data'), dict):
        raise ValueError('预测任务尚未完成或没有有效结果，请先运行预测或回测。')
    result = job['data']
    required = ('source_sha256', 'data_cutoff', 'province', 'energy', 'model', 'scenario')
    if any(not result.get(key) for key in required) or not (result.get('forecast') or result.get('backtest')):
        raise ValueError('任务回执不完整，无法绑定分析。')
    workbook = workbook_loader()
    if workbook.source_hash != result['source_sha256']:
        raise ValueError('历史数据文件已变化，无法与原预测的输入版本匹配；请重新运行预测或回测。')
    history = workbook.series(result['province'], result['energy'], result['data_cutoff'])
    if not history or history[-1][0] != result['data_cutoff']:
        raise ValueError('历史数据截止月份与预测回执不一致，请重新运行。')
    combined = dict(result)
    if related_run_id:
        related_job = job_store.get(related_run_id)
        other = related_job.get('data') if related_job.get('status') == 'completed' else None
        keys = ('source_sha256', 'data_cutoff', 'province', 'energy', 'model', 'scenario')
        if not isinstance(other, dict) or any(result.get(k) != other.get(k) for k in keys):
            raise ValueError('关联的预测与回测范围或数据版本不同，请重新运行同范围的任务。')
        if result.get('forecast') and other.get('backtest'):
            combined['backtest'] = other['backtest']
        elif result.get('backtest') and other.get('forecast'):
            combined['forecast'] = other['forecast']
        else:
            raise ValueError('关联任务必须分别为一次预测和一次回测。')
    return {'run_id': run_id, 'related_run_id': related_run_id, 'result': combined, 'history': history, 'workbook': workbook}


def _seasonality(history):
    years = defaultdict(dict)
    for ym, value in history:
        years[ym[:4]][int(ym[5:])] = value
    full = [(year, months) for year, months in sorted(years.items()) if len(months) == 12][-5:]
    ratios = defaultdict(list)
    used = []
    for year, months in full:
        annual_mean = mean(months.values())
        if annual_mean > 0:
            used.append(year)
            for month, value in months.items(): ratios[month].append(value / annual_mean * 100)
    if len(used) < 3: return None
    return {'years': used,
            'monthly_index': {str(month): round(mean(values), 2) for month, values in ratios.items()},
            'method': '每个完整年度的月销量除以该年月均销量，再对最近五个完整年度求均值；100 为年内月均水平'}


def _history_changes(history):
    values = dict(history)
    rows = []
    for ym, value in history[-24:]:
        rows.append({'month': ym, 'actual': value,
                     'mom_pct': _change(value, values.get(_previous(ym))),
                     'yoy_pct': _change(value, values.get(_previous(ym, 12)))})
    return rows


def _forecast_changes(history, forecast):
    actual = dict(history)
    predicted = {}
    rows = []
    for row in forecast:
        ym, value = row['month'], float(row['p50'])
        prev = _previous(ym)
        yoy = _previous(ym, 12)
        previous_value = actual.get(prev, predicted.get(prev))
        year_value = actual.get(yoy, predicted.get(yoy))
        rows.append({'month': ym, 'p10': float(row['p10']), 'p50': value, 'p90': float(row['p90']),
                     'mom_pct': _change(value, previous_value),
                     'mom_reference': '历史实际' if prev in actual else '上月预测',
                     'yoy_pct': _change(value, year_value),
                     'yoy_reference': ('历史实际' if yoy in actual else '去年同期预测' if yoy in predicted else '缺失')})
        predicted[ym] = value
    return rows


def _anomalies(history):
    # Compare last 12 actual months against the median of the same calendar
    # month in the previous five years. This flags differences, not causes.
    values = dict(history)
    rows = []
    for ym, value in history[-12:]:
        prior = [values[_previous(ym, 12*i)] for i in range(1, 6) if _previous(ym, 12*i) in values]
        if len(prior) < 3: continue
        reference = median(prior)
        delta = _change(value, reference)
        if delta is not None and abs(delta) >= 50:
            rows.append({'month': ym, 'actual': value, 'reference_median': reference,
                         'difference_pct': delta, 'reference_years': len(prior)})
    return rows


def _comparison(workbook, cutoff, province, energy, question):
    compare_regions = bool(re.search(r'省份|省之间|各省|哪些省|不同省|各地区|哪些地区|不同地区|各区域|不同区域|地区对比|区域对比|省市|省区|地区差异|区域差异', question))
    selected_regions = [p for p in workbook.provinces if p in question]
    compare_regions |= len(selected_regions) >= 2
    compare_energies = bool(re.search(r'动力.*(?:对比|比较|差异)|细分.*(?:对比|比较|差异)|各.*动力|各类别|各类型|不同.*(?:动力|类别)', question))
    if not (compare_regions or compare_energies): return None
    groups = []
    for region in (selected_regions if len(selected_regions) >= 2 else workbook.provinces) if compare_regions else (province,):
        for category in FORECAST_ENERGIES if compare_energies else (energy,):
            series = workbook.series(region, category, cutoff)
            if len(series) < 24: continue
            recent, previous = sum(v for _, v in series[-12:]), sum(v for _, v in series[-24:-12])
            groups.append({'province': region, 'energy': category,
                           'recent_12m': recent, 'previous_12m': previous,
                           'yoy_pct': _change(recent, previous)})
    valid = [g for g in groups if g['yoy_pct'] is not None]
    valid.sort(key=lambda row: row['yoy_pct'], reverse=True)
    return {'kind': '历史实际对比，不是其他地区或类别的预测',
            'recent_start': _previous(cutoff, 11), 'recent_end': cutoff,
            'previous_start': _previous(cutoff, 23), 'previous_end': _previous(cutoff, 12),
            'top': valid[:5], 'bottom': list(reversed(valid[-5:])),
            'groups_eligible': len(valid), 'zero_baseline_excluded': len(groups)-len(valid)}


def analyze(context, question):
    result, history, workbook = context['result'], context['history'], context['workbook']
    fc = _forecast_changes(history, result.get('forecast') or [])
    backtest = result.get('backtest')
    data = {'schema_version': 'forecast-analysis-v1', 'run_id': context['run_id'],
            'related_run_id': context.get('related_run_id'),
            'scope': {key: result.get(key) for key in ('province','energy','metric','unit','data_cutoff','model','model_revision','scenario','source_sha256')},
            'data_status': result.get('data_status'), 'external_citation_allowed': False,
            'history': _history_changes(history), 'seasonality': _seasonality(history),
            'anomalies': _anomalies(history), 'forecast': fc,
            'comparison': _comparison(workbook, result['data_cutoff'], result['province'], result['energy'], question),
            'limitations': ['本次序列不包含价格、政策、竞争等外部变量，无法确认销量变化的原因。',
                            '当前历史数据是最新工作簿快照，无法核验历史预测时点的数据修订版本。',
                            '结果与回测仍待业务验收；四类合计不含燃料电池。']}
    if backtest:
        records = backtest.get('records', [])
        scored = [dict(origin=r['origin'], month=r['month'], horizon=r['horizon'], actual=r['actual'],
                       predicted=r['p50'], abs_error=abs(r['p50']-r['actual']),
                       abs_error_pct=abs(r['p50']-r['actual'])/r['actual']*100 if r['actual'] else None)
                  for r in records]
        scored.sort(key=lambda x: x['abs_error_pct'] if x['abs_error_pct'] is not None else -1, reverse=True)
        groups = defaultdict(list)
        for row in scored:
            if row['abs_error_pct'] is not None: groups[row['month']].append(row)
        actuals = dict(history)
        worst_months = []
        for month, rows in groups.items():
            actual = actuals.get(month)
            worst_months.append({'month': month, 'observations': len(rows),
                                 'mean_abs_error_pct': mean(r['abs_error_pct'] for r in rows),
                                 'actual_mom_pct': _change(actual, actuals.get(_previous(month))) if actual is not None else None,
                                 'actual_yoy_pct': _change(actual, actuals.get(_previous(month,12))) if actual is not None else None})
        worst_months.sort(key=lambda row: row['mean_abs_error_pct'], reverse=True)
        data['backtest'] = {'origins': backtest.get('origins'), 'horizon': backtest.get('horizon'),
                            'observations': backtest.get('observations'), 'mape_pct': backtest.get('mape_pct'),
                            'wape_pct': backtest.get('wape_pct'), 'interval_coverage_pct': backtest.get('interval_coverage_pct'),
                            'by_horizon': backtest.get('by_horizon'), 'worst_errors': scored[:5], 'worst_months': worst_months[:5],
                            'note': backtest.get('note')}
    return data
