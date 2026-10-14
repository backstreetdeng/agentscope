#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: Docker is not installed or not in PATH."
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "ERROR: Docker Compose v2 is unavailable."
  exit 1
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created deploy/.env. Edit passwords, token and port, then run ./deploy.sh again."
  exit 2
fi

if grep -q 'replace-with\|replace-me' .env; then
  echo "ERROR: deploy/.env still contains placeholder secrets."
  exit 3
fi

docker compose config >/dev/null
docker compose up -d --build
docker compose ps

port="$(sed -n 's/^MCP_GATEWAY_PORT=//p' .env | tail -n 1)"
port="${port:-8788}"
echo "MCP gateway started on port ${port}."
echo "Run database initialization once with:"
echo "  docker compose run --rm policy-mcp python scripts/initialize_database.py"
echo "Then verify from a client machine with scripts/verify_deployment.py."

