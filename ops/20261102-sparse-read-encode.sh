set -euo pipefail
echo "=== m3.py encode refs ==="
grep -n "def encode\|lexical_weights\|dense_vecs\|colbert_vecs\|return_sparse\|return_dense" /root/miniconda3/envs/torchai/lib/python3.10/site-packages/FlagEmbedding/inference/embedder/encoder_only/m3.py 2>&1
echo "=== base.py encode ==="
grep -rn "def encode" /root/miniconda3/envs/torchai/lib/python3.10/site-packages/FlagEmbedding/inference/embedder/encoder_only/base.py 2>&1
echo "=== base.py encode body ==="
grep -n "lexical_weights\|dense_vecs\|colbert_vecs\|def encode\|return {" /root/miniconda3/envs/torchai/lib/python3.10/site-packages/FlagEmbedding/inference/embedder/encoder_only/base.py 2>&1
echo "=== DONE ==="
