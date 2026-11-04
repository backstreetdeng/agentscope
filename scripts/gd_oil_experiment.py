"""Audit/import a supplied oil snapshot or run offline experimental forecast.

No network. Copies only explicit CSV inputs to a new local snapshot, refuses
overwrite, saves unique result manifests; never modifies original files.
"""
from __future__ import annotations
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import sys
from uuid import uuid4

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--import-folder',type=Path)
    parser.add_argument('--operation',choices=['forecast','backtest'],default='forecast')
    parser.add_argument('--horizon',type=int,default=6)
    args=parser.parse_args()
    from integrations.gd_oil import audit, ROOT, DETAIL, END, AVG
    if args.import_folder:
        result=audit(args.import_folder)
        ROOT.mkdir(parents=True,exist_ok=False)
        for name in (DETAIL,END,AVG):shutil.copyfile(args.import_folder/name,ROOT/name)
        result.update(source_folder=str(args.import_folder),created_at=datetime.now().astimezone().isoformat(),
            retention='本机输入快照；保留用于复算，删除前确认任务引用。')
        (ROOT/'manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'imported':str(ROOT),'months':len(result['monthly']),'events':result['events']},ensure_ascii=True))
        return
    from integrations.sarimax_forecast import _run_child
    os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
    payload=dict(operation=args.operation,province='广东',energy='插电式混合动力',cutoff=None,horizon=args.horizon,profile='gd_oil')
    out=PROJECT/'outputs'/'chronos-003'/('oil-'+uuid4().hex)
    out.mkdir(parents=True,exist_ok=False)
    receipt=dict(arguments=payload,status='running',started_at=datetime.now().astimezone().isoformat(),
                 retention='内部实验回执；不对外引用；删除前确认任务引用。')
    path=out/'manifest.json'
    path.write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    try:
        result=_run_child(payload)
        receipt.update(status='completed',result=result)
    except Exception as exc:
        receipt.update(status='failed',error=str(exc));raise
    finally:
        path.write_text(json.dumps(receipt,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({'manifest':str(path),'status':receipt['status'],
        'scores':{k:v['by_horizon'] for k,v in result.get('benchmark',{}).items()}},ensure_ascii=True))


if __name__=='__main__':main()
