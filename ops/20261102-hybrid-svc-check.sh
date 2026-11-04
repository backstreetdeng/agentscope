set -euo pipefail
echo "=== fastapi/uvicorn check ==="
/root/miniconda3/envs/torchai/bin/python -c "import fastapi, uvicorn; print('fastapi', fastapi.__version__, 'uvicorn', uvicorn.__version__)" 2>&1
echo "=== port 8091 free? ==="
(ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null) | grep ':8091' || echo "port 8091 free"
echo "=== DONE ==="
