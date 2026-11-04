set -euo pipefail
echo "=== runner.py get_model (lines 45-90) ==="
sed -n '45,90p' /root/miniconda3/envs/torchai/lib/python3.10/site-packages/FlagEmbedding/finetune/embedder/encoder_only/m3/runner.py 2>&1
echo "=== m3.py init (lines 70-120) ==="
sed -n '70,120p' /root/miniconda3/envs/torchai/lib/python3.10/site-packages/FlagEmbedding/inference/embedder/encoder_only/m3.py 2>&1
echo "=== DONE ==="
