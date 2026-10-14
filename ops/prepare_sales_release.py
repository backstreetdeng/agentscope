import base64,gzip,json,hashlib
from pathlib import Path
root=Path(__file__).resolve().parents[1]
names=['api_read_models.py','monthly_sales_read.py','new_car_server.py']
files={name:(root/'mcp/market_data'/name).read_text(encoding='utf-8') for name in names}
encoded=base64.b64encode(gzip.compress(json.dumps(files,ensure_ascii=False).encode())).decode()
remote='/opt/market-mcp-deploy/sales-releases/20261014-v1'
api='/opt/market-mcp-deploy/api-releases/20261013-v1/market_data'
command=f'''set -eu
mkdir -p {remote}/package {remote}/backup-api {remote}/backup-mcp
test "$(sha256sum {api}/api_read_models.py | cut -d' ' -f1)" = c8ebcb2c12c7620523f708329439b02b1e2471e6c162baa1da0f734d56b66072
docker exec deploy-new-car-mcp-1 python -c "import hashlib; assert hashlib.sha256(open('/app/mcp/market_data/new_car_server.py','rb').read()).hexdigest()=='c6e266e8dc97eb1096d993ae057b8c756674e69cf14dfba3411e2d8fe12537a8'"
cp {api}/api_read_models.py {remote}/backup-api/
docker cp deploy-new-car-mcp-1:/app/mcp/market_data/new_car_server.py {remote}/backup-mcp/
printf '%s' '{encoded}' > {remote}/package.b64
python3 - <<'PY'
import pathlib,json,gzip,base64
p=pathlib.Path('{remote}');files=json.loads(gzip.decompress(base64.b64decode((p/'package.b64').read_text())))
for name,text in files.items():(p/'package'/name).write_text(text)
PY
cp {remote}/package/api_read_models.py {remote}/package/monthly_sales_read.py {api}/
for name in api_read_models.py monthly_sales_read.py new_car_server.py; do docker cp {remote}/package/$name deploy-new-car-mcp-1:/app/mcp/market_data/$name; done
docker exec market-data-api-20261013 python -c "from pathlib import Path; [compile(p.read_text(),str(p),'exec') for p in [Path('/app/mcp/market_data/api_read_models.py'),Path('/app/mcp/market_data/monthly_sales_read.py')]]"
docker exec deploy-new-car-mcp-1 python -m py_compile /app/mcp/market_data/new_car_server.py /app/mcp/market_data/monthly_sales_read.py
docker restart market-data-api-20261013 deploy-new-car-mcp-1
docker exec market-data-api-20261013 python -c "from market_data.api_read_models import new_car_sales; d=new_car_sales({{'model':'理想i8','energy_type':'纯电动'}});print('i8_months',len(d['items']),'total',d['total_sales'],'legacy_kept',d['legacy_months_retained']); assert len(d['items'])==15 and d['legacy_months_retained']==3"
'''
if len(command.encode())>16000:raise ValueError('Bastion command exceeds 16KiB')
(root/'ops/publish-sales-release.sh').write_text(command,encoding='utf-8')
print('prepared_release_bytes',len(command.encode()))
