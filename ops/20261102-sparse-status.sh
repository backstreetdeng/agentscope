set -euo pipefail
echo "=== column exists? ==="
sudo -u postgres psql -d vectordb -tAc "select column_name, udt_name from information_schema.columns where table_schema='user_insight' and table_name='answer' and column_name='sparse_embedding'" 2>&1
echo "=== counts ==="
sudo -u postgres psql -d vectordb -tAc "select count(*), count(sparse_embedding) from user_insight.answer" 2>&1
echo "=== tsv file ==="
ls -la /tmp/sparse_backfill.tsv 2>&1
echo "=== active locks on answer ==="
sudo -u postgres psql -d vectordb -tAc "select count(*) from pg_locks l join pg_class c on l.relation=c.oid where c.relname='answer'" 2>&1
echo "=== pg activity ==="
sudo -u postgres psql -d vectordb -tAc "select pid, state, left(query,60) from pg_stat_activity where datname='vectordb' and state<>'idle'" 2>&1
echo "=== DONE ==="
