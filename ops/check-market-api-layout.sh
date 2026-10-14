set -eu
cd /opt/market-mcp-deploy/mcp/deploy
docker inspect deploy-policy-mcp-1 --format '{{json .Mounts}}'
docker inspect deploy-gateway-1 --format '{{json .Mounts}}'
sed -n '1,140p' docker-compose.yml
sed -n '1,140p' nginx/default.conf.template
docker exec deploy-policy-mcp-1 python -c "import starlette,uvicorn; print('api_dependencies_available')"
