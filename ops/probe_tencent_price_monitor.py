"""Read-only SSH probe; credentials are consumed in memory and never logged."""
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path.home() / 'AppData/Local/Codex/ssh-146/python-packages'))
import paramiko

credential_path = Path('C:/Users/11489/.codex/skills/tencent-cloud-price-monitor-ssh/.env')
text = credential_path.read_text(encoding='utf-8-sig')
lines = text.splitlines()
password = None
for index, line in enumerate(lines):
    match = re.match(r'^\s*(?:[-*]\s*)?(?:\*\*)?(?:密码|登录密码|服务器密码|SSH_PASSWORD|PASSWORD)(?:\*\*)?\s*[:：=]\s*(.*?)\s*$', line, re.I)
    if match:
        password = match.group(1).strip().strip('`').strip('"').strip("'")
        if not password and index + 1 < len(lines):
            password = lines[index + 1].strip().strip('`')
        break
if not password:
    print('credential_format_not_recognized; no authentication attempted')
    sys.exit(2)

client = paramiko.SSHClient()
client.load_host_keys(str(Path.home() / '.ssh/known_hosts'))
client.set_missing_host_key_policy(paramiko.RejectPolicy())
try:
    client.connect('82.157.138.187', port=22, username='ubuntu', password=password,
                   look_for_keys=False, allow_agent=False, timeout=15, auth_timeout=15)
    command = """set -eu
id -un
hostname
test -d /opt/price-monitor && echo price_monitor_directory_present
systemctl is-active mysql || true
printf 'database_containers\\n'
docker ps --format '{{.Names}} {{.Image}} {{.Status}}' | grep -Ei 'mysql|maria' || true
printf 'database_process_names\\n'
ps -eo comm | grep -E '^(mysqld|mariadbd)$' || true
ss -lnt | awk 'NR==1 || /:3306 /'
printf 'daily_run_process_ids\\n'
pgrep -f '[d]aily_run.py' || true
/opt/price-monitor/venv/bin/python - <<'PY'
from pathlib import Path
import json
runs = Path('/opt/price-monitor/runs')
for path in sorted((p for p in runs.iterdir() if p.is_dir()), reverse=True)[:4]:
    result = {'date': path.name, 'success': (path/'SUCCESS.json').exists(), 'failed': (path/'FAILED.json').exists()}
    done = path/'done_brands.txt'
    if done.exists():
        result['done_brands'] = len(set(x.strip() for x in done.read_text().splitlines() if x.strip()))
    success = path/'SUCCESS.json'
    if success.exists():
        data = json.loads(success.read_text())
        result['success_metadata_keys'] = list(data) if isinstance(data, dict) else []
        if isinstance(data, dict):
            for key in ('target_date', 'started_at', 'ended_at', 'finished_at', 'duration_seconds', 'brands_completed', 'new_records', 'inserted_records', 'valid_queries'):
                if key in data and isinstance(data[key], (str, int, float, bool)):
                    result[key] = data[key]
    print(json.dumps(result, ensure_ascii=False))
print('project_python_files:', ', '.join(p.name for p in Path('/opt/price-monitor').glob('*.py')))
PY
"""
    if '--upload-dir' in sys.argv:
        folder=Path(sys.argv[sys.argv.index('--upload-dir')+1])
        remote=sys.argv[sys.argv.index('--remote-dir')+1]
        if not remote.startswith('/opt/price-monitor/rights-mcp/releases/'):
            raise ValueError('upload scope invalid')
        _, out, _=client.exec_command('mkdir -p '+remote+'/market_data')
        if out.channel.recv_exit_status(): raise RuntimeError('mkdir failed')
        with client.open_sftp() as sftp:
            for name in ('__init__.py','shared.py','cloud_rights.py'):
                sftp.put(str(folder/name),remote+'/market_data/'+name)
        print('new_release_uploaded')
    if '--command-file' in sys.argv:
        command = Path(sys.argv[sys.argv.index('--command-file')+1]).read_text(encoding='utf-8-sig')
    _, stdout, stderr = client.exec_command(command, timeout=300 if '--upload-dir' in sys.argv else 40)
    print(stdout.read().decode('utf-8', errors='replace'))
    code = stdout.channel.recv_exit_status()
    if code:
        print('remote_probe_incomplete', code)  # Never dump arbitrary runtime errors.
    if code == 0 and '--configure-local' in sys.argv:
        with client.open_sftp() as sftp:
            with sftp.open('/opt/price-monitor/rights-mcp/token','r') as f:
                token=f.read().decode().strip()
        if len(token)<32: raise ValueError('invalid token')
        envpath=Path(__file__).resolve().parents[1]/'.env'
        content=envpath.read_text(encoding='utf-8-sig')
        backup=envpath.parent/'runtime'/'rights-cloud-before.env'
        if not backup.exists():
            backup.write_text(content,encoding='utf-8')
        entries={'MARKET_MCP_RIGHTS_URL':'http://127.0.0.1:18812/mcp','MARKET_MCP_RIGHTS_API_TOKEN':token}
        newlines=[line for line in content.splitlines() if not any(re.match(r'^\s*'+key+r'\s*=',line) for key in entries)]
        newlines.extend(k+'='+v for k,v in entries.items())
        envpath.write_text('\n'.join(newlines)+'\n',encoding='utf-8')
        print('local_rights_configuration_updated; credentials withheld')
    sys.exit(code)
except paramiko.AuthenticationException:
    print('authentication_failed; no retry')
    sys.exit(3)
except Exception as exc:
    print('connection_failed:', type(exc).__name__)
    sys.exit(4)
finally:
    password = None
    client.close()
