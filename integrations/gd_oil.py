"""Read-only Guangdong oil snapshot audit. No network and no vintage claims.

Reconstruct prices from dated events; never infer an unknown event date or
replace missing prices with zero. Snapshot hashes are retained in each result.
"""
from __future__ import annotations
import calendar
import csv
from datetime import date, timedelta
import hashlib
import json
import math
from pathlib import Path
import re

from integrations.chronos2_data import PROJECT

ROOT = PROJECT / 'data' / 'passenger-forecast' / 'gd-oil'
DETAIL = '广东汽油价格_调价明细.csv'
END = '广东油价_月末有效价_月度.csv'
AVG = '广东油价_月均价_按生效天数加权.csv'


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def audit(folder):
    folder = Path(folder)
    raw = read_csv(folder / DETAIL)
    events = []
    for row in raw:
        when = date.fromisoformat(row['生效日期'])
        announced = date.fromisoformat(row['公告日期'])
        prices = tuple(float(row[f'{q}号汽油_元每升']) for q in (92, 95))
        if (row['生效时刻'] != '00:00' or announced > when
                or not all(math.isfinite(v) and v > 0 for v in prices)
                or prices[1] < prices[0] or not row['公告原文链接'] or not row['采集时间']):
            raise ValueError('油价明细缺少有效时间、价格或来源。')
        match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日24时', row['原文生效表述'])
        if not match or date(*map(int, match.groups())) + timedelta(days=1) != when:
            raise ValueError('原文 24 时与生效日期不一致，需人工核验。')
        events.append((when, prices, row))
    events.sort(key=lambda x: x[0])
    if len({e[0] for e in events}) != len(events):
        raise ValueError('油价包含重复生效日期。')
    ends, avgs = read_csv(folder / END), read_csv(folder / AVG)
    if not ends or [x['月份'] for x in ends] != [x['月份'] for x in avgs]:
        raise ValueError('油价月表月份不一致。')
    monthly = []
    for end, avg in zip(ends, avgs):
        ym = end['月份']; year, month = map(int, ym.split('-'))
        first = date(year, month, 1)
        if monthly:
            prev = date.fromisoformat(monthly[-1]['period'] + '-01')
            if first != (prev.replace(day=28) + timedelta(days=4)).replace(day=1):
                raise ValueError('油价月份重复或不连续。')
        daily = []
        for day in range(1, calendar.monthrange(year, month)[1] + 1):
            known = [e for e in events if e[0] <= date(year, month, day)]
            if not known:
                raise ValueError('缺少月初有效价格，不能沿用未知值。')
            daily.append(known[-1][1])
        for i, grade in enumerate((92, 95)):
            if (abs(float(end[f'{grade}号_月末有效价_元每升']) - daily[-1][i]) > 1e-8
                    or abs(float(avg[f'{grade}号_月均价_按生效天数加权']) - sum(d[i] for d in daily)/len(daily)) > .000051):
                raise ValueError(f'{ym} {grade} 号月末价或月均价重算不一致。')
        if int(avg['覆盖天数']) != len(daily) or int(avg['当月天数']) != len(daily):
            raise ValueError('月均价覆盖天数不一致。')
        monthly.append(dict(period=ym, value=sum(d[0] for d in daily)/len(daily),
                            available_at=date(year, month, len(daily)).isoformat()))
    hashes = {n: hashlib.sha256((folder/n).read_bytes()).hexdigest() for n in (DETAIL, END, AVG)}
    return dict(events=len(events), monthly=monthly, hashes=hashes,
                boundary_events=sum(e[0].day == 1 for e in events),
                status='calculation_verified_snapshot', vintage_verified=False,
                limitation='按当前采集快照重建；原始公告完整性与历史版本未全量验收。')


def load():
    manifest = json.loads((ROOT/'manifest.json').read_text(encoding='utf-8'))
    result = audit(ROOT)
    if result['hashes'] != manifest['hashes']:
        raise ValueError('油价文件版本变化，请重新核验。')
    return result
