set -euo pipefail
echo "=== answer table schema ==="
sudo -u postgres psql -d vectordb -c "select column_name, data_type, udt_name, is_nullable from information_schema.columns where table_schema='user_insight' and table_name='answer' order by ordinal_position" 2>&1
echo "=== embedding col type ==="
sudo -u postgres psql -d vectordb -tAc "select format_type(att.atttypid, att.atttypmod) from pg_attribute att where att.attrelid='user_insight.answer'::regclass and att.attname='embedding'" 2>&1
echo "=== download bge-m3 ==="
export HF_ENDPOINT=https://hf-mirror.com
/root/miniconda3/envs/torchai/bin/python -c "from huggingface_hub import snapshot_download; p=snapshot_download('BAAI/bge-m3'); print('downloaded_to', p)" 2>&1
echo "=== DONE ==="
