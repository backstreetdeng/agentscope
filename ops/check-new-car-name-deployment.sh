set -euo pipefail
cd /opt/market-mcp-deploy/mcp/deploy
test "$(realpath ..)" = /opt/market-mcp-deploy/mcp
docker compose ps new-car-mcp gateway
docker inspect --format '{{.Name}} {{.Image}}' deploy-new-car-mcp-1
sha256sum ../market_data/new_car_server.py
