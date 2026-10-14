set -eu
printf 'listeners\n'
ss -lnt
printf 'deployment_tools\n'
command -v docker || true
command -v nginx || true
command -v caddy || true
sudo -n true && echo sudo_available || true
/opt/price-monitor/venv/bin/python - <<'PY'
import ast, json
from pathlib import Path
for filename in ('price_runner.py', 'export_delivery.py', 'daily_run.py'):
    source = (Path('/opt/price-monitor')/filename).read_text()
    tree = ast.parse(source)
    print('FILE',filename)
    print('FUNCTIONS', [n.name for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))])
    for n in ast.walk(tree):
        if isinstance(n,ast.Constant) and isinstance(n.value,str):
            value = n.value
            if ('SELECT ' in value.upper() or 'CREATE TABLE' in value.upper()) and ('ledger' in value or 'search_log' in value):
                print('SQL',value)
        if isinstance(n,ast.Assign):
            names = [t.id for t in n.targets if isinstance(t,ast.Name)]
            if any(k in names for k in ('HEADERS','DB_CONFIG','CONFIG_PATH','CONFIG_FILE')):
                if any(k in names for k in ('DB_CONFIG',)):
                    print('CONFIG_KEYS', [k.value for k in n.value.keys if isinstance(k,ast.Constant)] if isinstance(n.value,ast.Dict) else type(n.value).__name__)
                else:
                    print('CONSTANT',ast.get_source_segment(source,n))
    for n in ast.walk(tree):
        if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in ('connect','load'):
            print('CONFIG_CALL',ast.get_source_segment(source,n).splitlines()[0][:180])
        if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id == 'open':
            print('OPEN_CALL',ast.get_source_segment(source,n))
cfgpath=Path('/opt/price-monitor/config.json')
if cfgpath.exists():
    import pymysql
    cfg=json.loads(cfgpath.read_text())
    db=pymysql.connect(**cfg['mysql'],charset='utf8mb4',cursorclass=pymysql.cursors.DictCursor)
    with db.cursor() as c:
        c.execute('START TRANSACTION READ ONLY')
        c.execute('SHOW COLUMNS FROM ledger')
        print('LEDGER_COLUMNS',json.dumps(c.fetchall(),default=str))
        c.execute('SELECT COUNT(*) AS total, COUNT(DISTINCT record_no) AS unique_ids, MAX(monitor_date) AS latest_monitor, MAX(crawl_date) AS latest_crawl FROM ledger')
        print('LEDGER_TOTAL',json.dumps(c.fetchone(),default=str))
        c.execute('SELECT crawl_date, COUNT(*) AS total, COUNT(DISTINCT brand) AS brands FROM ledger GROUP BY crawl_date ORDER BY crawl_date DESC LIMIT 5')
        print('LEDGER_BATCHES',json.dumps(c.fetchall(),default=str))
    db.close()
PY
