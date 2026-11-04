set -euo pipefail
echo "=== answer schema ==="
sudo -u postgres psql -d vectordb -c "select column_name, data_type, udt_name, is_nullable from information_schema.columns where table_schema='user_insight' and table_name='answer' order by ordinal_position" 2>&1
echo "=== embedding type ==="
sudo -u postgres psql -d vectordb -tAc "select format_type(att.atttypid, att.atttypmod) from pg_attribute att where att.attrelid='user_insight.answer'::regclass and att.attname='embedding'" 2>&1
echo "=== model weight present ==="
ls -la /root/.cache/huggingface/hub/models--BAAI--bge-m3/snapshots/*/ 2>/dev/null | grep -iE 'safetensors|pytorch_model|\.bin' || echo "NO_MODEL_WEIGHT_YET"
echo "=== dl proc ==="
ps aux | grep snapshot_download | grep -v grep || echo "DL_DONE"
echo "=== DONE ==="
