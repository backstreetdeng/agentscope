set -euo pipefail
echo "=== add column ==="
sudo -u postgres psql -d vectordb -c "ALTER TABLE user_insight.answer ADD COLUMN IF NOT EXISTS sparse_embedding sparsevec(250002)" 2>&1
echo "=== import + update ==="
sudo -u postgres psql -d vectordb -c "CREATE TEMP TABLE tmp_sparse(answer_id text, sv sparsevec(250002)); COPY tmp_sparse FROM '/tmp/sparse_backfill.tsv' WITH (FORMAT text, DELIMITER E'\t'); UPDATE user_insight.answer a SET sparse_embedding = t.sv FROM tmp_sparse t WHERE a.answer_id = t.answer_id; SELECT count(*) AS tmp_rows FROM tmp_sparse;" 2>&1
echo "=== verify counts ==="
sudo -u postgres psql -d vectordb -c "SELECT count(*) AS total, count(sparse_embedding) AS has_sparse FROM user_insight.answer" 2>&1
echo "=== verify sample row ==="
sudo -u postgres psql -d vectordb -c "SELECT answer_id, sparse_embedding FROM user_insight.answer WHERE answer_id='A-R001-Q001'" 2>&1
echo "=== DONE ==="
