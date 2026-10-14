"""Scoped live validation of existing raw reputation tables; optional read-only grant."""
import argparse
import json
import os
from pathlib import Path
import sys
from dotenv import dotenv_values
import psycopg2

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'mcp'))
from market_data.reputation_sources import source_status, search_source_reviews, SourceReviewInput

parser=argparse.ArgumentParser()
parser.add_argument('--grant-reader',action='store_true')
args=parser.parse_args()
env=dotenv_values(ROOT/'.env.new-car')
if env['NEW_CAR_PG_HOST']!='192.168.3.146' or env['NEW_CAR_PG_DATABASE']!='vectordb':
    raise ValueError('Unexpected target')
for key in ['HOST','PORT','DATABASE','USER','PASSWORD']:
    value=env.get('NEW_CAR_PG_'+key)
    if value: os.environ['MARKET_PG_'+key]=value
if args.grant_reader:
    with psycopg2.connect(host=env['NEW_CAR_PG_HOST'],port=env.get('NEW_CAR_PG_PORT','5432'),dbname=env['NEW_CAR_PG_DATABASE'],
        user=env['NEW_CAR_PG_USER'],password=env['NEW_CAR_PG_PASSWORD'],connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT has_table_privilege('market_mcp_reader','public.autohome_koubei','SELECT'),has_table_privilege('market_mcp_reader','public.dongchedi_koubei','SELECT')")
            before=cur.fetchone()
            cur.execute('GRANT SELECT ON public.autohome_koubei, public.dongchedi_koubei TO market_mcp_reader')
            print('reader_select_before',before,'reader_select_after',True)
print(json.dumps(source_status(),ensure_ascii=False,default=str))
for model in ['理想i8','星光730新能源']:
    data=search_source_reviews(SourceReviewInput(model=model,limit=2))
    print(json.dumps({'model':model,'total':data['total_count'],'sources':data['sources'],
                     'sample_models':[r['model'] for r in data['items']]},ensure_ascii=False))
