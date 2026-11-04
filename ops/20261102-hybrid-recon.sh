set -euo pipefail
echo "=== tag cols ==="
sudo -u postgres psql -d vectordb -c "SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='user_insight' AND table_name='tag' ORDER BY ordinal_position" 2>&1
echo "=== tag_evidence cols ==="
sudo -u postgres psql -d vectordb -c "SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='user_insight' AND table_name='tag_evidence' ORDER BY ordinal_position" 2>&1
echo "=== content_group dist ==="
sudo -u postgres psql -d vectordb -c "SELECT content_group, count(*) FROM user_insight.tag GROUP BY content_group ORDER BY count(*) DESC" 2>&1
echo "=== tag sample ==="
sudo -u postgres psql -d vectordb -c "SELECT * FROM user_insight.tag LIMIT 5" 2>&1
echo "=== sparsevec operators ==="
sudo -u postgres psql -d vectordb -c "SELECT oprname, oprcode::regproc FROM pg_operator WHERE oprleft='sparsevec'::regtype AND oprright='sparsevec'::regtype ORDER BY oprname" 2>&1
echo "=== DONE ==="
