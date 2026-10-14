set -eu
task_root=/opt/market-mcp-deploy/mcp
test "$(realpath "$task_root")" = "$task_root"
python3 - <<'PY'
import ast
import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path

root = Path('/opt/market-mcp-deploy/mcp')
p = root / 'market_data/policy_server.py'
assert root.resolve() == root and p.resolve() == p, 'Unexpected target path'
raw = p.read_bytes()
assert hashlib.sha256(raw).hexdigest() == '31279a72854dbc57139ca8b46715747d3eab84730c29791a825c8f76bb6cb311', 'Source changed; stop for review'
s = raw.decode('utf-8')
start = s.index('    @mcp.tool(name="policy_get_status"')
end = s.index('    @mcp.tool(name="policy_search_policies"', start)
block = s[start:end]
old_doc = '        """Return policy source status, record count, version and extraction method."""'
assert block.count(old_doc) == 1
block = block.replace(old_doc, '''        """Return policy source status, effective storage backend, count and version.

        storage_backend is postgres or json, matching the actual dataset loader.
        storage_table is policy_record for postgres and null for file storage.
        These are runtime configuration facts, not additional database columns.
        """''')
needle = '        dataset = _dataset()\n        payload = {'
assert block.count(needle) == 1
block = block.replace(needle, '''        dataset = _dataset()
        # Keep this condition identical to load_domain_dataset; report effective
        # storage rather than echoing an unrecognised environment value.
        backend = "postgres" if os.getenv("MARKET_MCP_BACKEND", "json").casefold() == "postgres" else "json"
        payload = {''')
needle = '            "status": "ready",'
assert block.count(needle) == 1
block = block.replace(needle, '''            "status": "ready",
            "storage_backend": backend,
            "storage_table": "policy_record" if backend == "postgres" else None,''')
new = s[:start] + block + s[end:]
ast.parse(new)
stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
backup_dir = root / 'deploy/backups' / ('policy-status-' + stamp)
assert root in backup_dir.resolve().parents
backup_dir.mkdir(parents=True, exist_ok=False)
backup = backup_dir / 'policy_server.py'
with backup.open('xb') as out:
    out.write(raw)
shutil.copystat(p, backup)
assert backup.read_bytes() == raw
p.write_bytes(new.encode('utf-8'))
print('backup=' + str(backup))
print('new_sha256=' + hashlib.sha256(p.read_bytes()).hexdigest())
PY
cd "$task_root/deploy"
rollback_tag="market-policy-status-rollback:$(date -u +%Y%m%dT%H%M%SZ)"
old_image=$(docker inspect --format '{{.Image}}' deploy-policy-mcp-1)
docker image tag "$old_image" "$rollback_tag"
printf 'rollback_image=%s\n' "$rollback_tag"
docker compose build policy-mcp
docker compose up -d --no-deps policy-mcp
docker compose ps
docker compose logs --tail=20 policy-mcp
