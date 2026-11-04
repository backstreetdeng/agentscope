set -euo pipefail
echo "=== MEM ==="
free -h
echo "=== DISK ==="
df -h
echo "=== CPU ==="
nproc
echo "=== PYTHON ==="
for p in python3 python; do command -v $p 2>/dev/null && $p --version 2>&1; done
echo "=== PIP ==="
python3 -m pip --version 2>&1 || true
echo "=== GPU ==="
nvidia-smi 2>&1 | head -20 || echo "NO_NVIDIA_SMI"
echo "=== PORTS 8082/11434 ==="
(ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null) | grep -E ':8082|:11434' || echo "NO_PORT_MATCH"
echo "=== RERANK/EMBED/OLLAMA PROC ==="
ps aux | grep -iE 'rerank|flag|embed|infinity|ollama|uvicorn|python' | grep -v grep || echo "NO_PROC_MATCH"
echo "=== TARGET PY PKGS ==="
python3 -m pip list 2>/dev/null | grep -iE 'flagembedding|torch|sentence-transformers|transformers|fastapi|uvicorn' || echo "NO_TARGET_PKGS"
echo "=== HOME LIST ==="
ls -la /root 2>/dev/null | head -40
echo "=== DONE ==="
