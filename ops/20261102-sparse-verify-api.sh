set -euo pipefail
export HF_ENDPOINT=https://hf-mirror.com
/root/miniconda3/envs/torchai/bin/python -c "
from FlagEmbedding import BGEM3FlagModel
import time
t0=time.time()
model = BGEM3FlagModel('BAAI/bge-m3', use_fp16=False, device='cpu')
print('model_loaded_sec', round(time.time()-t0,1))
out = model.encode('后排空间很大，适合家用带娃', return_dense=False, return_sparse=True, return_colbert_vecs=False)
w = out['lexical_weights'][0]
print('n_items', len(w))
items = list(w.items())[:8]
print('sample', items)
print('max_dim', max(w.keys()))
print('sparse_example_str', '{'+','.join(str(k)+':'+str(round(v,4)) for k,v in list(w.items())[:5])+'}/250002')
" 2>&1
echo "=== DONE ==="
