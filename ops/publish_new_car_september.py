"""Publish only the 266 approved September additions; no updates or schema changes."""
import argparse
import asyncio
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

from dotenv import dotenv_values, load_dotenv
from openpyxl import load_workbook
import psycopg2
from psycopg2.extras import RealDictCursor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from integrations.new_car_live import load_new_car
from utils.config import load_json_config

HEADERS = ['汽车之家款型ID', '上市年', '上市月', '国别', '品牌', '车型', '属性', '车型类别', '车型级别', '车型系别', '企业', '新能源类型']
COLUMNS = ['model_style_id', 'launch_year', 'launch_month', 'launch_date', 'region', 'brand', 'model', 'attr', 'vehicle_type', 'vehicle_level', 'series', 'enterprise', 'energy_type', 'import_batch']


def read_input(path):
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        full = list(wb['Sheet1'].values)
        added = list(wb['9月新增款型'].values)
        if list(full[0]) != HEADERS or list(added[0]) != HEADERS:
            raise ValueError('Unexpected approved workbook headers')
        ids = [int(r[0]) for r in full[1:]]
        if len(ids) != 2228 or len(set(ids)) != 2228 or len(added[1:]) != 266:
            raise ValueError('Workbook count or uniqueness changed')
        dates = {int(r[0]): str(r[2] or '') for r in list(wb['9月日期来源'].values)[1:]}
        rows = []
        for r in added[1:]:
            style_id = int(r[0])
            year = int(re.fullmatch(r'(\d{4})年?', str(r[1])).group(1))
            month = int(re.fullmatch(r'(\d{1,2})月?', str(r[2])).group(1))
            if (year, month) != (2026, 9) or not r[4] or not r[5]:
                raise ValueError(f'Invalid approved September record {style_id}')
            text = dates.get(style_id, '')
            match = re.fullmatch(r'(2026)[-/](09|9)[-/](\d{1,2})(?:\s+00:00:00)?', text)
            if not match:
                raise ValueError(f'No verified exact launch date for {style_id}: {text}')
            launch_date = date(int(match[1]), int(match[2]), int(match[3]))
            rows.append(dict(zip(COLUMNS, [style_id, year, month, launch_date, *r[3:12], '202609'])))
        if len({r['model_style_id'] for r in rows}) != 266:
            raise ValueError('Duplicate additions')
        return rows, set(ids)
    finally:
        wb.close()


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workbook', required=True, type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    approved, full_ids = read_input(args.workbook)
    file_hash = hashlib.sha256(args.workbook.read_bytes()).hexdigest()
    load_dotenv(ROOT / '.env', override=True)
    before_mcp = asyncio.run(load_new_car(load_json_config(), 'list'))
    ids = {int(r['id']) for r in before_mcp['rows']}
    approved_ids = {r['model_style_id'] for r in approved}
    if full_ids - ids != approved_ids or ids - full_ids:
        raise ValueError('Formal MCP IDs no longer match the approved 266-only delta')
    env = {**dotenv_values(ROOT / '.env'), **dotenv_values(ROOT / '.env.new-car')}
    if env.get('NEW_CAR_PG_HOST') != '192.168.3.146' or env.get('NEW_CAR_PG_DATABASE') != 'vectordb':
        raise ValueError('Unexpected formal database target')
    out = ROOT / 'outputs' / 'new-car-september-publication' / datetime.now().strftime('%Y%m%d-%H%M%S')
    out.mkdir(parents=True, exist_ok=False)
    dump(out / 'approved-additions.json', approved)
    dump(out / 'before-mcp.json', before_mcp)
    report = {'mode': 'apply' if args.apply else 'dry-run', 'source_sha256': file_hash,
              'before_count': len(ids), 'approved_additions': 266, 'updated': 0,
              'output_dir': str(out), 'status': 'checked'}
    if not args.apply:
        dump(out / 'report.json', report)
        print(json.dumps(report, ensure_ascii=False))
        return
    connection = psycopg2.connect(host=env['NEW_CAR_PG_HOST'], port=int(env.get('NEW_CAR_PG_PORT', '5432')),
        dbname=env['NEW_CAR_PG_DATABASE'], user=env['NEW_CAR_PG_USER'], password=env['NEW_CAR_PG_PASSWORD'],
        connect_timeout=5, application_name='approved-new-car-september-insert')
    try:
        with connection:
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SET LOCAL lock_timeout='10s'")
                cursor.execute("SET LOCAL statement_timeout='60s'")
                cursor.execute('LOCK TABLE public.new_car_model IN SHARE ROW EXCLUSIVE MODE')
                cursor.execute('SELECT '+','.join(COLUMNS)+' FROM public.new_car_model ORDER BY model_style_id')
                old = [dict(r) for r in cursor.fetchall()]
                if {r['model_style_id'] for r in old} != ids:
                    raise ValueError('Formal table changed since MCP reconciliation; rollback')
                dump(out / 'before-database.json', old)
                inserted = []
                statement = 'INSERT INTO public.new_car_model ('+','.join(COLUMNS)+') VALUES ('+','.join(['%s']*len(COLUMNS))+') ON CONFLICT (model_style_id) DO NOTHING RETURNING model_style_id'
                for row in approved:
                    cursor.execute(statement, tuple(row[k] for k in COLUMNS))
                    result = cursor.fetchone()
                    if result:
                        inserted.append(result['model_style_id'])
                cursor.execute('SELECT '+','.join(COLUMNS)+' FROM public.new_car_model ORDER BY model_style_id')
                after = [dict(r) for r in cursor.fetchall()]
                retained = [r for r in after if r['model_style_id'] in ids]
                added = [r for r in after if r['model_style_id'] in approved_ids]
                if len(inserted) != 266 or retained != old or len(after) != 2228:
                    raise ValueError('Post-insert preservation/count failed; rollback')
                if sorted(added, key=lambda r:r['model_style_id']) != sorted(approved, key=lambda r:r['model_style_id']):
                    raise ValueError('Inserted fields differ from approved input; rollback')
                if hashlib.sha256(args.workbook.read_bytes()).hexdigest() != file_hash:
                    raise ValueError('Source workbook changed; rollback')
                report.update(status='transaction_validated', inserted=266, after_count=2228, inserted_ids=inserted,
                              retained_records_unchanged=True)
                dump(out / 'report.json', report)
        report['status'] = 'committed'
        dump(out / 'report.json', report)
    finally:
        connection.close()
    after_mcp = asyncio.run(load_new_car(load_json_config(), 'list'))
    dump(out / 'after-mcp.json', after_mcp)
    if {int(r['id']) for r in after_mcp['rows']} != full_ids:
        raise ValueError('Committed but MCP verification failed; do not rerun insertion')
    report.update(status='committed_and_mcp_verified', mcp_count=after_mcp['total'])
    dump(out / 'report.json', report)
    print(json.dumps({k:v for k,v in report.items() if k != 'inserted_ids'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
