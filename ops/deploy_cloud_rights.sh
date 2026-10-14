set -eu
test "$(id -un)" = ubuntu
test "$(hostname)" = VM-0-13-ubuntu
test -f /opt/price-monitor/config.json
test -f /opt/price-monitor/rights-mcp/releases/20261011-v1/market_data/cloud_rights.py
if ss -lnt | grep -q ':8812 '; then echo port_8812_in_use_abort; exit 1; fi
python3 -m venv /opt/price-monitor/rights-mcp/venv
/opt/price-monitor/rights-mcp/venv/bin/pip install --index-url https://mirrors.aliyun.com/pypi/simple/ --timeout 60 --retries 2 'mcp==1.27.2' 'pymysql>=1.1,<2' 'openpyxl>=3.1,<4' >/opt/price-monitor/rights-mcp/install.log 2>&1
python3 - <<'PY'
import secrets,os
from pathlib import Path
p=Path('/opt/price-monitor/rights-mcp/token')
if not p.exists():
    with p.open('x') as f:f.write(secrets.token_hex(32)+'\n')
os.chmod(p,0o600)
PY
test ! -e /etc/systemd/system/price-rights-mcp.service
sudo -n tee /etc/systemd/system/price-rights-mcp.service >/dev/null <<'UNIT'
[Unit]
Description=Read-only Tencent price ledger MCP
After=network.target
[Service]
User=ubuntu
WorkingDirectory=/opt/price-monitor/rights-mcp/releases/20261011-v1
Environment=RIGHTS_MCP_TOKEN_FILE=/opt/price-monitor/rights-mcp/token
Environment=PRICE_MONITOR_CONFIG=/opt/price-monitor/config.json
ExecStart=/opt/price-monitor/rights-mcp/venv/bin/python -m market_data.cloud_rights
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadOnlyPaths=/opt/price-monitor
[Install]
WantedBy=multi-user.target
UNIT
sudo -n systemctl daemon-reload
sudo -n systemctl enable --now price-rights-mcp.service
sudo -n systemctl is-active price-rights-mcp.service
