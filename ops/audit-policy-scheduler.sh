set -eu
printf 'AUTO COLLECT IMPLEMENTATION\n'
docker exec policycrawler-web sh -c 'sed -n "1,180p" /app/src/pipeline/auto_collect.py'
printf '\nSAFE SCHEDULER STATUS\n'
python3 - <<'PY'
import json, urllib.request
try:
    with urllib.request.urlopen('http://127.0.0.1:18080/api/collect/schedule', timeout=15) as r:
        data=json.load(r)
    def safe(v):
        if isinstance(v, dict):
            return {k:safe(x) for k,x in v.items() if not any(w in k.lower() for w in ['token','password','secret','key','credential'])}
        if isinstance(v,list): return [safe(x) for x in v]
        return v
    print(json.dumps(safe(data), ensure_ascii=False))
except Exception as e:
    print(type(e).__name__,str(e))
PY
printf '\nAPI ROUTE REFERENCES\n'
docker exec policycrawler-web sh -c 'grep -nE "@app\.(get|post)|def collect_schedule_status" /app/src/api/main.py | head -110'
