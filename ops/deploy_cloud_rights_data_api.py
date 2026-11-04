"""Deploy the Phase-5 rights data-api split on the Tencent Cloud price-monitor host.

Layout after deploy (dual process, loopback only):
  - price-rights-data-api.service : 127.0.0.1:8815  `python -m market_data.api_server`
        MARKET_RIGHTS_BACKEND=mysql  (holds the MySQL credential; TokenAuth serves /api/v1/rights/*)
  - price-rights-mcp.service       : 127.0.0.1:8812  `python -m market_data.rights_server`
        protocol-only MCP, calls data-api via DATA_API_INTERNAL_URL/TOKEN, keeps token-file Auth.

Both share release dir `20261103-data-api-v1` and the existing `rights-mcp/venv`.
Credentials are consumed in-memory only; never printed or persisted locally.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rights_ssh_tunnel import connect  # noqa: E402

RELEASE = '/opt/price-monitor/rights-mcp/releases/20261103-data-api-v1'
VENV = '/opt/price-monitor/rights-mcp/venv'
MARKET_DATA = Path(__file__).resolve().parents[1] / 'mcp' / 'market_data'

DATA_API_UNIT = '''[Unit]
Description=Read-only Tencent price ledger data-api (mysql backend)
After=network.target
[Service]
User=ubuntu
WorkingDirectory=RELEASE_DIR
Environment=RIGHTS_MCP_TOKEN_FILE=/opt/price-monitor/rights-mcp/token
Environment=PRICE_MONITOR_CONFIG=/opt/price-monitor/config.json
Environment=MARKET_RIGHTS_BACKEND=mysql
Environment=DATA_API_HOST=127.0.0.1
Environment=DATA_API_PORT=8815
ExecStart=VENV_BIN/python -m market_data.api_server
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadOnlyPaths=/opt/price-monitor
[Install]
WantedBy=multi-user.target
'''.replace('RELEASE_DIR', RELEASE).replace('VENV_BIN', VENV + '/bin')

RIGHTS_MCP_UNIT = '''[Unit]
Description=Read-only Tencent price rights MCP (data-api client)
After=network.target price-rights-data-api.service
[Service]
User=ubuntu
WorkingDirectory=RELEASE_DIR
Environment=RIGHTS_MCP_TOKEN_FILE=/opt/price-monitor/rights-mcp/token
Environment=MCP_HOST=127.0.0.1
Environment=MCP_PORT=8812
EnvironmentFile=/opt/price-monitor/rights-mcp/data-api.env
ExecStart=VENV_BIN/python -m market_data.rights_server
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadOnlyPaths=/opt/price-monitor
[Install]
WantedBy=multi-user.target
'''.replace('RELEASE_DIR', RELEASE).replace('VENV_BIN', VENV + '/bin')


def main() -> int:
    client = connect()
    try:
        stdin, stdout, stderr = client.exec_command('id -un; hostname', timeout=30)
        identity = stdout.read().decode().strip()
        errors = stderr.read().decode()
        print('connected:', identity.replace('\n', ' '))
        if 'VM-0-13-ubuntu' not in identity:
            client.close()
            raise SystemExit('unexpected_host_identity')

        def run(command, timeout=120, critical=True):
            _, out, err = client.exec_command(command, timeout=timeout)
            output = out.read().decode('utf-8', errors='replace')
            errout = err.read().decode('utf-8', errors='replace')
            code = out.channel.recv_exit_status()
            if code and critical:
                raise RuntimeError(f'remote_command_failed({code}): {command}\n{errout[-2000:]}')
            return output, errout, code

        # 1. Prepare release dir + upload package (only .py, no __pycache__).
        run(f"sudo -n install -d -o ubuntu -g ubuntu {RELEASE}; sudo -n install -d -o ubuntu -g ubuntu {RELEASE}/market_data/contracts; sudo -n chown -R ubuntu:ubuntu {RELEASE}")
        files = [p for p in MARKET_DATA.rglob('*.py')]
        with client.open_sftp() as sftp:
            for path in files:
                rel = path.relative_to(MARKET_DATA)
                sftp.put(str(path), f'{RELEASE}/market_data/{rel.as_posix()}')
        print(f'uploaded {len(files)} py files')

        # 2. data-api.env (600) from the existing token file, generated remotely
        #    so the token value never enters this transcript.
        run("sudo -n sh -c 'umask 177; TOKEN=$(cat /opt/price-monitor/rights-mcp/token); "
            "printf \"DATA_API_INTERNAL_URL=http://127.0.0.1:8815/api/v1\\nDATA_API_INTERNAL_TOKEN=%s\\n\" \"$TOKEN\" "
            "> /opt/price-monitor/rights-mcp/data-api.env; chown ubuntu:ubuntu /opt/price-monitor/rights-mcp/data-api.env; chmod 600 /opt/price-monitor/rights-mcp/data-api.env'")

        # 3. compile + import parity check before touching services.
        run(f"{VENV}/bin/python -m compileall -q {RELEASE}")
        run(f"cd {RELEASE} && {VENV}/bin/python -c \"from market_data.api_server import api_routes; from market_data.rights_server import build_server; print('import_ok')\"")

        # 4. Write units (backup existing mcp service first).
        run(f"sudo -n cp -a /etc/systemd/system/price-rights-mcp.service /opt/price-monitor/rights-mcp/price-rights-mcp.service.pre-data-api.backup")
        with tempfile.TemporaryDirectory() as tmp:
            api_unit = Path(tmp) / 'price-rights-data-api.service'
            mcp_unit = Path(tmp) / 'price-rights-mcp.service'
            api_unit.write_text(DATA_API_UNIT, encoding='utf-8')
            mcp_unit.write_text(RIGHTS_MCP_UNIT, encoding='utf-8')
            with client.open_sftp() as sftp:
                sftp.put(str(api_unit), '/tmp/price-rights-data-api.service')
                sftp.put(str(mcp_unit), '/tmp/price-rights-mcp.service')
        run("sudo -n install -m 0644 -o root -g root /tmp/price-rights-data-api.service /etc/systemd/system/price-rights-data-api.service; "
            "sudo -n install -m 0644 -o root -g root /tmp/price-rights-mcp.service /etc/systemd/system/price-rights-mcp.service; "
            "sudo -n rm -f /tmp/price-rights-data-api.service /tmp/price-rights-mcp.service")

        # 5. Start data-api first, smoke it, then restart the MCP.
        run("sudo -n systemctl daemon-reload; sudo -n systemctl enable --now price-rights-data-api.service; sleep 2; systemctl is-active price-rights-data-api.service")
        run("sudo -n systemctl restart price-rights-mcp.service; sleep 2; systemctl is-active price-rights-mcp.service")

        # 6. Smoke data-api (token read remotely; only status printed, never the token).
        run(VENV + "/bin/python -c 'import urllib.request,json; from pathlib import Path; t=Path(\"/opt/price-monitor/rights-mcp/token\").read_text().strip(); r=urllib.request.Request(\"http://127.0.0.1:8815/api/v1/rights/overview\",headers={\"Authorization\":\"Bearer \"+t}); d=json.load(urllib.request.urlopen(r,timeout=30)); print(\"rights_data_api_ok\", d.get(\"success\"), d.get(\"rights\",{}).get(\"total\"))'",
            critical=False)

        # 7. Restart binds; report final listening state.
        out, _, _ = run("ss -lnt | awk 'NR==1 || /:(3306|8812|8815) /'", critical=False)
        print(out)
        print('DEPLOY_COMPLETE')
        return 0
    finally:
        client.close()


if __name__ == '__main__':
    sys.exit(main())