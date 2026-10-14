"""Scoped rights-service deploy using the established, host-key-verified channel."""
import argparse
from pathlib import Path
import shlex
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from rights_ssh_tunnel import connect

parser=argparse.ArgumentParser(); parser.add_argument('--deploy',action='store_true'); args=parser.parse_args()
client=connect()
def run(command):
    _,stdout,stderr=client.exec_command(command,timeout=60)
    output=stdout.read().decode(); errors=stderr.read().decode()
    code=stdout.channel.recv_exit_status()
    print(output[-10000:]); print(errors[-2000:] if errors else '')
    if code: raise RuntimeError('remote_command_failed_'+str(code))
try:
    run("id -un; hostname; systemctl show price-rights-mcp.service -p WorkingDirectory -p ExecStart; pgrep -af daily_run.py || true")
    if args.deploy:
        release='/opt/price-monitor/rights-mcp/releases/20261013-api-v1'
        run("sudo install -d -o ubuntu -g ubuntu "+release+"; sudo cp -a /opt/price-monitor/rights-mcp/releases/20261012-v2/. "+release+"/; sudo chown -R ubuntu:ubuntu "+release)
        sftp=client.open_sftp()
        root=Path(__file__).resolve().parents[1]/'mcp'/'market_data'
        for name in ['cloud_rights.py','api_server.py','api_read_models.py','new_car_server.py','policy_server.py','reputation_sources.py']:
            sftp.put(str(root/name),release+'/market_data/'+name)
        sftp.close()
        run('/opt/price-monitor/rights-mcp/venv/bin/python -m compileall -q '+release)
        run('cd '+release+' && /opt/price-monitor/rights-mcp/venv/bin/python -c "from market_data.api_server import api_routes; from market_data import cloud_rights; print(\'api_import_ok\')"')
        # Save the service file and change only its release directory.
        run("sudo cp -a /etc/systemd/system/price-rights-mcp.service /opt/price-monitor/rights-mcp/price-rights-mcp.service.pre-api.backup; sudo sed -i 's@20261012-v2@20261013-api-v1@g' /etc/systemd/system/price-rights-mcp.service; sudo systemctl daemon-reload; sudo systemctl restart price-rights-mcp.service; systemctl is-active price-rights-mcp.service")
        try:
            run("sleep 2; cd "+release+" && RIGHTS_MCP_TOKEN_FILE=/opt/price-monitor/rights-mcp/token /opt/price-monitor/rights-mcp/venv/bin/python -c "+shlex.quote("import os,urllib.request; from pathlib import Path; token=Path(os.environ['RIGHTS_MCP_TOKEN_FILE']).read_text().strip(); r=urllib.request.Request('http://127.0.0.1:8812/api/v1/rights/overview',headers={'Authorization':'Bearer '+token}); print('rights_api_http',urllib.request.urlopen(r,timeout=20).status)"))
        except Exception:
            run('sudo cp -a /opt/price-monitor/rights-mcp/price-rights-mcp.service.pre-api.backup /etc/systemd/system/price-rights-mcp.service; sudo systemctl daemon-reload; sudo systemctl restart price-rights-mcp.service')
            raise
finally: client.close()
