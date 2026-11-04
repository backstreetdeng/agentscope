set -euo pipefail
echo "=== psql client ==="
which psql || ls /usr/lib/postgresql/*/bin/psql 2>/dev/null || echo "no psql"
echo "=== pg 5432 ==="
(ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null) | grep ':5432' || echo "no 5432"
echo "=== sudo postgres peer test ==="
sudo -u postgres psql -d vectordb -tAc "select 'peer_ok', current_user" 2>&1 | head -5 || echo "peer fail"
echo "=== hba_file ==="
HB=$(sudo -u postgres psql -tAc "show hba_file" 2>/dev/null || echo "")
echo "hba_file=$HB"
if [ -n "$HB" ] && [ -f "$HB" ]; then grep -vE '^\s*#|^\s*$' "$HB"; else echo "no hba readable"; fi
echo "=== roles ==="
sudo -u postgres psql -d vectordb -tAc "select rolname from pg_roles where rolname in ('user_insight_loader','market_mcp_reader','vectordb','postgres')" 2>&1
echo "=== schema owner ==="
sudo -u postgres psql -d vectordb -tAc "select nspname, nspowner::regrole from pg_namespace where nspname='user_insight'" 2>&1
echo "=== answer sparse col exists? ==="
sudo -u postgres psql -d vectordb -tAc "select column_name, data_type from information_schema.columns where table_schema='user_insight' and table_name='answer' and column_name like '%sparse%'" 2>&1 || echo "no sparse col"
echo "=== DONE ==="
