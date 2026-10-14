set -eu
systemctl is-active price-rights-mcp.service
ss -lnt | grep '127.0.0.1:8812 '
