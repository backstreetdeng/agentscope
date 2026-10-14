set -eu
systemctl is-active price-rights-mcp.service || true
ss -lnt | grep ':8812 ' || true
pgrep -f '[p]ip install.*mcp' || true
tail -n 12 /opt/price-monitor/rights-mcp/install.log || true
test -f /etc/systemd/system/price-rights-mcp.service && echo service_file_exists || true
/opt/price-monitor/rights-mcp/venv/bin/python -c 'import mcp,pymysql,openpyxl; print("dependencies_ready")' || true
