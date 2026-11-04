set -euo pipefail
/root/miniconda3/envs/torchai/bin/python -c "
from FlagEmbedding import BGEM3FlagModel
p='/root/.cache/huggingface/hub/models--BAAI--bge-m3/snapshots/5617a9f61b028005a4858fdac845db406aefb181'
model = BGEM3FlagModel(p, use_fp16=False, device='cpu')
# 批量输入
out = model.encode(['后排空间很大适合家用', '智驾和NOA很好用'], return_dense=False, return_sparse=True, return_colbert_vecs=False)
lw = out['lexical_weights']
print('lw_type', type(lw).__name__, 'len', len(lw))
w0 = lw[0]
print('w0_type', type(w0).__name__, 'n_items', len(w0))
print('sample_items', list(w0.items())[:6])
print('max_dim', max(w0.keys()))
# 单条输入
out1 = model.encode('单条测试', return_dense=False, return_sparse=True, return_colbert_vecs=False)
w1 = out1['lexical_weights']
print('single_type', type(w1).__name__, 'n_items', len(w1))
" 2>&1
echo "=== DONE ==="
