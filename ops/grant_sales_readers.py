"""Retain the existing sales service's SELECT boundary on the additive table."""
from pathlib import Path
from dotenv import dotenv_values
import psycopg2
from psycopg2 import sql
root=Path(__file__).resolve().parents[1]
env={**dotenv_values(root/'.env'),**dotenv_values(root/'.env.new-car')}
assert env['NEW_CAR_PG_HOST']=='192.168.3.146' and env['NEW_CAR_PG_DATABASE']=='vectordb'
db=psycopg2.connect(host=env['NEW_CAR_PG_HOST'],port=int(env.get('NEW_CAR_PG_PORT',5432)),dbname=env['NEW_CAR_PG_DATABASE'],user=env['NEW_CAR_PG_USER'],password=env['NEW_CAR_PG_PASSWORD'],connect_timeout=15)
with db:
    with db.cursor() as c:
        c.execute("SELECT DISTINCT grantee FROM information_schema.role_table_grants WHERE table_schema='public' AND table_name='new_car_monthly_sales' AND privilege_type='SELECT'")
        existing={r[0] for r in c.fetchall()}
        assert 'market_mcp_reader' in existing
        roles=['market_mcp_reader']
        for role in roles:c.execute(sql.SQL('GRANT SELECT ON new_car_monthly_sales_by_energy TO {}').format(sql.Identifier(role)))
        print('Existing sales SELECT roles preserved:',len(roles))
db.close()
