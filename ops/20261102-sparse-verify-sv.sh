set -euo pipefail
echo "=== sparsevec syntax test ==="
sudo -u postgres psql -d vectordb -c "SELECT '{1:0.5,3:0.8}/250002'::sparsevec AS sv" 2>&1
echo "=== sparsevec high dim ==="
sudo -u postgres psql -d vectordb -c "SELECT '{250002:0.7}/250002'::sparsevec AS sv" 2>&1
echo "=== token id range ==="
/root/miniconda3/envs/torchai/bin/python -c "
from FlagEmbedding import BGEM3FlagModel
p='/root/.cache/huggingface/hub/models--BAAI--bge-m3/snapshots/5617a9f61b028005a4858fdac845db406aefb181'
model = BGEM3FlagModel(p, use_fp16=False, device='cpu')
out = model.encode(['后排空间很大适合家用带娃和老人'], return_dense=False, return_sparse=True, return_colbert_vecs=False)
w = out['lexical_weights'][0]
ids = [int(k) for k in w.keys()]
print('max_token_id', max(ids), 'min_token_id', min(ids))
" 2>&1
echo "=== DONE ==="
