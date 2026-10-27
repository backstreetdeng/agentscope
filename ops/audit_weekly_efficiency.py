import json, sys
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict
root=Path(__file__).resolve().parents[1]
run=root/'runtime/weekly-report/weekly-20261014-101813-22d8a00c'
events=[json.loads(line) for line in (run/'checkpoints.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
opened={};durations=defaultdict(list);searches=Counter();fetches=Counter();submits=Counter();rejects=Counter();accepts=defaultdict(list)
for event in events:
    data=event.get('data',{});message=event.get('message','');at=datetime.fromisoformat(event['at'])
    if message.startswith('任务 ') and ' 更新为 ' in message:
        sid=message.split()[1];status=message.split(' 更新为 ')[1]
        if status=='running':opened[sid]=at
        elif sid in opened:
            durations[sid].append(dict(start=opened[sid].isoformat(),end=at.isoformat(),seconds=round((at-opened.pop(sid)).total_seconds()),end_status=status))
    sid=data.get('section')
    if message=='联网检索完成':searches[sid]+=1
    if message=='来源正文已读取':fetches[sid]+=1
    if message=='结构化工具提交并核验条目':
        submits[sid]+=1
        accepts[sid].append(dict(at=at.isoformat(),accepted=data.get('accepted',0)))
        for item in data.get('rejected',[]):rejects.update(item.get('errors',[]))
checks={p.name:json.loads(p.read_text(encoding='utf-8')) for p in run.joinpath('working').glob('model-check-*.json')}
state=json.loads((run/'run-state.json').read_text(encoding='utf-8'))
result=dict(run_id=state['run_id'],status=state['status'],created_at=state['created_at'],stopped_at=state['updated_at'],wall_minutes=round((datetime.fromisoformat(state['updated_at'])-datetime.fromisoformat(state['created_at'])).total_seconds()/60,1),completed_business_sections=[s['id'] for s in state['plan'] if s['status']=='completed' and s['id']!='package'],durations=dict(durations),search_count=dict(searches),fetch_count=dict(fetches),submit_count=dict(submits),accepted_timeline=dict(accepts),rejection_counts=rejects.most_common(),model_checks=checks,limits=dict(serial_sections=14,attempts_per_section=2,seconds_per_attempt=600,react_iterations_per_attempt=18,searches_per_section=10),timing_limit='模型与工具缺少开始/结束逐调用计时，不能把日志之间空白全部算作模型耗时')
out=root/'outputs/weekly-report-monitor/efficiency-audit.json';out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
