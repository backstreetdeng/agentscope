set -eu
cd /opt/market-mcp-deploy/mcp/deploy
test "$(realpath ..)" = /opt/market-mcp-deploy/mcp
docker compose ps reputation-mcp gateway
docker inspect --format '{{.Name}} {{.Image}} {{json .Mounts}}' deploy-reputation-mcp-1
sha256sum ../market_data/reputation_server.py
test -f ../market_data/reputation_sources.py && sha256sum ../market_data/reputation_sources.py || true
