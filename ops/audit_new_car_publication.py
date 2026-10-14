"""Read-only reconciliation of local collection tables and the existing 146 MCP."""
import asyncio
from collections import Counter
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import sys

import httpx
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import sql
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from integrations.market_mcp_plugins import market_mcp_plugin_catalog
from utils.config import ENV_PATH, load_json_config

TABLES = ('autohome_newcar_specs', 'autohome_newcar_specs_invalid_date',
          'autohome_newcar_runs', 'ods_pz_base_info', 'ods_pz_detail_info',
          'car_monitoring_weekly_new', 'car_monitoring_weekly_new_history')

def decode(result):
    if result.isError:
        raise RuntimeError('MCP tool rejected request')
    for block in result.content:
        if getattr(block, 'type', '') == 'text':
            data = json.loads(block.text)
            if not data.get('success'):
                raise RuntimeError('MCP returned unavailable')
            return data
    raise RuntimeError('MCP returned no JSON')

def sid(value):
    value = str(value or '').strip()
    return str(int(value)) if value.isdigit() else value

def local_snapshot():
    conn = psycopg2.connect(host='127.0.0.1', port=5432, dbname='postgres',
                           user='postgres', password=os.environ['NEWCAR_AUDIT_LOCAL_PASSWORD'],
                           connect_timeout=5)
    conn.set_session(readonly=True, isolation_level='REPEATABLE READ', autocommit=False)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name=ANY(%s)", (list(TABLES),))
            existing = {r['table_name'] for r in cur.fetchall()}
            counts = {}
            for name in TABLES:
                if name in existing:
                    cur.execute(sql.SQL('SELECT COUNT(*) AS n FROM public.{}').format(sql.Identifier(name)))
                    counts[name] = cur.fetchone()['n']
                else:
                    counts[name] = None
            cur.execute('SELECT spec_id,series_id,series_name,factory_name,brand_name,spec_name,vehicle_class,min_price,launch_date,first_seen_at,updated_at FROM public.autohome_newcar_specs ORDER BY spec_id')
            base = [dict(r) for r in cur.fetchall()]
            config_rows, history_rows = [], []
            if 'car_monitoring_weekly_new' in existing:
                cur.execute('SELECT * FROM public.car_monitoring_weekly_new')
                config_rows = [dict(r) for r in cur.fetchall()]
            if 'car_monitoring_weekly_new_history' in existing:
                cur.execute('SELECT * FROM public.car_monitoring_weekly_new_history')
                history_rows = [dict(r) for r in cur.fetchall()]
            ods_ids = {}
            for name in ('ods_pz_base_info', 'ods_pz_detail_info'):
                if name in existing:
                    cur.execute(sql.SQL('SELECT DISTINCT car_id FROM public.{}').format(sql.Identifier(name)))
                    ods_ids[name] = {sid(r['car_id']) for r in cur.fetchall() if r['car_id']}
            runs, success = [], None
            if 'autohome_newcar_runs' in existing:
                columns = 'id,run_type,status,started_at,finished_at,stored_specs,total_specs'
                cur.execute('SELECT '+columns+' FROM public.autohome_newcar_runs ORDER BY id DESC LIMIT 8')
                runs = [dict(r) for r in cur.fetchall()]
                cur.execute('SELECT '+columns+" FROM public.autohome_newcar_runs WHERE status='success' ORDER BY finished_at DESC NULLS LAST,id DESC LIMIT 1")
                value = cur.fetchone()
                success = dict(value) if value else None
        return counts, base, config_rows, history_rows, ods_ids, runs, success
    finally:
        conn.rollback()
        conn.close()

async def remote_snapshot():
    load_dotenv(ENV_PATH, override=False)
    plugin = next(p for p in market_mcp_plugin_catalog(load_json_config()) if p.plugin_id == 'new-car')
    async with httpx.AsyncClient(headers={'Authorization': 'Bearer '+plugin.resolve_token()}, timeout=30) as client:
        async with streamable_http_client(plugin.url, http_client=client) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                before = decode(await session.call_tool('new_car_get_status', {'response_format': 'json'}))
                rows = []
                offset = 0
                while True:
                    page = decode(await session.call_tool('new_car_search_models', {'params': {'limit': 100, 'offset': offset, 'response_format': 'json'}}))
                    if page['total_count'] != before['model_count']:
                        raise RuntimeError('Remote count changed during audit')
                    rows.extend(page['items'])
                    if not page['has_more']:
                        break
                    if page['next_offset'] <= offset:
                        raise RuntimeError('Invalid MCP pagination')
                    offset = page['next_offset']
                after = decode(await session.call_tool('new_car_get_status', {'response_format': 'json'}))
                if before != after or len(rows) != before['model_count'] or len({sid(r['id']) for r in rows}) != len(rows):
                    raise RuntimeError('Remote audit is incomplete or inconsistent')
                return before, rows

