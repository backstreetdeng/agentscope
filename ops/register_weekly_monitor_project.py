import sys, json
from pathlib import Path
from urllib.request import urlopen
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
from app import store_project_run
run_id=sys.argv[1] if len(sys.argv)>1 else 'weekly-20261014-101813-22d8a00c'
run=root/'runtime/weekly-report'/run_id
with urlopen('http://127.0.0.1:7860/api/weekly-report/jobs?run_id='+run_id,timeout=15) as response:job=json.load(response)
request=json.loads((run/'inputs/request.json').read_text(encoding='utf-8'))
state=json.loads((run/'run-state.json').read_text(encoding='utf-8'))
result=dict(answer='# 中国汽车产业周度资讯快报 '+request['start_date']+' 至 '+request['end_date']+'\n\n'+job['message']+' 尚未生成交付文件。',agent='market_strategy',model_provider=request['model_provider'],quality=dict(overall_status='验收尚未完成'),formal_delivery_allowed=False,skill=dict(active=True,name='auto-weekly-report',display_name='周度资讯快报自动生成'),skill_run=dict(run_id=run_id,package_hash=job['package_hash'],state=state,artifacts=[]),tool_events=[dict(name=s['id'],status=s['status'],detail=s['summary']) for s in job['steps'] if s['status']!='pending'])
project=store_project_run(result,request.get('question',''),'auto_weekly_report',request['model_provider'],['auto_weekly_report'],run_id=run_id,replace_existing=True)
print(json.dumps(dict(id=project['id'],status=project['status'],url=project['detail_url']),ensure_ascii=False))
