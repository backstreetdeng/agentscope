"""Publish validated Excel to an additive energy-specific sales table."""
import argparse,json,sys,hashlib
from pathlib import Path
from datetime import datetime
from dotenv import dotenv_values
import psycopg2
from psycopg2.extras import execute_values
from psycopg2 import sql
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.monthly_sales_workbook import read_workbook

def main():
    parser=argparse.ArgumentParser();parser.add_argument('workbook');parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    data=read_workbook(args.workbook);out=ROOT/'outputs/monthly-model-sales/20261014';out.mkdir(parents=True,exist_ok=True)
    (out/'normalized-sales.json').write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    summary={k:v for k,v in data.items() if k!='rows'};summary['status']='validated';summary['batch']='20261014-'+data['source_sha256'][:12]
    if args.apply:
        env={**dotenv_values(ROOT/'.env'),**dotenv_values(ROOT/'.env.new-car')}
        if env.get('NEW_CAR_PG_HOST')!='192.168.3.146' or env.get('NEW_CAR_PG_DATABASE')!='vectordb':raise ValueError('Unexpected business publication target')
        db=psycopg2.connect(host=env['NEW_CAR_PG_HOST'],port=int(env.get('NEW_CAR_PG_PORT',5432)),dbname=env['NEW_CAR_PG_DATABASE'],user=env['NEW_CAR_PG_USER'],password=env['NEW_CAR_PG_PASSWORD'],connect_timeout=15)
        try:
            with db:
                with db.cursor() as cursor:
                    cursor.execute("SELECT to_regclass('public.new_car_monthly_sales_by_energy')")
                    existed=bool(cursor.fetchone()[0])
                    if existed:
                        cursor.execute('SELECT row_to_json(t) FROM new_car_monthly_sales_by_energy t')
                        (out/'before-energy-sales.json').write_text(json.dumps([r[0] for r in cursor.fetchall()],ensure_ascii=False,default=str),encoding='utf-8')
                    cursor.execute('SELECT row_to_json(t) FROM new_car_monthly_sales t')
                    legacy=[r[0] for r in cursor.fetchall()]
                    (out/'legacy-sales-preserved.json').write_text(json.dumps(legacy,ensure_ascii=False,default=str),encoding='utf-8')
                    cursor.execute('''CREATE TABLE IF NOT EXISTS new_car_monthly_sales_by_energy (
                        model_key TEXT NOT NULL, model TEXT NOT NULL,energy_type TEXT NOT NULL,sales_month DATE NOT NULL,
                        sales_volume BIGINT NOT NULL CHECK(sales_volume>=0),source_rows JSONB NOT NULL,
                        import_batch TEXT NOT NULL,source_name TEXT NOT NULL,source_sha256 TEXT NOT NULL,
                        imported_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY(model_key,energy_type,sales_month))''')
                    if hashlib.sha256(Path(args.workbook).read_bytes()).hexdigest()!=data['source_sha256']:raise ValueError('Workbook changed during publication')
                    records=[(r['model_key'],r['model'],r['energy_type'],r['month'],r['sales'],json.dumps(r['source_rows']),summary['batch'],data['source_name'],data['source_sha256']) for r in data['rows']]
                    execute_values(cursor,'''INSERT INTO new_car_monthly_sales_by_energy
                        (model_key,model,energy_type,sales_month,sales_volume,source_rows,import_batch,source_name,source_sha256) VALUES %s
                        ON CONFLICT(model_key,energy_type,sales_month) DO UPDATE SET
                        model=EXCLUDED.model,sales_volume=EXCLUDED.sales_volume,source_rows=EXCLUDED.source_rows,
                        import_batch=EXCLUDED.import_batch,source_name=EXCLUDED.source_name,source_sha256=EXCLUDED.source_sha256,imported_at=CURRENT_TIMESTAMP''',records,page_size=1000)
                    cursor.execute('SELECT COUNT(*),SUM(sales_volume) FROM new_car_monthly_sales_by_energy WHERE source_sha256=%s',(data['source_sha256'],))
                    count,total=cursor.fetchone()
                    if count!=data['records'] or int(total)!=data['total_sales']:raise ValueError('Published quantity reconciliation failed')
                    cursor.execute("SELECT DISTINCT grantee FROM information_schema.role_table_grants WHERE table_schema='public' AND table_name='new_car_monthly_sales' AND privilege_type='SELECT'")
                    for (role,) in cursor.fetchall():
                        cursor.execute(sql.SQL('GRANT SELECT ON new_car_monthly_sales_by_energy TO {}').format(sql.Identifier(role)))
                    cursor.execute('SELECT row_to_json(t) FROM new_car_monthly_sales t')
                    if [r[0] for r in cursor.fetchall()]!=legacy:raise ValueError('Legacy sales changed')
                    summary.update(status='published',published_records=count,published_total=int(total),legacy_records_preserved=len(legacy))
        finally:db.close()
    (out/'report.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':main()
