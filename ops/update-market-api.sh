set -eu
python3 - <<'PY'
import pathlib,json,gzip,base64
p=pathlib.Path('/opt/market-mcp-deploy/api-releases/20261013-v1')
files=json.loads(gzip.decompress(base64.b64decode((p/'package.b64').read_text())))
for name,text in files.items(): (p/'market_data'/name).write_text(text)
PY
docker restart market-data-api-20261013
sleep 2
docker exec market-data-api-20261013 python -c "import urllib.request,os; r=urllib.request.Request('http://127.0.0.1:8815/api/v1/new-cars/snapshot',headers={'Authorization':'Bearer '+os.environ['MCP_API_TOKEN']}); print('snapshot_http',urllib.request.urlopen(r,timeout=20).status)"
