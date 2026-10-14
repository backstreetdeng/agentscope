set -eu
docker inspect market-data-api-20261013 --format '{{.State.Status}}'
docker logs --tail 15 market-data-api-20261013
docker exec market-data-api-20261013 python -c "import urllib.request,os; r=urllib.request.Request('http://127.0.0.1:8815/api/v1/new-cars/dashboard',headers={'Authorization':'Bearer '+os.environ['MCP_API_TOKEN']}); print('api_smoke_http',urllib.request.urlopen(r,timeout=20).status)"
python3 - <<'PY'
from pathlib import Path
import shutil
p=Path('/opt/market-mcp-deploy/mcp/deploy/nginx/default.conf.template')
text=p.read_text()
if 'location /api/v1/' not in text:
    shutil.copy2(p,p.with_name('default.conf.template.pre-api'))
    text=text.replace('    location /downloads/ {','    location /api/v1/ {\n        proxy_pass http://data-api:8815/api/v1/;\n        proxy_http_version 1.1;\n        proxy_read_timeout 30s;\n    }\n    location /downloads/ {')
    p.write_text(text)
PY
docker exec deploy-gateway-1 sh -c 'envsubst "\${MCP_API_TOKEN}" < /etc/nginx/templates/default.conf.template > /tmp/market-api-nginx.conf; cp /etc/nginx/conf.d/default.conf /tmp/default.conf.pre-api; cp /tmp/market-api-nginx.conf /etc/nginx/conf.d/default.conf; if nginx -t; then nginx -s reload; else cp /tmp/default.conf.pre-api /etc/nginx/conf.d/default.conf; exit 1; fi'