async def main():
    counts, base, configs, history, ods, runs, success = local_snapshot()
    print(json.dumps({'local_table_counts': counts}, ensure_ascii=False), flush=True)
    status, remote_rows = await remote_snapshot()
    current = {sid(r['spec_id']): r for r in base}
    old = {sid(r['id']): r for r in remote_rows}
    common = current.keys() & old.keys()
    differences = []
    field_counts = Counter()
    for key in sorted(common, key=int):
        for local_field, remote_field in [('launch_date','launch_date'), ('brand_name','brand'), ('series_name','model'), ('factory_name','enterprise')]:
            a, b = str(current[key].get(local_field) or '').strip(), str(old[key].get(remote_field) or '').strip()
            if a != b:
                field_counts[local_field] += 1
                differences.append({'spec_id': key, 'field': local_field, 'local': a, '146_legacy': b})
    config_counts = Counter(sid(r.get('汽车之家款型id')) for r in configs)
    history_counts = Counter(sid(r.get('汽车之家款型id')) for r in history)
    config_ids = set(config_counts) - {''}
    history_ids = set(history_counts) - {''}
    valid_configs = config_ids | history_ids
    dates = [r['launch_date'] for r in base if r['launch_date']]
    report = {
        'audited_at': datetime.now(timezone(timedelta(hours=8))).isoformat(),
        'read_only': True,
        'local_source': '127.0.0.1:5432/postgres/public',
        'local_table_counts': counts,
        'local_base': {'count': len(base), 'series_count': len({r['series_id'] for r in base}),
                       'earliest_launch': min(dates) if dates else None, 'latest_launch': max(dates) if dates else None},
        'remote_status': status,
        'reconciliation': {'common_ids': len(common), 'local_only': len(current.keys()-old.keys()),
                           'legacy_only': len(old.keys()-current.keys()), 'union_ids': len(current.keys()|old.keys()),
                           'local_only_ids': sorted(current.keys()-old.keys(), key=int),
                           'legacy_only_ids': sorted(old.keys()-current.keys(), key=int),
                           'different_field_counts': dict(field_counts),
                           'affected_ids': len({r['spec_id'] for r in differences}), 'differences': differences},
        'configuration': {'current_distinct_ids': len(config_ids), 'history_distinct_ids': len(history_ids),
                           'current_plus_history_distinct_ids': len(valid_configs),
                           'base_with_config': len(current.keys() & valid_configs),
                           'base_without_config': len(current.keys()-valid_configs),
                           'config_not_in_base_ids': sorted(valid_configs-current.keys()),
                           'duplicate_current_ids': {k:v for k,v in config_counts.items() if v>1},
                           'field_count': len(configs[0]) if configs else None,
                           'ods_distinct_ids': {k:len(v) for k,v in ods.items()},
                           'latest_history_snapshot': max((r.get('snapshot_at') for r in history if r.get('snapshot_at')), default=None)},
        'recent_runs': runs, 'last_successful_task_run': success,
        'last_successful_collect_in_recent_runs': next((r for r in runs if r['run_type'].startswith('collect-') and r['status']=='success'), None),
        'limitations': ['Configuration presence does not prove all 76 fields are complete.',
                       'MCP lacks a snapshot version; count and batch checked before/after paging, but concurrent same-count field edits cannot be ruled out.',
                       'A successful collector/export/launcher run is not proof of successful configuration publication.']}
    folder = ROOT/'outputs'/'new-car-source-audit'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder/('audit-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.json')
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    summary = {k:v for k,v in report.items() if k not in ('reconciliation','recent_runs','limitations')}
    summary['reconciliation'] = {k:v for k,v in report['reconciliation'].items() if k not in ('differences','local_only_ids','legacy_only_ids')}
    summary['report_path'] = str(path)
    print(json.dumps(summary, ensure_ascii=False, default=str), flush=True)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as error:
        print(json.dumps({'audit_complete': False, 'error_type': type(error).__name__}))
        sys.exit(1)
