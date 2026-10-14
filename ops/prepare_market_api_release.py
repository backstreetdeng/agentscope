"""Prepare bounded source-transfer commands for the verified bastion terminal.

No secrets are packed. The release overlays only the new API modules onto a
copy of the installed MCP package; existing MCP containers are not replaced.
"""
import base64
import gzip
from pathlib import Path
import json

root=Path(__file__).resolve().parents[1]
folder=root/'runtime'/'market-api-release'
folder.mkdir(parents=True,exist_ok=True)
files={name:(root/'mcp'/'market_data'/name).read_text(encoding='utf-8') for name in ['api_server.py','api_read_models.py']}
blob=base64.b64encode(gzip.compress(json.dumps(files).encode())).decode()
remote='/opt/market-mcp-deploy/api-releases/20261013-v1'
start=f"set -eu\nmkdir -p {remote}\nif [ ! -d {remote}/market_data ]; then docker cp deploy-new-car-mcp-1:/app/mcp/market_data {remote}/; fi\n: > {remote}/package.b64\n"
(folder/'00-stage.sh').write_text(start,encoding='utf-8')
for i in range(0,len(blob),7000):
    text=f"set -eu\nprintf '%s' '{blob[i:i+7000]}' >> {remote}/package.b64\n"
    (folder/f'{1+i//7000:02d}-transfer.sh').write_text(text,encoding='utf-8')
finish=f'''set -eu
python3 -c "import pathlib,json,gzip,base64; p=pathlib.Path('{remote}'); data=json.loads(gzip.decompress(base64.b64decode((p/'package.b64').read_text()))); [(p/'market_data'/name).write_text(text) for name,text in data.items()]"
docker run -d --name market-data-api-20261013 --restart unless-stopped --network deploy_market-mcp --network-alias data-api --env-file /opt/market-mcp-deploy/mcp/deploy/.env -v {remote}/market_data:/app/mcp/market_data:ro deploy-new-car-mcp python -m market_data.api_server
docker exec market-data-api-20261013 python -c "import urllib.request,os; r=urllib.request.Request('http://127.0.0.1:8815/api/v1/new-cars/dashboard',headers={{'Authorization':'Bearer '+os.environ['MCP_API_TOKEN']}}); print('api_smoke_http',urllib.request.urlopen(r,timeout=20).status)"
'''
(folder/'90-start.sh').write_text(finish,encoding='utf-8')
print('prepared_source_transfer',len(blob), 'bytes',len(list(folder.glob('*.sh'))),'commands')
update=(root/'ops'/'update-market-api.sh').read_text(encoding='utf-8')
combined=start+f"printf '%s' '{blob}' >> {remote}/package.b64\n"+update
if len(combined.encode())>16000: raise ValueError('command exceeds bastion transfer bound')
(folder/'95-update-all.sh').write_text(combined,encoding='utf-8')
