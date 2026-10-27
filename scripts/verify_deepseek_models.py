"""Minimal user-authorized DeepSeek preflight; never prints credentials or responses."""
from datetime import datetime
import json
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))


def main():
    from dotenv import dotenv_values
    key=dotenv_values(PROJECT/'.env').get('DASHSCOPE_API_KEY')
    if not key: raise RuntimeError('DASHSCOPE_API_KEY is absent; no request sent')
    output=PROJECT/'outputs/deepseek-configuration'/datetime.now().strftime('%Y%m%d-%H%M%S')
    output.mkdir(parents=True)
    rows=[]
    for model in ('deepseek-v4-flash','deepseek-v4-pro'):
        payload=dict(model=model,messages=[dict(role='user',content='Reply with OK only.')],max_tokens=32,stream=False,thinking={'type':'disabled'})
        request=Request('https://api.deepseek.com/chat/completions',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
        try:
            with urlopen(request,timeout=45) as response:
                data=json.load(response)
                rows.append(dict(requested_model=model,response_model=data.get('model'),status=response.status,
                                 passed=bool(data.get('choices'))))
        except HTTPError as exc: rows.append(dict(requested_model=model,status=exc.code,passed=False))
        except (URLError,TimeoutError): rows.append(dict(requested_model=model,status='network_error',passed=False))
        print(json.dumps(rows[-1],ensure_ascii=False),flush=True)
    (output/'verification.json').write_text(json.dumps(dict(endpoint='https://api.deepseek.com/chat/completions',credential_variable='DASHSCOPE_API_KEY',results=rows),ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'README.md').write_text('Minimal DeepSeek provider preflight. No API key, response text or reasoning retained.\nReproduce: ../Scripts/python.exe -B scripts/verify_deepseek_models.py\n',encoding='utf-8')
    return 0 if all(r['passed'] for r in rows) else 1


if __name__=='__main__': raise SystemExit(main())
