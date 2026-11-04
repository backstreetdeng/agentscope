#!/usr/bin/env bash
# 权益数据底座 · 腾讯云双进程发布（data-api 8815 + rights MCP 8812）。
#
# 源码推送由本地 Windows 的 ops/deploy_cloud_rights_data_api.py 完成（SFTP 上传完整
# market_data 包到 release 目录）；本脚本在云端 ubuntu 本地执行“系统服务发布 + 冒烟”。
# 数据访问与 MCP 协议已分离：
#   - price-rights-data-api.service -> python -m market_data.api_server
#         MARKET_RIGHTS_BACKEND=mysql（唯一持有 MySQL 凭据，TokenAuth 服务 /api/v1/rights/*）
#   - price-rights-mcp.service       -> python -m market_data.rights_server
#         协议适配，经 DATA_API_INTERNAL_URL/TOKEN 调 data-api，保留 token-file Auth
set -eu

ROOT=/opt/price-monitor
RIGHTS="$ROOT/rights-mcp"
VENV="$RIGHTS/venv"
RELEASE="$RIGHTS/releases/20261103-data-api-v1"
UNIT_DIR=/etc/systemd/system

test "$(id -un)" = ubuntu
test "$(hostname)" = VM-0-13-ubuntu
test -f "$ROOT/config.json"
test -f "$RIGHTS/token"
test -f "$RELEASE/market_data/api_server.py"
test -f "$RELEASE/market_data/rights_server.py"
test -f "$RELEASE/market_data/cloud_rights.py"

# 1) 生成 data-api 内部令牌 env 文件（600；从既有 token 文件生成，令牌值不回显）。
sudo -n sh -c 'umask 177; TOKEN=$(cat /opt/price-monitor/rights-mcp/token); printf "DATA_API_INTERNAL_URL=http://127.0.0.1:8815/api/v1\nDATA_API_INTERNAL_TOKEN=%s\n" "$TOKEN" > /opt/price-monitor/rights-mcp/data-api.env; chown ubuntu:ubuntu /opt/price-monitor/rights-mcp/data-api.env; chmod 600 /opt/price-monitor/rights-mcp/data-api.env'

# 2) 校验包可编译、可 import（data-api 与 rights MCP 入口并存）。
"$VENV/bin/python" -m compileall -q "$RELEASE"
(cd "$RELEASE" && "$VENV/bin/python" -c "from market_data.api_server import api_routes; from market_data.rights_server import build_server; print('import_ok')")

# 3) 写两个 systemd 单元（先备份旧 mcp 单元）。
sudo -n cp -a "$UNIT_DIR/price-rights-mcp.service" "$RIGHTS/price-rights-mcp.service.pre-data-api.backup"
sudo -n tee "$UNIT_DIR/price-rights-data-api.service" >/dev/null <<UNIT
[Unit]
Description=Read-only Tencent price ledger data-api (mysql backend)
After=network.target
[Service]
User=ubuntu
WorkingDirectory=$RELEASE
Environment=RIGHTS_MCP_TOKEN_FILE=$RIGHTS/token
Environment=PRICE_MONITOR_CONFIG=$ROOT/config.json
Environment=MARKET_RIGHTS_BACKEND=mysql
Environment=DATA_API_HOST=127.0.0.1
Environment=DATA_API_PORT=8815
ExecStart=$VENV/bin/python -m market_data.api_server
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadOnlyPaths=$ROOT
[Install]
WantedBy=multi-user.target
UNIT

sudo -n tee "$UNIT_DIR/price-rights-mcp.service" >/dev/null <<UNIT
[Unit]
Description=Read-only Tencent price rights MCP (data-api client)
After=network.target price-rights-data-api.service
[Service]
User=ubuntu
WorkingDirectory=$RELEASE
Environment=RIGHTS_MCP_TOKEN_FILE=$RIGHTS/token
Environment=MCP_HOST=127.0.0.1
Environment=MCP_PORT=8812
EnvironmentFile=$RIGHTS/data-api.env
ExecStart=$VENV/bin/python -m market_data.rights_server
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadOnlyPaths=$ROOT
[Install]
WantedBy=multi-user.target
UNIT

sudo -n systemctl daemon-reload
sudo -n systemctl enable --now price-rights-data-api.service
sudo -n systemctl restart price-rights-mcp.service
sleep 2
systemctl is-active price-rights-data-api.service
systemctl is-active price-rights-mcp.service

# 4) 冒烟 data-api（令牌值不回显）。
"$VENV/bin/python" -c 'import urllib.request,json; from pathlib import Path; t=Path("/opt/price-monitor/rights-mcp/token").read_text().strip(); r=urllib.request.Request("http://127.0.0.1:8815/api/v1/rights/overview",headers={"Authorization":"Bearer "+t}); d=json.load(urllib.request.urlopen(r,timeout=30)); print("rights_data_api_ok", d.get("success"), d.get("rights",{}).get("total"))'

echo deploy_cloud_rights_data_api_done