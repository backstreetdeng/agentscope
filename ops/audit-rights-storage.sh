set -eu
task_root=/opt/market-mcp-deploy/mcp
test "$(realpath "$task_root")" = "$task_root"
cd "$task_root/deploy"
docker compose ps rights-mcp
docker compose exec -T rights-mcp python -c 'import os; print("effective_backend=" + ("postgres" if os.getenv("MARKET_MCP_BACKEND", "json").casefold() == "postgres" else "json"))'
docker compose exec -T rights-mcp python -c 'import inspect; from market_data.shared import load_domain_dataset; print(inspect.getsource(load_domain_dataset))'
