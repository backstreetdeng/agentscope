import json,hashlib,re,sys,concurrent.futures
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
from tools.custom_tools import fetch_url_text
run=root/'runtime/weekly-report/weekly-20261014-101813-22d8a00c';state=json.loads((run/'run-state.json').read_text(encoding='utf-8'));assert state['status']=='cancelled'
rows=json.loads((root/'outputs/weekly-report-monitor/window-recompile-candidates.json').read_text(encoding='utf-8'))
sources=json.loads((run/'working/sources.json').read_text(encoding='utf-8'));out=root/'outputs/weekly-report-monitor/window-sources';out.mkdir(exist_ok=True)
urls=list(dict.fromkeys(r['source'] for r in rows if r['source'].startswith(('http://','https://'))))
def one(url):
 sid='src-'+hashlib.sha256(url.encode()).hexdigest()[:24]
 if sources.get(sid,{}).get('fetched'):return dict(url=url,id=sid,cached=True)
 try:
  text=fetch_url_text(url,16000);m=re.search(r'(?m)^Title:\s*(.+)',text);title=m.group(1).strip() if m else '来源原文'
  if len(text)<100:raise ValueError('source too short')
  path=out/(sid+'.txt');path.write_text(text,encoding='utf-8',newline='\n')
  return dict(id=sid,url=url,title=title,text=text,source_file=str(path),text_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),fetched=True,fetch_method='web_fetch',query='用户指定历史窗口重编候选，逐条另行验收')
 except Exception as e:return dict(url=url,id=sid,error=str(e))
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
 result=[]
 for r in pool.map(one,urls):result.append(r);print('cached' if r.get('cached') else 'fetched' if r.get('fetched') else 'failed',r['url'],flush=True)
(out/'sources.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print('sources',len(result),'available',sum(bool(x.get('fetched') or x.get('cached')) for x in result))
