"""Manual forecast UI jobs. Engine tools run without a language model."""
from __future__ import annotations
import ast
import csv
import json
import shutil
from pathlib import Path
from threading import Lock, Thread
from datetime import datetime
from integrations.forecast_engine_runtime import (ENGINE, PROJECT, ForecastEngineSession,
    prompt_and_specs, render_answer, validate_arguments)


def status():
    source='unknown'
    for node in ast.parse((ENGINE/'ingest/ingest.py').read_text(encoding='utf-8-sig')).body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SOURCE' for t in node.targets): source=ast.literal_eval(node.value)
    with (ENGINE/'data/retail_monthly.csv').open(encoding='utf-8-sig',newline='') as stream: rows=list(csv.DictReader(stream))
    with (ENGINE/'data/events.csv').open(encoding='utf-8-sig',newline='') as stream: events=list(csv.DictReader(stream))
    synthetic='SAMPLE' in source.upper() or 'PLACEHOLDER' in source.upper()
    config=json.loads((PROJECT/'model_config/config.json').read_text(encoding='utf-8'))
    return dict(available=True,data_status='synthetic' if synthetic else 'real_unvalidated',source=source,
                first_month=min(r['ym'] for r in rows),data_cutoff=max(r['ym'] for r in rows),months=len(rows),
                external_citation_allowed=False,events=[dict(event_id=e['event_id'],label=e.get('note') or e['event_id'],
                    mult_base=float(e['mult_base']),scope=e['scope']) for e in events],
                default_model=config['providers']['deepseek_flash']['model'],complex_model=config['providers']['deepseek_pro']['model'])


class ForecastWebJobs:
    def __init__(self):
        self.sessions={}; self.jobs={}; self.lock=Lock()

    def start(self,payload,run_async):
        name=str(payload.get('tool','run_forecast'))
        specs={s['name']:s for s in prompt_and_specs()[1]}
        if name not in specs: raise ValueError('不支持的预测操作。')
        arguments=payload.get('arguments',{})
        if not isinstance(arguments,dict): raise ValueError('工具参数必须为对象。')
        validate_arguments(specs[name],arguments)
        previous=str(payload.get('run_id') or '')
        with self.lock:
            session=self.sessions.get(previous) if previous else None
            if name=='explain_forecast' and not session:
                raise ValueError('请先运行一次预测，再查看本轮预测依据。')
            if session and self.jobs.get(previous,{}).get('status')=='running':
                raise ValueError('本轮任务仍在执行，请等待结果。')
            if session and name=='explain_forecast':
                parent=session
                session=ForecastEngineSession()
                session.root.mkdir(parents=True)
                shutil.copytree(parent.root/'engine',session.root/'engine')
                (session.root/'README.md').write_text('Read-only explanation of parent forecast snapshot '+parent.run_id+'; private archive copy.\n',encoding='utf-8')
                self.sessions[session.run_id]=session
            if not session: session=ForecastEngineSession(); self.sessions[session.run_id]=session
            # A completed forecast can be explained within the same evidence snapshot.
            if name!='explain_forecast' and previous:
                session=ForecastEngineSession(); self.sessions[session.run_id]=session
            session.prepare()
            job=dict(run_id=session.run_id,status='running',tool=name,arguments=arguments,
                     message='数学引擎正在执行',created_at=datetime.now().astimezone().isoformat(),model_used=False)
            self.jobs[session.run_id]=job; self._save(session,job)
        def work():
            try:
                result=run_async(session.call(name,arguments))
                if not result.get('ok'): raise ValueError(result.get('error') or result.get('data',{}).get('error','预测工具返回错误。'))
                answer,_=render_answer(session,'查看预测依据' if name=='explain_forecast' else '如果调整事件' if name=='adjust_scenario' else '查询历史' if name=='query_indicator' else '运行预测')
                values=dict(status='completed',message='数学结果已生成',data=result['data'],answer=answer,receipt_count=len(session.results))
            except Exception as exc: values=dict(status='failed',message=str(exc)[:500])
            with self.lock:
                job.update(values); self._save(session,job)
        Thread(target=work,daemon=True,name=session.run_id).start()
        return dict(job)

    def _save(self,session,job):
        path=session.root/'web-job.json'; tmp=path.with_suffix('.tmp')
        tmp.write_text(json.dumps(job,ensure_ascii=False,indent=2),encoding='utf-8'); tmp.replace(path)

    def get(self,run_id):
        import re
        if not re.fullmatch(r'forecast-[a-f0-9]{32}',run_id): raise ValueError('无效的预测任务编号。')
        with self.lock:
            if run_id in self.jobs: return dict(self.jobs[run_id])
        path=PROJECT/'runtime/forecast-engine-runs'/run_id/'web-job.json'
        if not path.is_file(): raise ValueError('未找到预测任务。')
        job=json.loads(path.read_text(encoding='utf-8'))
        if job['status']=='running': job.update(status='failed',message='服务重启中断了任务；证据保留，请重新运行。')
        return job


FORECAST_WEB_JOBS=ForecastWebJobs()
