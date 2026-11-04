set -euo pipefail
echo "=== sample row readback ==="
sudo -u postgres psql -d vectordb -c "SELECT answer_id, sparse_embedding FROM user_insight.answer WHERE answer_id='A-R001-Q001'" 2>&1
echo "=== sparsevec operators ==="
sudo -u postgres psql -d vectordb -c "SELECT oprname, oprleft::regtype, oprright::regtype FROM pg_operator WHERE oprleft='sparsevec'::regtype AND oprright='sparsevec'::regtype ORDER BY oprname" 2>&1
echo "=== inner product test ==="
sudo -u postgres psql -d vectordb -c "SELECT (SELECT sparse_embedding FROM user_insight.answer WHERE answer_id='A-R001-Q001') <#> (SELECT sparse_embedding FROM user_insight.answer WHERE answer_id='A-R001-Q002') AS neg_inner" 2>&1
echo "=== distinct vocab size sanity (avg nonzero) ==="
sudo -u postgres psql -d vectordb -c "SELECT round(avg(length(sparse_embedding::text) - length(replace(sparse_embedding::text,':','')))) AS avg_nonzero_terms FROM user_insight.answer" 2>&1
echo "=== DONE ==="
