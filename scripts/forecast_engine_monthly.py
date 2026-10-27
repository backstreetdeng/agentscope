"""Monthly operations: intake -> backtest scorecard -> forecasts -> internal report.

Default refuses placeholder CSVs. --allow-synthetic explicitly exercises the
pipeline without claiming market accuracy. All execution is in a private copy.
"""
from __future__ import annotations
import argparse
import ast
import csv
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

PROJECT=Path(__file__).resolve().parents[1]
SOURCE=PROJECT/'forecast-engine'


def source_label():
    tree=ast.parse((SOURCE/'ingest/ingest.py').read_text(encoding='utf-8-sig'))
    for node in tree.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SOURCE' for t in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError('Missing source declaration')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase',choices=['intake','backtest','forecast','report','all'],default='all')
    parser.add_argument('--allow-synthetic',action='store_true')
    args=parser.parse_args()
    stamp=datetime.now().strftime('%Y%m%d-%H%M%S')
    root=PROJECT/'outputs/forecast-engine-operations'/stamp
    root.mkdir(parents=True)
    source=source_label()
    synthetic='SAMPLE' in source.upper() or 'PLACEHOLDER' in source.upper()
    input_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (SOURCE/'data').glob('*.csv')}
    state=dict(phase=args.phase,source=source,synthetic=synthetic,input_sha256=input_hashes,
               external_citation_allowed=False,stages=[],status='created')
    with (SOURCE/'data/retail_monthly.csv').open(encoding='utf-8-sig',newline='') as stream:
        state['data_cutoff']=max(row['ym'] for row in csv.DictReader(stream))
    def save(): (root/'operations.json').write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
    (root/'README.md').write_text('Monthly forecast operations, isolated input snapshot.\nReproduce: ../Scripts/python.exe -B scripts/forecast_engine_monthly.py --phase '+args.phase+'\nKeep input hashes, scorecard and report for audit; no source database changed.\n',encoding='utf-8')
    if synthetic and not args.allow_synthetic:
        state.update(status='waiting_real_data',reason='Waiting for authorized real CSVs, metric/source confirmation and event-coefficient review; do not promote placeholder data.')
        save(); print(json.dumps(dict(status=state['status'],output=str(root)),ensure_ascii=False)); return 2
    work=PROJECT/'runtime/forecast-engine-operations'/stamp/'engine'
    shutil.copytree(SOURCE,work,ignore=shutil.ignore_patterns('__pycache__','*.pyc','market.db','outputs'))
    env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',HF_HUB_OFFLINE='1',OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2')
    def run(label,script):
        log=root/(label+'.log')
        with log.open('w',encoding='utf-8') as stream:
            proc=subprocess.run([sys.executable,'-B',script],cwd=work,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=600)
        state['stages'].append(dict(name=label,exit_code=proc.returncode,log=log.name)); save()
        if proc.returncode: raise RuntimeError(label+' failed; inspect '+str(log))
        return log.read_text(encoding='utf-8')
    try:
        run('intake','ingest/ingest.py')
        if args.phase in {'all','backtest','report'}:
            text=run('backtest','eval/backtest.py')
            m=re.search(r'^total\s+([\d.]+)%\s+([\d.]+)%',text,re.M)
            coverage=re.search(r'区间覆盖\s+([\d.]+)%',text)
            state['scorecard']=dict(m2_mape=float(m[2]) if m else None,interval_coverage=float(coverage[1]) if coverage else None,
                                    scope='synthetic_pipeline_only' if synthetic else 'real_data_review_pending')
            if not m or not coverage: raise RuntimeError('Backtest did not produce complete scorecard')
            state['scorecard']['numerical_threshold_passed']=float(m[2])<=10 and 70<=float(coverage[1])<=90
        if args.phase in {'all','forecast','report'}:
            run('forecast','run_forecast.py')
            if synthetic:
                # The migrated province reader is sample-source-specific; never mix it with real national data.
                run('province-intake','ingest/ingest_province.py')
                run('province-forecast','run_province.py')
            else:
                state['province_status']='not_run: real province source/metric reader requires separate acceptance'
            for path in (work/'outputs').glob('*.csv'): shutil.copy2(path,root/path.name)
        if args.phase in {'all','report'}:
            report=['# 市场预测内部核验月报','模拟占位数据，禁止对外引用。' if synthetic else '真实数据尚待业务验收，禁止对外引用。',
                    '## 口径与证据', '零售口径；销量单位：辆；数据截止：'+state['data_cutoff']+'；输入版本见 operations.json 的 SHA256。',
                    '## 回测记分卡',json.dumps(state.get('scorecard',{}),ensure_ascii=False),
                    '## 三情景结果','| 情景 | 2027 P10 | P50 | P90 |','|---|---:|---:|---:|']
            import pandas as pd
            for scenario in ('base','bull','bear'):
                frame=pd.read_csv(work/f'outputs/forecast_{scenario}.csv',index_col=0)
                annual=frame[(frame.index>='2027-01')&(frame.index<='2027-12')]
                if len(annual)!=12: raise RuntimeError('Incomplete annual forecast')
                report.append('| '+scenario+' | '+' | '.join(f"{annual['total_'+q].sum():,.0f}" for q in ('p10','p50','p90'))+' |')
            report+=['## 决策含义','用于审查产能、产品线与预算的情景敏感性；当前验收状态不支持形成正式经营结论。',
                     '## 待核验','事件假设需业务评审；年度区间为月度分位数加总；分省需同口径与独立回测；不将文档历史精度作为真实市场效果。']
            (root/'monthly-report.md').write_text('\n\n'.join(report),encoding='utf-8')
        state['status']='completed_internal_only'; save()
        print(json.dumps(dict(status=state['status'],output=str(root),scorecard=state.get('scorecard')),ensure_ascii=False)); return 0
    except Exception as exc:
        state.update(status='failed',error=type(exc).__name__+': '+str(exc)); save(); raise


if __name__=='__main__': raise SystemExit(main())
