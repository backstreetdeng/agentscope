"""Create a local, review-only price candidate inventory from supplied Excel files.

No source file is changed, no missing value is filled, and no monthly model
variable is created. Output is private and stays under outputs/chronos-003.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
from uuid import uuid4

from openpyxl import load_workbook

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from integrations.price_candidates import historical_candidate, monitor_candidate

HISTORICAL = {'22年涨价','23年降价','24年降价','25年降价','26年降价','26年涨价车型','新车上市礼','超长期低息清单','Sheet2','一口价清单'}


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024), b''): digest.update(chunk)
    return digest.hexdigest()


def read_candidates(path):
    before = sha256(path)
    book = load_workbook(path,read_only=True,data_only=True)
    result = []
    try:
        for sheet in book.worksheets:
            if sheet.title in {'综合台账','10月监测总表'}:
                header_row, factory = 1, monitor_candidate
            elif sheet.title in HISTORICAL:
                header_row = 1 if sheet.title in {'超长期低息清单','Sheet2','一口价清单'} else 2
                factory = historical_candidate
            else: continue
            rows = sheet.iter_rows(values_only=True)
            for _ in range(header_row-1): next(rows, None)
            headers = next(rows, ())
            for number, values in enumerate(rows, header_row+1):
                record = {str(k):v for k,v in zip(headers,values) if k is not None}
                item = factory(record,sheet=sheet.title,row=number,source=path.name)
                if item: result.append(item)
    finally:
        book.close()
    if sha256(path) != before: raise ValueError('读取期间源文件发生变化，已停止整理。')
    return before, result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',action='append',required=True,help='指定来源 Excel；可重复')
    args=parser.parse_args()
    candidates=[]; sources=[]
    for name in args.source:
        path=Path(name)
        digest, rows=read_candidates(path)
        sources.append({'name':path.name,'sha256':digest,'candidate_rows':len(rows)})
        candidates.extend(rows)
    output=PROJECT/'outputs'/'chronos-003'/('price-candidates-'+uuid4().hex)
    output.mkdir(parents=True,exist_ok=False)
    with (output/'candidates.jsonl').open('w',encoding='utf-8',newline='\n') as stream:
        for row in candidates: stream.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n')
    manifest={'task':'CHRONOS-003','created_at':datetime.now().astimezone().isoformat(),
              'sources':sources,'candidate_rows':len(candidates),'status':'未核验候选记录，不是月度价格指数',
              'privacy':'内部资料，仅本机使用；不发送到外部服务',
              'retention':'保留用于复核；需要人工确认后才能清理',
              'rebuild':'使用本脚本并重新提供每个 --source 原始文件；不覆盖输出'}
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print('候选整理完成；文件:', output)
    print('候选行数:',len(candidates))
    return 0


if __name__ == '__main__': raise SystemExit(main())
