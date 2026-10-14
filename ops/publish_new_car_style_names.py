"""Guarded name-only enrichment: existing formal IDs, no baseline replacements."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
from dotenv import dotenv_values
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values

ROOT=Path(__file__).resolve().parents[1]
def dump(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
def base(rows):return [{k:v for k,v in r.items() if k!='style_name'} for r in rows]
def snapshot(cur):
    cur.execute('SELECT * FROM public.new_car_model ORDER BY model_style_id')
    return [dict(r) for r in cur.fetchall()]

def plan(rows,mapping):
    names={r['id']:r['name'] for r in mapping['names']}
    ids={r['model_style_id'] for r in rows}
    changes=[];conflicts=[]
    for row in rows:
        sid=row['model_style_id'];name=names.get(sid);old=row.get('style_name')
        if name and old and old!=name:conflicts.append({'id':sid,'existing':old,'incoming':name})
        elif name and not old:changes.append((sid,name))
    return changes,conflicts,sorted(ids-names.keys()),sorted(names.keys()-ids)

def main():
    p=argparse.ArgumentParser();p.add_argument('--mapping',type=Path,required=True);p.add_argument('--apply',action='store_true');a=p.parse_args()
    mapping=json.loads(a.mapping.read_text(encoding='utf-8'))
    if hashlib.sha256(Path(mapping['source']).read_bytes()).hexdigest()!=mapping['sha256']:raise ValueError('Source workbook changed')
    if mapping['conflicts'] or mapping['invalid_id_rows']:raise ValueError('Resolve source ID conflicts before publication')
    names=mapping['names']
    if len({r['id'] for r in names})!=len(names) or any(not r['name'].strip() for r in names):raise ValueError('Invalid mapping')
    env=dotenv_values(ROOT/'.env.new-car')
    if (env['NEW_CAR_PG_HOST'],env['NEW_CAR_PG_DATABASE'])!=('192.168.3.146','vectordb'):raise ValueError('Unexpected target')
    out=ROOT/'outputs/new-car-style-names'/datetime.now().strftime('%Y%m%dT%H%M%S');out.mkdir(parents=True,exist_ok=False)
    connection=psycopg2.connect(host=env['NEW_CAR_PG_HOST'],port=env.get('NEW_CAR_PG_PORT','5432'),dbname=env['NEW_CAR_PG_DATABASE'],user=env['NEW_CAR_PG_USER'],password=env['NEW_CAR_PG_PASSWORD'],connect_timeout=5,application_name='new-car-style-name-enrichment')
    report={'mode':'apply' if a.apply else 'dry_run','source_sha256':mapping['sha256'],'output_dir':str(out)}
    try:
        with connection:
            with connection.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SET LOCAL lock_timeout='5s'");cur.execute("SET LOCAL statement_timeout='60s'")
                if a.apply:cur.execute('LOCK TABLE public.new_car_model IN ACCESS EXCLUSIVE MODE')
                before=snapshot(cur);changes,conflicts,missing,extra=plan(before,mapping)
                dump(out/'before-database.json',before)
                dump(out/'reconciliation.json',{'existing_name_conflicts':conflicts,'missing_formal_ids':missing,'source_only_ids':extra,'changes':[{'id':sid,'name':name} for sid,name in changes]})
                report.update(formal_total=len(before),source_names=len(names),matched=len(before)-len(missing),missing_ids=missing,source_only_ids=extra,existing_conflicts=len(conflicts),planned_updates=len(changes),updated=0)
                if conflicts:raise ValueError('Existing names conflict; no overwrites')
                if a.apply:
                    cur.execute("SELECT data_type FROM information_schema.columns WHERE table_schema='public' AND table_name='new_car_model' AND column_name='style_name'")
                    column=cur.fetchone()
                    if column and column['data_type']!='text':raise ValueError('Unexpected style_name column type')
                    if not column:cur.execute('ALTER TABLE public.new_car_model ADD COLUMN style_name TEXT')
                    if changes:
                        result=execute_values(cur,'UPDATE public.new_car_model n SET style_name=v.name FROM (VALUES %s) AS v(id,name) WHERE n.model_style_id=v.id AND COALESCE(n.style_name,\'\')=\'\' RETURNING n.model_style_id',changes,page_size=500,fetch=True)
                        if {r['model_style_id'] for r in result}!={sid for sid,name in changes}:raise ValueError('Update count mismatch; rollback')
                    after=snapshot(cur)
                    if base(after)!=base(before):raise ValueError('Existing base fields changed; rollback')
                    expected={r['id']:r['name'] for r in names}
                    if any(r.get('style_name')!=expected[r['model_style_id']] for r in after if r['model_style_id'] in expected):raise ValueError('Name verification failed; rollback')
                    cur.execute("SELECT has_column_privilege('market_mcp_reader','public.new_car_model','style_name','SELECT') AS allowed")
                    if not cur.fetchone()['allowed']:raise ValueError('MCP reader lacks new column access; rollback')
                    dump(out/'after-names.json',[{'id':r['model_style_id'],'name':r['style_name']} for r in after])
                    report.update(updated=len(changes),column_added=not bool(column),base_preserved=True,status='validated')
        report['status']='committed' if a.apply else 'checked'
        dump(out/'report.json',report);print(json.dumps(report,ensure_ascii=False))
    finally:connection.close()

if __name__=='__main__':main()
