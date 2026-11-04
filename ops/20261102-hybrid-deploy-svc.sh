set -euo pipefail
mkdir -p /opt/user-insight-sparse
cat > /opt/user-insight-sparse/sparse_server.py << 'PYEOF'
from typing import List
from fastapi import FastAPI
from pydantic import BaseModel
from FlagEmbedding import BGEM3FlagModel

MODEL_PATH = '/root/.cache/huggingface/hub/models--BAAI--bge-m3/snapshots/5617a9f61b028005a4858fdac845db406aefb181'

app = FastAPI(title="user-insight-sparse")

# 启动时加载模型（CPU 推理）
model = BGEM3FlagModel(MODEL_PATH, use_fp16=False, device='cpu')

class SparseRequest(BaseModel):
    texts: List[str]

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/sparse")
def sparse(req: SparseRequest):
    res = model.encode(req.texts, return_dense=False, return_sparse=True, return_colbert_vecs=False)
    lws = res['lexical_weights']
    if not isinstance(lws, list):
        lws = [lws]
    vectors = [[[int(k), float(v)] for k, v in w.items()] for w in lws]
    return {"vectors": vectors}
PYEOF

cd /opt/user-insight-sparse
nohup /root/miniconda3/envs/torchai/bin/python -m uvicorn sparse_server:app --host 0.0.0.0 --port 8091 > /opt/user-insight-sparse/server.log 2>&1 &
echo "started_pid $!"

for i in $(seq 1 40); do
  if curl -sf http://127.0.0.1:8091/health > /dev/null 2>&1; then
    echo "health_ok_after_${i}x2s"
    break
  fi
  sleep 2
done

echo "=== health ==="
curl -s http://127.0.0.1:8091/health; echo ""
echo "=== sparse test ==="
curl -s -X POST http://127.0.0.1:8091/sparse -H 'Content-Type: application/json' -d '{"texts":["后排空间很大","智驾好用"]}' | head -c 400; echo ""
echo "=== log tail ==="
tail -3 /opt/user-insight-sparse/server.log
echo "=== DONE ==="
