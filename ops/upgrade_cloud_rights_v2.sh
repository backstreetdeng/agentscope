set -eu
test "$(id -un)" = ubuntu
test "$(hostname)" = VM-0-13-ubuntu
test -f /opt/price-monitor/rights-mcp/releases/20261012-v2/market_data/cloud_rights.py
grep -q 'releases/20261011-v1' /etc/systemd/system/price-rights-mcp.service
/opt/price-monitor/rights-mcp/venv/bin/python -m compileall -q /opt/price-monitor/rights-mcp/releases/20261012-v2/market_data
sudo -n cp -p /etc/systemd/system/price-rights-mcp.service /opt/price-monitor/rights-mcp/price-rights-mcp.service.v1.backup
sudo -n sed -i 's|releases/20261011-v1|releases/20261012-v2|' /etc/systemd/system/price-rights-mcp.service
sudo -n systemctl daemon-reload
sudo -n systemctl restart price-rights-mcp.service
sudo -n systemctl is-active price-rights-mcp.service
