import json,hashlib,sys
from pathlib import Path
from datetime import datetime
from openpyxl import load_workbook
from dotenv import dotenv_values
import psycopg2
from psycopg2.extras import RealDictCursor
root=Path(__file__).resolve().parents[1]
source=Path(r"E:/AI/migration-backup/files/1009.xlsx")
sha=hashlib.sha256(source.read_bytes()).hexdigest()
w=load_workbook(source,read_only=True,data_only=True)
raw=[r for r in list(w['data'].values)[2:] if isinstance(r[1],datetime) and (r[1].year,r[1].month)==(2026,10)]
w.close()
assert len(raw)==8 and len({r[0] for r in raw})==8
columns=['model_style_id','launch_year','launch_month','launch_date','region','brand','model','attr','vehicle_type','vehicle_level','series','enterprise','energy_type','import_batch','style_name']
rows=[]
for r in raw:
 assert r[2]=='小改款' and r[12] in ['中型车','中型SUV','中大型SUV'] and r[15]=='纯电动'
 values=[int(r[0]),2026,10,r[1].date(),r[3] or None,r[5],r[6],'改款','轿车' if r[12]=='中型车' else 'SUV',r[11],r[7],r[4],r[15],'202610',r[17]]
 assert all(values[i] for i in [0,5,6,7,8,9,10,11,12,13,14])
 rows.append(dict(zip(columns,values)))
out=root/'outputs/new-car-october-publication';out.mkdir(exist_ok=True)
def dump(name,data):(out/name).write_text(json.dumps(data,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
dump('source-records.json',raw);dump('mapped-records.json',rows)
e={**dotenv_values(root/'.env'),**dotenv_values(root/'.env.new-car')}
assert e['NEW_CAR_PG_HOST']=='192.168.3.146' and e['NEW_CAR_PG_DATABASE']=='vectordb'
c=psycopg2.connect(host=e['NEW_CAR_PG_HOST'],port=int(e.get('NEW_CAR_PG_PORT',5432)),dbname=e['NEW_CAR_PG_DATABASE'],user=e['NEW_CAR_PG_USER'],password=e['NEW_CAR_PG_PASSWORD'],connect_timeout=15)
with c:
 with c.cursor(cursor_factory=RealDictCursor) as q:
  q.execute("SET LOCAL lock_timeout='10s'")
  q.execute('LOCK TABLE public.new_car_model IN SHARE ROW EXCLUSIVE MODE')
  q.execute('SELECT * FROM public.new_car_model ORDER BY model_style_id');before=[dict(x) for x in q.fetchall()];dump('before.json',before)
  ids={x['model_style_id'] for x in before};existing=[x for x in rows if x['model_style_id'] in ids]
  for x in existing:
   old=next(z for z in before if z['model_style_id']==x['model_style_id'])
   assert all(old[k]==x[k] for k in columns),'Conflicting existing ID'
  pending=[x for x in rows if x['model_style_id'] not in ids]
  if '--apply' in sys.argv:
   for x in pending:q.execute('INSERT INTO public.new_car_model ('+','.join(columns)+') VALUES ('+','.join(['%s']*len(columns))+')',tuple(x[k] for k in columns))
   q.execute('SELECT * FROM public.new_car_model ORDER BY model_style_id');after=[dict(x) for x in q.fetchall()]
   assert [x for x in after if x['model_style_id'] in ids]==before
   assert len(after)==len(before)+len(pending)
   assert hashlib.sha256(source.read_bytes()).hexdigest()==sha
  report=dict(status='committed' if '--apply' in sys.argv else 'checked',before=len(before),added=len(pending),existing=len(existing),after=len(before)+len(pending),source_sha256=sha,source_models=sorted({x['model'] for x in rows}),missing_region=8,missing_article=4)
  dump('report.json',report)
c.close();print(json.dumps(report,ensure_ascii=False))
