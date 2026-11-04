set -euo pipefail
# 1. 导出 answers（CSV 格式，正确处理换行/逗号）
sudo -u postgres psql -d vectordb -c "COPY (SELECT answer_id, answer_text FROM user_insight.answer ORDER BY answer_id) TO '/tmp/answers.csv' WITH (FORMAT csv)" 2>&1
echo "exported_rows:"; wc -l < /tmp/answers.csv

# 2. 写回填脚本
cat > /tmp/sparse_backfill.py << 'PYEOF'
import csv, time
from FlagEmbedding import BGEM3FlagModel

MODEL_PATH = '/root/.cache/huggingface/hub/models--BAAI--bge-m3/snapshots/5617a9f61b028005a4858fdac845db406aefb181'
VOCAB = 250002
BATCH = 64

t0 = time.time()
model = BGEM3FlagModel(MODEL_PATH, use_fp16=False, device='cpu')
print('model_loaded_sec', round(time.time()-t0,1), flush=True)

answers = []
with open('/tmp/answers.csv', newline='', encoding='utf-8') as f:
    for row in csv.reader(f):
        answers.append((row[0], row[1]))
print('answers', len(answers), flush=True)

def to_sv(w):
    items = sorted((int(k), float(v)) for k, v in w.items())
    inner = ','.join('%d:%s' % (k+1, v) for k, v in items)
    return '{' + inner + '}/%d' % VOCAB

t1 = time.time()
written = 0
with open('/tmp/sparse_backfill.tsv', 'w', encoding='utf-8') as out:
    for i in range(0, len(answers), BATCH):
        batch = answers[i:i+BATCH]
        res = model.encode([a[1] for a in batch], return_dense=False, return_sparse=True, return_colbert_vecs=False)
        lws = res['lexical_weights']
        if not isinstance(lws, list):
            lws = [lws]
        for a, w in zip(batch, lws):
            out.write(a[0] + '\t' + to_sv(w) + '\n')
            written += 1
        if (i // BATCH) % 20 == 0:
            print('progress', i, '/', len(answers), flush=True)
print('encoded', written, 'in', round(time.time()-t1,1), 'sec', flush=True)
PYEOF

# 3. 执行
/root/miniconda3/envs/torchai/bin/python /tmp/sparse_backfill.py 2>&1
chmod 644 /tmp/sparse_backfill.tsv
echo "=== tsv rows ==="
wc -l < /tmp/sparse_backfill.tsv
echo "=== sample head ==="
head -2 /tmp/sparse_backfill.tsv
echo "=== DONE ==="
