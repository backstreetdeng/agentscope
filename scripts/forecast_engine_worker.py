"""Private subprocess bridge. Writes only the caller's isolated engine workspace."""
from __future__ import annotations
import argparse
import contextlib
import hashlib
import importlib
import io
import json
from pathlib import Path
import sys
import traceback

PROJECT = Path(__file__).resolve().parents[1]


def execute(engine: Path, name: str, arguments: dict) -> dict:
    sys.path.insert(0, str(engine))
    ingest = importlib.import_module('ingest.ingest')
    tools = importlib.import_module('agent.tools')
    pipeline = importlib.import_module('run_forecast')
    import pandas as pd
    marker = engine / '.initialized'
    if not marker.exists():
        frame = pd.read_csv(ingest.DATA)
        ingest.validate(frame)
        ingest.ingest(frame)
        marker.write_text('CSV snapshot initialized in private task database.\n', encoding='utf-8')
    if name == 'query_indicator':
        data = tools.query_indicator(**arguments)
    elif name == 'run_forecast':
        fc, log, cutoff = pipeline.run_pipeline(**arguments)
        data = forecast_payload(fc, log, cutoff, arguments.get('scenario', 'base'), pipeline.MODEL_VERSION)
    elif name == 'adjust_scenario':
        # Invoke the migrated function itself. All coefficient changes are in memory.
        data = tools.adjust_scenario(**arguments)
        if 'error' not in data:
            events = tools.load_events(pipeline.EVENTS_PATH)
            events.loc[events.event_id == arguments['event_id'], 'mult_base'] = arguments['mult']
            fc, log, cutoff = pipeline.run_pipeline('base', events_override=events, save=False)
            data.update(forecast_payload(fc, log, cutoff, 'base', pipeline.MODEL_VERSION))
            # Store adjusted results only in this task's archive so explain uses them.
            db = importlib.import_module('db')
            conn = db.init_db()
            pipeline.save_runs(conn, fc, log, 'base', cutoff)
            conn.commit(); conn.close()
            data['assumption_persisted_to_source'] = False
    elif name == 'explain_forecast':
        data = tools.explain_forecast(**arguments)
    else:
        raise ValueError('Unsupported forecast tool')
    data.setdefault('model_version', pipeline.MODEL_VERSION)
    data.setdefault('data_cutoff', str(ingest.load_wide().index[-1]))
    data.setdefault('scenario', arguments.get('scenario', 'base'))
    data['source'] = ingest.SOURCE
    data['metric'] = 'retail'
    data['unit'] = '辆'
    data['data_status'] = 'synthetic' if 'SAMPLE' in ingest.SOURCE.upper() or 'PLACEHOLDER' in ingest.SOURCE.upper() else 'real_unvalidated'
    # Formal release needs separately reviewed real-data acceptance; changing SOURCE is insufficient.
    data['external_citation_allowed'] = False
    data['input_sha256'] = hashlib.sha256((engine/'data/retail_monthly.csv').read_bytes()).hexdigest()
    return data


def forecast_payload(fc, log, cutoff, scenario, model_version):
    annual = fc[(fc.index >= '2027-01') & (fc.index <= '2027-12')]
    if len(annual) != 12:
        raise ValueError('2027 annual forecast does not contain twelve months')
    parts = {c: {'p10': float(annual[(c,.1)].sum()), 'p50': float(annual[(c,.5)].sum()),
                 'p90': float(annual[(c,.9)].sum())} for c in ('total','bev','phev','hev','ice')}
    total = parts['total']['p50']
    return dict(model_version=model_version, data_cutoff=cutoff, scenario=scenario,
                y2027_total_p10=parts['total']['p10'], y2027_total_p50=total,
                y2027_total_p90=parts['total']['p90'], annual_by_powertrain=parts,
                y2027_nev_penetration_pct=100*(parts['bev']['p50']+parts['phev']['p50'])/total,
                adjustments=len(log), adjustment_chain=log.to_dict('records'),
                interval_method='sum_of_monthly_marginal_quantiles; annual coverage not calibrated')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', required=True)
    args = parser.parse_args()
    request_path = Path(args.request).resolve()
    allowed = (PROJECT/'runtime/forecast-engine-runs').resolve()
    if not request_path.is_relative_to(allowed):
        raise ValueError('Request must belong to an isolated forecast task')
    request = json.loads(request_path.read_text(encoding='utf-8'))
    engine = request_path.parent / 'engine'
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            data = execute(engine, request['name'], request['arguments'])
        result = dict(ok='error' not in data, data=data)
    except Exception as exc:
        result = dict(ok=False, error=type(exc).__name__+': '+str(exc)[:500])
        (request_path.parent/'worker-error.txt').write_text(traceback.format_exc(), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
