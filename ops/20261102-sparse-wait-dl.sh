set -euo pipefail
for i in $(seq 1 60); do
  if ! ps aux | grep snapshot_download | grep -v grep > /dev/null 2>&1; then
    echo "DL_PROC_DONE after ${i}x5s"
    break
  fi
  sleep 5
done
echo "=== weight files ==="
ls -la /root/.cache/huggingface/hub/models--BAAI--bge-m3/snapshots/*/ 2>/dev/null | grep -iE 'safetensors|pytorch_model|\.bin'
echo "=== total size ==="
du -sh /root/.cache/huggingface/hub/models--BAAI--bge-m3 2>/dev/null
echo "=== DONE ==="
