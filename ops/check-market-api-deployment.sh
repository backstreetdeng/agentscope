set -eu
docker ps --format '{{.Names}} {{.Image}} {{.Ports}}'
find /opt /srv -maxdepth 4 -name docker-compose.yml -o -name compose.yml 2>/dev/null | head -40
ss -lnt | grep -E '8790|8788|881[1-5]'
