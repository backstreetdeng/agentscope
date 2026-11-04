"""Collect public EIA monthly Brent spot prices into an immutable local snapshot.

This international crude series is NOT domestic gasoline retail price. Historical
publication vintages are not provided by this snapshot; do not use it for
leakage-safe rolling exogenous backtests without separate vintage evidence.
No private business data or credentials are sent to the public source.
"""
from __future__ import annotations

import csv
from datetime import datetime
import hashlib
import io
import json
import math
from pathlib import Path
import re
from urllib.request import Request, urlopen
from uuid import uuid4

import pandas as pd

PROJECT=Path(__file__).resolve().parents[1]
URL='https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?n=PET&s=RBRTE&f=M'
MONTHS=('Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec')


def parse(html, current_month):
    tables=pd.read_html(io.StringIO(html))
    matches=[t for t in tables if tuple(map(str,t.columns)) == ('Year',)+MONTHS]
    if not matches: raise ValueError('EIA 表格结构已变化，未生成数据。')
    # Nested copies can appear in the page. A single canonical table is used.
    rows=[]; seen=set()
    for row in matches[0].itertuples(index=False,name=None):
        if pd.isna(row[0]): continue
        year=int(row[0])
        for month,value in enumerate(row[1:],1):
            ym=f'{year:04d}-{month:02d}'
            if pd.isna(value) or ym >= current_month: continue
            number=float(value)
            if not math.isfinite(number) or number <= 0 or ym in seen:
                raise ValueError('EIA 油价存在重复或无效值。')
            seen.add(ym); rows.append((ym,number))
    if not rows: raise ValueError('EIA 油价没有完整月份记录。')
    rows.sort()
    return rows


def main():
    req=Request(URL,headers={'User-Agent':'HelloAgent-public-data-audit/1.0'})
    with urlopen(req,timeout=30) as response:
        if response.status != 200: raise ValueError('EIA 公开来源不可用。')
        raw=response.read(2_000_001)
    if len(raw)>2_000_000: raise ValueError('来源页面过大，已停止。')
    html=raw.decode('utf-8','replace')
    now=datetime.now().astimezone()
    rows=parse(html,now.strftime('%Y-%m'))
    release=re.search(r'Release Date:\s*(\d{1,2}/\d{1,2}/\d{4})',html,re.I)
    directory=PROJECT/'outputs'/'chronos-003'/('eia-brent-'+uuid4().hex)
    directory.mkdir(parents=True,exist_ok=False)
    (directory/'source.html').write_bytes(raw)
    with (directory/'monthly.csv').open('w',encoding='utf-8',newline='') as stream:
        writer=csv.writer(stream); writer.writerow(['month','brent_usd_per_barrel','historical_vintage_verified'])
        writer.writerows((month,value,'false') for month,value in rows)
    manifest={'source':'EIA Europe Brent Spot Price FOB','url':URL,'unit':'USD/barrel',
              'retrieved_at':now.isoformat(),'source_release_date':release.group(1) if release else None,
              'source_sha256':hashlib.sha256(raw).hexdigest(),'first_month':rows[0][0],'last_month':rows[-1][0],
              'months':len(rows),'historical_vintage_verified':False,
              'use':'公开国际原油候选，不等同国内零售油价；历史发布日期/修订未核验，不可直接进入防泄漏回测',
              'retention':'公开来源快照，保留用于复核；需确认后清理'}
    (directory/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print('公开油价快照:',directory)
    print('月份数:',len(rows),'范围:',rows[0][0],rows[-1][0])
    return 0


if __name__=='__main__': raise SystemExit(main())
