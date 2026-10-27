"""Run MIGRATION.md 3.3 verbatim in an isolated copy; preserve source DB/data."""
from __future__ import annotations
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from datetime import datetime

PROJECT = Path(__file__).resolve().parents[1]


def hashes(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts}


def main():
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    source = PROJECT / 'forecast-engine'
    output = PROJECT / 'outputs' / 'forecast-engine-integration' / stamp
    work = PROJECT / 'runtime' / 'forecast-engine-validation' / stamp / 'engine'
    output.mkdir(parents=True)
    before = hashes(source)
    shutil.copytree(source, work, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    (work.parent/'README.md').write_text('Isolated migration verification copy. Source engine, CSVs and DB remain untouched. Results: '+str(output)+'\nRetain until migration evidence is reviewed.\n', encoding='utf-8')
    (output/'README.md').write_text('MIGRATION.md 3.3 verification; synthetic pipeline checks only.\nFour original commands run in a separate copied engine. No model download or source CSV replacement.\nReproduce: ../Scripts/python.exe -B scripts/verify_forecast_engine_migration.py\n', encoding='utf-8')
    versions = {}
    for name in ('pandas','numpy','lightgbm','scipy','chronos-forecasting','torch'):
        try: versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: versions[name] = None
    record = dict(source=str(source), workspace=str(work), python=sys.version, versions=versions,
                  input_hashes=before, commands=[], expected=dict(m2_mape=6.65,province_mape=3.58,base_2027_vehicles=20560000))
    def save():
        (output/'migration-verification.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    save()
    env=dict(os.environ, PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', OMP_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2')
    commands=[['eval/backtest.py'],['eval/backtest_province.py'],['run_forecast.py'],['agent/tools.py','demo']]
    for i, args in enumerate(commands,1):
        log=output/f'{i}-command.log'
        print('Running: python '+' '.join(args),flush=True)
        with log.open('w',encoding='utf-8') as stream:
            try:
                result=subprocess.run([sys.executable,'-B',*args],cwd=work,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=600)
                code=result.returncode
            except subprocess.TimeoutExpired: code=124
        text=log.read_text(encoding='utf-8')
        row=dict(command='python '+' '.join(args),exit_code=code,log=log.name)
        if i==1:
            match=re.search(r'^total\s+([\d.]+)%\s+([\d.]+)%',text,re.M)
            if match: row.update(m2_mape=float(match[2]),matches_reference=abs(float(match[2])-6.65)<=0.1)
        elif i==2:
            match=re.search(r'全省平均: 份额法\s+([\d.]+)%',text)
            if match: row.update(province_mape=float(match[1]),matches_reference=abs(float(match[1])-3.58)<=0.1)
        elif i==3:
            match=re.search(r'\[base情景\].*?总量 P50 = ([\d.]+)',text,re.S)
            if match: row.update(base_2027_vehicles=float(match[1]),matches_reference=abs(float(match[1])-20560000)<=100000)
        else:
            row.update(all_four_tools_present=all('【工具'+str(n)+'】' in text for n in range(1,5)), no_tool_error='"error"' not in text)
            delta=re.search(r'"delta":\s*([-\d.]+)',text)
            row['scenario_delta_vehicles']=float(delta[1]) if delta else None
            row['matches_reference']=row['all_four_tools_present'] and row['no_tool_error'] and bool(delta) and abs(float(delta[1])-380000)<=50000
        record['commands'].append(row); save(); print(json.dumps(row,ensure_ascii=False),flush=True)
    after=hashes(source)
    record['source_changed']=[name for name in set(before)|set(after) if before.get(name)!=after.get(name)]
    record['passed']=not record['source_changed'] and all(x['exit_code']==0 and x.get('matches_reference',False) for x in record['commands'])
    record['interpretation']='Synthetic pipeline self-check only; not evidence of real market accuracy.'
    save(); print(json.dumps(dict(output=str(output),passed=record['passed'],source_changed=record['source_changed']),ensure_ascii=False))
    return 0 if record['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
