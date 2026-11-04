set -euo pipefail
/root/miniconda3/envs/torchai/bin/python -c "
from FlagEmbedding import BGEM3FlagModel
import time
p='/root/.cache/huggingface/hub/models--BAAI--bge-m3/snapshots/5617a9f61b028005a4858fdac845db406aefb181'
t0=time.time()
model = BGEM3FlagModel(p, use_fp16=False, device='cpu')
print('model_loaded_sec', round(time.time()-t0,1))
out = model.encode('后排空间很大，适合家用带娃', return_dense=False, return_sparse=True, return_colbert_vecs=False)
w = out['lexical_weights'][0]
print('n_items', len(w))
print('max_dim', max(w.keys()))
print('sample', list(w.items())[:8])
" 2>&1
echo "=== DONE ==="
