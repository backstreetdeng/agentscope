set -eu
task_root=/opt/market-mcp-deploy/mcp
test "$(realpath "$task_root")" = "$task_root"
test -f "$task_root/market_data/policy_server.py"
sha256sum "$task_root/market_data/policy_server.py"
python3 - <<'PY'
from pathlib import Path
p = Path('/opt/market-mcp-deploy/mcp/market_data/policy_server.py')
s = p.read_text(encoding='utf-8')
start = s.index('    @mcp.tool(name="policy_get_status"')
end = s.index('    @mcp.tool(name="policy_search_policies"', start)
print(s[start:end])
PY
cd "$task_root/deploy"
docker compose ps
docker compose exec -T policy-mcp python -c 'import os; print("effective_backend=" + ("postgres" if os.getenv("MARKET_MCP_BACKEND", "json").casefold() == "postgres" else "json"))'
docker inspect --format '{{.Image}}' deploy-policy-mcp-1
