"""Full-package, resumable weekly brief execution and verified three-file delivery."""
from __future__ import annotations
import asyncio, hashlib, importlib.util, json, re, shutil, time, os
from datetime import datetime, timedelta, timezone, date
from pathlib import Path
from threading import Lock, Thread, Event
from uuid import uuid4
from skill_runtime import SkillRegistry, SkillRunContext
from skill_runtime.tools import SkillRunScriptTool
TZ=timezone(timedelta(hours=8))

def now(): return datetime.now(TZ).isoformat(timespec='seconds')
def read(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.'+uuid4().hex+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8',newline='\n')
    for attempt in range(6):
        try:temp.replace(path);break
        except PermissionError:
            if attempt==5:raise
            time.sleep(0.05*(attempt+1))

def default_period(today=None):
    today=today or datetime.now(TZ).date()
    end=today-timedelta(days=(today.weekday()-4)%7)
    return (end-timedelta(days=6)).isoformat(),end.isoformat()

def validator(package):
    path=package.resolve('scripts/validate_weekly.py')
    spec=importlib.util.spec_from_file_location('weekly_validator_'+package.package_hash[:12],path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

class ExecutionLock:
    def __init__(self,path):self.path=Path(path);self.file=None
    def acquire(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.file=self.path.open('a+b');self.file.seek(0,2)
        if not self.file.tell():self.file.write(b'0');self.file.flush()
        self.file.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            return True
        except OSError:self.close();return False
    def close(self):
        if self.file:self.file.close();self.file=None

def build_visual(sections,start,end):
    counts={}
    items=[]
    for block in sections:
        counts[block['section']]=counts.get(block['section'],0)+len(block['items'])
        items.extend(block['items'])
    highest=max(counts.values(),default=1) or 1
    timeline=[]
    for item in sorted(items,key=lambda row:row['event_date']):
        if item['event_date'] not in [entry['date'] for entry in timeline]:
            timeline.append(dict(date=item['event_date'],name=item['title'],desc=item['body'][:80],done=True))
    return dict(hook_title='中国汽车产业周度资讯快报',hook_sub=f'{start} 至 {end} · 已核验资讯',
        meta=[f'事件窗口 {start} 至 {end}','九大章节 · 逐条来源核验'],
        kpis=[dict(num=str(len(items)),unit='条',label='本期已核验资讯'),dict(num=str(len(counts)),unit='章',label='固定章节'),dict(num=str(len(sections)),unit='个',label='板块小节')],
        bars=[dict(title='本期资讯分布',note='统计本报告收录条数，不代表行业规模或市场份额。',rows=[dict(k=name,label=f'{count}条',pct=round(count/highest*100,2),color='#2563eb',v=f'{count}条') for name,count in counts.items()])],
        timeline=timeline[:8],footer_note='按事件真实发生日收录；已报道事件、周期性汽车运营数据、纯海外与预告剔除。')

class Cancelled(RuntimeError): pass

class WeeklyReportJobs:
    def __init__(self,project_dir,skill_dir,config_loader,section_runner,on_complete=None,office_validation=True):
        self.project_dir=Path(project_dir).resolve();self.skill_dir=Path(skill_dir).resolve()
        self.root=self.project_dir/'runtime/weekly-report';self.data_dir=self.project_dir/'data/weekly-report'
        self.config_loader=config_loader;self.section_runner=section_runner;self.on_complete=on_complete
        self.office_validation=office_validation
        self.lock=Lock();self.active=set();self.cancel_events={}

    def _run_path(self,run_id):
        if not re.fullmatch(r'weekly-\d{8}-\d{6}-[a-f0-9]{8}',str(run_id)): raise ValueError('周报任务编号无效。')
        root=self.root/run_id
        if not (root/'run-state.json').is_file(): raise ValueError('未找到这次周报任务。')
        return root

    def _package(self,root):
        package=SkillRegistry([root/'working/skill-package']).get('auto-weekly-report')
        state=read(root/'run-state.json')
        if package.package_hash!=state['package_hash']:raise ValueError('本次锁定的技能包内容已改变，已停止恢复。')
        self._verify_integrity(package)
        for relative in read(package.resolve('package-manifest.json')).get('web_runtime', []):
            current=self.project_dir/'utils'/Path(relative).name
            if current.is_file() and digest(current)!=digest(package.resolve(relative)):
                raise ValueError('执行器版本与本轮锁定版本不一致；已保留原任务与全部证据。')
        return package

    @staticmethod
    def _verify_integrity(package):
        manifest=read(package.resolve('package-manifest.json'))
        for relative in [*manifest['knowledge'],*manifest['scripts'],manifest['template']]:package.resolve(relative)
        for relative,expected in read(package.resolve('package-integrity.json')).items():
            if digest(package.resolve(relative))!=expected:raise ValueError('技能资源指纹不匹配：'+relative)

    def status(self):
        try:
            package=SkillRegistry([self.skill_dir.parent]).get('auto-weekly-report');self._verify_integrity(package)
            import docx,lxml
            start,end=default_period()
            return dict(available=True,name='周度资讯快报自动生成',skill_id=package.skill_id,package_hash=package.package_hash,
                        resources=len(package.resources()),default_start=start,default_end=end,
                        deliverables=['HTML阅读版','Word正报','来源文档'],date_basis='Asia/Shanghai')
        except Exception as exc:return dict(available=False,name='周度资讯快报自动生成',error=str(exc))

    def start(self,payload):
        start,end=default_period();start=str(payload.get('start_date') or start);end=str(payload.get('end_date') or end)
        first,last=date.fromisoformat(start),date.fromisoformat(end)
        if first>last or (last-first).days>30:raise ValueError('开始日期应不晚于结束日期，单次范围最多31天。')
        if last>datetime.now(TZ).date():raise ValueError('结束日期不能晚于当前上海日期；请等待实际事件发生后生成。')
        provider=str(payload.get('model_provider') or 'minimax');self.config_loader(provider)
        with self.lock:
            # A retry after a lost HTTP response cannot launch duplicate research.
            for path in sorted(self.root.glob('weekly-*/inputs/request.json'),reverse=True):
                prior=read(path); state=read(path.parent.parent/'run-state.json')
                if prior.get('start_date')==start and prior.get('end_date')==end and prior.get('model_provider')==provider:
                    if state.get('status') in {'created','running','completed'} and not payload.get('force_new'):
                        return self.get(path.parent.parent.name)
        package=SkillRegistry([self.skill_dir.parent]).get('auto-weekly-report');self._verify_integrity(package)
        run_id='weekly-'+datetime.now(TZ).strftime('%Y%m%d-%H%M%S')+'-'+uuid4().hex[:8]
        ctx=SkillRunContext(package,self.root,run_id)
        snapshot=ctx.working_dir/'skill-package'/package.skill_id
        shutil.copytree(package.root,snapshot,ignore=shutil.ignore_patterns('__pycache__','*.pyc','~$*'))
        package=SkillRegistry([snapshot.parent]).get(package.skill_id)
        if package.package_hash!=ctx.load_state()['package_hash']:raise ValueError('建立任务时技能包已变化，请重试。')
        request=dict(start_date=start,end_date=end,model_provider=provider,question=str(payload.get('question',''))[:6000])
        write(ctx.inputs_dir/'request.json',request)
        with self.lock:
            self.data_dir.mkdir(parents=True,exist_ok=True)
            ledger=self.data_dir/'coverage_log.md'
            if not ledger.exists():shutil.copy2(package.resolve('references/coverage_log.md'),ledger)
            shutil.copy2(ledger,ctx.inputs_dir/'coverage_log.md')
        write(ctx.working_dir/'package-manifest.json',dict(package_hash=package.package_hash,resources=package.resources(),
            tools={'research':['skill_package_inspect','skill_read_resource','weekly_search','weekly_fetch','weekly_series_lookup','weekly_submit_section'],
                   'production':['skill_run_script','weekly_content_validate','weekly_artifact_validate','coverage_commit']}))
        self._reuse_verified_evidence(ctx,request,package)
        rows=read(package.resolve('references/sections.json'))
        titles=[('package','装载完整技能包与历史台账')]+[(r['id'],r['section']+(' · '+r['subsection'] if r['subsection'] else '')) for r in rows]+[('content','摘要与全篇事实核验'),('render','生成阅读版、正报和来源文档'),('validate','三件套独立验收'),('archive','保存任务与更新去重台账')]
        ctx.set_plan([dict(id=k,title=t,depends_on=[] if i==0 else [titles[i-1][0]],success_criteria=t+'并留存证据') for i,(k,t) in enumerate(titles)])
        state=ctx.load_state();state.update(status='created',message=f'周报日期：{start} 至 {end}；任务已建立。',stage='package',report_period=[start,end],counts={},recoverable=True);ctx.save_state(state)
        write(self.root/'latest.json',dict(run_id=run_id));self._launch(run_id);return self.get(run_id)

    def _reuse_verified_evidence(self,ctx,request,package):
        """Reuse same-period public source bytes, revalidating sections with current rules."""
        rules=validator(package)
        coverage=rules.coverage_for_period((ctx.inputs_dir/'coverage_log.md').read_text(encoding='utf-8'),request['start_date'],request['end_date'])
        for previous in sorted(self.root.glob('weekly-*/inputs/request.json'),reverse=True):
            old_root=previous.parent.parent
            if old_root==ctx.root:continue
            prior=read(previous);old_state=read(old_root/'run-state.json')
            if any(prior.get(k)!=request.get(k) for k in ('start_date','end_date','model_provider')):continue
            if old_state.get('status') not in {'cancelled','failed','needs_review','completed'}:continue
            old_sources=old_root/'working/sources.json'
            if not old_sources.exists():continue
            sources=read(old_sources)
            if rules.validate_source_files(sources,old_root):continue
            for folder in ('source-text','search'):
                origin=old_root/'working'/folder
                if origin.is_dir():shutil.copytree(origin,ctx.working_dir/folder,dirs_exist_ok=True)
            write(ctx.working_dir/'sources.json',sources)
            reused=[]
            for spec in read(package.resolve('references/sections.json')):
                origin=old_root/'working'/('section-'+spec['id']+'.json')
                if not origin.exists():origin=old_root/'working'/('section-partial-'+spec['id']+'.json')
                section=read(origin) if origin.exists() else dict(items=[])
                candidates=list(section.get('items',[]))
                draft_json=old_root/'working'/('draft-'+spec['id']+'.json')
                if draft_json.exists():candidates.extend(read(draft_json).get('items',[]))
                from utils.text import strip_thinking
                from utils.weekly_report_research import original_event_excerpt,extract_weekly_output
                for draft in sorted((old_root/'working').glob('model-'+spec['id']+'-attempt-*.txt')):
                    try:candidates.extend(extract_weekly_output(strip_thinking(draft.read_text(encoding='utf-8'))).get('items',[]))
                    except (ValueError,TypeError):continue
                for item in candidates:
                    source=sources.get(str(item.get('source_id',''))) or {}
                    if not source.get('fetched'):continue
                    item['source']=source['url']
                    if spec.get('preserve_title'):item['title']=source['title']
                    try:item['date']=date.fromisoformat(str(item.get('event_date',''))).strftime('%m.%d')
                    except ValueError:continue
                    issues=rules.validate_item(item,spec,sources,request['start_date'],request['end_date'],coverage)
                    if any(error in issues for error in ('事件证据不是来源正文逐字摘录','事件日仅来自文章时间或预告，未锚定实际发生动作','原文证据不能确认事件日与年度','事件日期证据缺少已发生的动作')):
                        excerpt=original_event_excerpt(source,item.get('event_date',''),rules)
                        if excerpt:item['event_quote']=excerpt
                valid=[item for item in candidates if not rules.validate_item(item,spec,sources,request['start_date'],request['end_date'],coverage)]
                unique=[]
                for item in valid:
                    if not any(old.get('event_key')==item.get('event_key') or old.get('source')==item.get('source') for old in unique):unique.append(item)
                valid=unique[:spec['target_max']]
                if candidates:write(ctx.working_dir/('candidate-'+spec['id']+'.json'),dict(items=candidates))
                if valid:
                    section=dict(section=spec['section'],subsection=spec['subsection'],items=valid)
                    write(ctx.working_dir/('section-'+spec['id']+'.json'),section);reused.append(spec['id'])
            ctx.checkpoint('复用同日期已保存原文，按当前规则重验已完成板块',dict(previous_run_id=old_root.name,source_records=len(sources),sections=reused))
            break

    def _launch(self,run_id):
        with self.lock:
            if run_id in self.active:return
            self.active.add(run_id);self.cancel_events[run_id]=Event()
        Thread(target=self._execute,args=(run_id,),daemon=True,name=run_id).start()

    def resume(self,run_id):
        root=self._run_path(run_id);state=read(root/'run-state.json')
        if state.get('status')=='completed':
            try:
                for kind in ('html','docx','sources'):self.download(run_id,kind)
                return self.get(run_id)
            except ValueError:pass
        self._package(root);self._launch(run_id);return self.get(run_id)

    def cancel(self,run_id):
        self._run_path(run_id)
        with self.lock:
            if run_id in self.active:self.cancel_events[run_id].set()
        return self.get(run_id)

    def recover_pending(self):
        for path in self.root.glob('weekly-*/run-state.json'):
            if read(path).get('status') in {'created','running'}:self._launch(path.parent.name)

    def _check_cancel(self,run_id):
        if self.cancel_events.get(run_id,Event()).is_set():raise Cancelled('任务已取消，来源与已完成板块保留，可从检查点继续。')

    def _update(self,ctx,stage,status,message):
        ctx.update_task(stage,status,message)
        state=ctx.load_state();state.update(status='running',stage=stage,message=message);ctx.save_state(state)

    def _script(self,ctx,name,args):
        result=asyncio.run(SkillRunScriptTool(ctx).call('scripts/'+name,json.dumps(args,ensure_ascii=False),180))
        text='\n'.join(str(b.text if hasattr(b,'text') else b.get('text','')) for b in result.content)
        path=ctx.working_dir/(name+'.log');path.write_text(text,encoding='utf-8')
        value=json.loads(text)
        if value.get('returncode',value.get('exit_code',0))!=0:raise ValueError(name+'执行失败：'+str(value.get('stderr') or value.get('stdout') or '详细原因已保存。')[-1800:])
        return value

    def _execute(self,run_id):
        execution=ExecutionLock(self._run_path(run_id)/'.execution.lock')
        try:
            if not execution.acquire():return
            self._execute_owned(run_id)
        finally:
            execution.close()
            with self.lock:self.active.discard(run_id)

    def _execute_owned(self,run_id):
        ctx=None;stage='package'
        try:
            root=self._run_path(run_id);package=self._package(root);ctx=SkillRunContext(package,self.root,run_id)
            state=ctx.load_state();state.update(status='running',error='',recoverable=True);ctx.save_state(state)
            request=read(ctx.inputs_dir/'request.json');start,end=request['start_date'],request['end_date']
            rules=validator(package);specs=read(package.resolve('references/sections.json'))
            coverage=rules.coverage_for_period((ctx.inputs_dir/'coverage_log.md').read_text(encoding='utf-8'),request['start_date'],request['end_date'])
            completed={t['id'] for t in state['plan'] if t['status']=='completed'}
            if stage not in completed:
                self._update(ctx,stage,'running','已锁定完整周报技能包，核对依赖、十四板块及历史台账。')
                for rel in ('references/runtime-contract.md','references/search_prompts.md','references/report_rules.md'):
                    package.resolve(rel).read_text(encoding='utf-8')
                    ctx.checkpoint('读取技能操作知识',dict(resource=rel,sha256=digest(package.resolve(rel))))
                self._update(ctx,stage,'completed','完整知识、模板、脚本、来源工具和验收能力已挂载。')
            sections=[];gaps=[]
            for spec in specs:
                self._check_cancel(run_id);stage=spec['id'];path=ctx.working_dir/('section-'+stage+'.json')
                source_path=ctx.working_dir/'sources.json';sources=read(source_path) if source_path.exists() else {}
                existing=read(path) if path.exists() else None
                if existing and all(not rules.validate_item(i,spec,sources,start,end,coverage) for i in existing.get('items',[])) and existing.get('items') and not rules.section_issues(spec,existing['items']):
                    section=existing
                else:
                    self._update(ctx,stage,'running',f'日期 {start} 至 {end}；正在检索并核验 {spec["section"]} {spec["subsection"]}。')
                    write(ctx.working_dir/'selected-stories.json',[item for block in sections for item in block['items']])
                    section=self.section_runner(ctx,spec,request,coverage,lambda:self._check_cancel(run_id))
                    write(path,section)
                    sources=read(source_path) if source_path.exists() else {}
                accepted=[];rejected=[];gap_reason=str(section.get('gap',''))
                for item in section.get('items',[]):
                    errors=rules.validate_item(item,spec,sources,start,end,coverage)
                    if errors:rejected.append(dict(title=item.get('title',''),errors=errors))
                    elif any(rules.same_story(item,old) for block in sections for old in block['items']):
                        rejected.append(dict(title=item.get('title',''),errors=['本期前序板块已收录同一来源或事件']))
                    else:accepted.append(item)
                section=dict(section=spec['section'],subsection=spec['subsection'],items=accepted,gap=gap_reason)
                write(path,section);write(ctx.working_dir/('diagnostics-'+stage+'.json'),dict(accepted=len(accepted),rejected=rejected))
                sections.append(section)
                quality=rules.section_issues(spec,accepted)
                if accepted and not quality:
                    self._update(ctx,stage,'completed',f'已验收 {len(accepted)} 条资讯；来源与事件日证据已保存。')
                else:
                    reason='；'.join(quality) if quality else '；'.join(rejected[0]['errors']) if rejected else gap_reason or '检索未取得符合日期、来源与去重规则的事实'
                    gaps.append(spec['section']+' / '+(spec['subsection'] or '正文')+'：'+reason)
                    self._update(ctx,stage,'blocked','未找到通过事件日、来源与去重核验的资讯；保留已取得证据。')
            stage='content'
            evidence_errors=rules.validate_source_files(read(ctx.working_dir/'sources.json'),ctx.root)
            if evidence_errors:raise ValueError('；'.join(evidence_errors))
            if gaps:raise ValueError('以下板块尚无可用事实，不能交付正式报告：'+'；'.join(gaps))
            self._check_cancel(run_id);stage='content';self._update(ctx,stage,'running','从已验收正文复制摘要，检查跨板块重复与全部事实。')
            summary_pool=[]
            for name in ('宏观动态','政策法规','企业要闻','新车上市'):
                grouped=[b for b in sections if b['section']==name]
                # One from each enterprise group first, then select a second.
                for index in range(max((len(block['items']) for block in grouped),default=0)):
                    for block in grouped:
                        if len(block['items'])>index:summary_pool.append(block['items'][index])
            lower,upper=(12,13) if (date.fromisoformat(end)-date.fromisoformat(start)).days>6 else (9,10)
            summary=[]
            for block in sections:
                if block['section'] in {'宏观动态','政策法规','企业要闻','新车上市'} and block['items']:
                    summary.append(block['items'][0])
            for item in summary_pool:
                if len(summary)>=upper:break
                if not any(chosen['event_key']==item['event_key'] for chosen in summary):summary.append(item)

            ranking={'宏观动态':0,'政策法规':1,'企业要闻':2,'新车上市':3}
            summary.sort(key=lambda i:next(ranking[b['section']] for b in sections if i in b['items']))
            data=dict(period_start=start,period_end=end,run_id=run_id,summary=summary,body_sections=sections,
                      toc=[b['section']+(' / '+b['subsection'] if b['subsection'] else '')+'\t' for b in sections],
                      visual=build_visual(sections,start,end))
            write(ctx.working_dir/'report_data.json',data)
            sources=read(ctx.working_dir/'sources.json')
            check=rules.validate_content(data,sources,coverage,start,end);write(ctx.working_dir/'content-validation.json',check)
            if not check['passed']:raise ValueError('全篇事实门禁未通过：'+'；'.join(check['errors'][:12]))
            self._update(ctx,stage,'completed',f'九章十四板块、{check["items"]}条资讯及{len(summary)}条摘要已通过事实门禁。')
            self._check_cancel(run_id);stage='render';self._update(ctx,stage,'running','正在执行技能包内三份生成程序，克隆模板并生成三件套。')
            dates=date.fromisoformat(start).strftime('%m.%d')+'-'+date.fromisoformat(end).strftime('%m.%d')
            period=start[:4]+'.'+start[5:].replace('-','')+'-'+(end[:4]+'.' if end[:4]!=start[:4] else '')+end[5:].replace('-','')
            base='中国汽车产业周度资讯快报'+period
            outputs={'html':ctx.outputs_dir/(base+'.html'),'docx':ctx.outputs_dir/(base+'.docx'),'sources':ctx.outputs_dir/(base+'_来源.docx')}
            data_path=str(ctx.working_dir/'report_data.json')
            prior_release=ctx.working_dir/'release-validation.json'
            valid_existing=False
            if prior_release.exists():
                prior=read(prior_release)
                valid_existing=bool(prior.get('passed') and all(p.is_file() and any(r['kind']==kind and digest(p)==r['sha256'] for r in prior['artifacts']['artifacts']) for kind,p in outputs.items()))
            if not valid_existing:
                self._script(ctx,'gen_report.py',['--template',str(package.resolve('assets/weekly-template.docx')),'--output',str(outputs['docx']),'--data',data_path,'--date-old','09.26-10.10','--date-new',dates,'--start-date',start,'--end-date',end])
                self._script(ctx,'gen_visual_html.py',['--data',data_path,'--output',str(outputs['html']),'--date-new',dates,'--report-date',datetime.now(TZ).strftime('%Y.%m.%d')])
                self._script(ctx,'gen_sources.py',['--data',data_path,'--output',str(outputs['sources']),'--date-new',dates])
            else:
                ctx.checkpoint('复用本轮已验收三件套，跳过重复生成',dict(run_id=run_id))
            if self.office_validation and not valid_existing:
                for kind in ('docx','sources'):
                    args=['-InputPath',str(outputs[kind]),'-OutputDir',str(ctx.working_dir/'word-render')]
                    if kind=='docx':args.append('-UpdateToc')
                    result=self._script(ctx,'render_word.ps1',args)
                    try:office=json.loads(result.get('stdout','').strip().lstrip('\ufeff'))
                    except ValueError:raise ValueError('Word实机验收未返回有效结果。')
                    write(ctx.working_dir/('word-validation-'+kind+'.json'),office)
                    if office.get('available') and not office.get('success'):raise ValueError('Word无法正常打开并渲染本轮文件。')
                    ctx.checkpoint('Word打开与目录验收' if office.get('available') else 'Word环境不可用，采用结构与内容验收',dict(kind=kind,**office))
                    if not office.get('available'):break
            for kind,path in outputs.items():ctx.register_artifact(path,kind)
            self._update(ctx,stage,'completed','HTML阅读版、Word正报、逐条来源文档已生成。')
            self._check_cancel(run_id);stage='validate';self._update(ctx,stage,'running','独立检查三份文件、模板结构、内容一致及来源完整性。')
            report=ctx.working_dir/'release-validation.json'
            self._script(ctx,'validate_weekly.py',['--data',data_path,'--sources',str(ctx.working_dir/'sources.json'),'--coverage',str(ctx.inputs_dir/'coverage_log.md'),'--start-date',start,'--end-date',end,'--artifacts',str(ctx.outputs_dir),'--template',str(package.resolve('assets/weekly-template.docx')),'--report',str(report)])
            release=read(report)
            if not release['passed']:raise ValueError('三件套独立验收未通过。')
            for kind,path in outputs.items():
                ctx.record_artifact_validation(path,'weekly_content',True,check)
                ctx.record_artifact_validation(path,'weekly_artifacts',True,release['artifacts'])
            self._update(ctx,stage,'completed','三件套独立验收通过，内容与事件证据一致。')
            stage='archive';self._update(ctx,stage,'running','保存可回放执行记录，按事件更新跨周去重台账。')
            artifact_rows=self._artifact_rows(run_id,release)
            with self.lock:
                live_path=self.data_dir/'coverage_log.md';live=live_path.read_text(encoding='utf-8');ledger=rules.coverage_entries(live)
                if ('<!-- run:'+run_id+' -->') not in live:
                    additions=[]
                    for block in sections:
                        for item in block['items']:
                            if not rules.duplicate(item,ledger):
                                title=item['title'].replace('|','／');label=block['section']+('（'+block['subsection']+'）' if block['subsection'] else '')
                                additions.append(f'| {period} | {label} | {title} | {item["date"]} | {item["source"]} |')
                    temp=live_path.with_suffix('.tmp');temp.write_text(live+'\n<!-- run:'+run_id+' -->\n'+'\n'.join(additions)+'\n',encoding='utf-8');temp.replace(live_path)
            self._update(ctx,stage,'completed','三件套与执行记录已归档，跨周台账已更新。')
            outcome=ctx.validate([str(p.relative_to(ctx.root)).replace('\\','/') for p in outputs.values()])
            if not outcome.get('passed',outcome.get('status')=='passed'):raise ValueError('任务图或产物总验收未通过。')
            state=ctx.load_state();state.update(message=f'{start} 至 {end} 周报已完成：{check["items"]}条资讯，三件套验收通过。',recoverable=False,items=check['items'],summary_items=len(summary));ctx.save_state(state)
            if self.on_complete:
                project_id=self.on_complete(dict(run_id=run_id,status='completed',report_period=[start,end],items=check['items'],artifacts=artifact_rows,package_hash=package.package_hash,state=ctx.load_state()),request)
                current=ctx.load_state();current['project_id']=project_id;ctx.save_state(current)
        except Exception as exc:
            if ctx:
                detail=str(exc) or (f'{stage}板块执行超时，已保留原文和检查点。' if isinstance(exc,TimeoutError) else type(exc).__name__)
                if stage in {task['id'] for task in ctx.load_state().get('plan',[])}:self._update(ctx,stage,'blocked',detail)
                state=ctx.load_state();state.update(status='cancelled' if isinstance(exc,Cancelled) else 'needs_review' if isinstance(exc,ValueError) else 'failed',error=detail,message=detail,recoverable=True,stage=stage);ctx.save_state(state)
                ctx.checkpoint('任务停止，已有证据与检查点保留',dict(stage=stage,error=detail))
        finally:
            with self.lock:self.active.discard(run_id)

    @staticmethod
    def _artifact_rows(run_id,release):
        labels={'html':'HTML阅读版','docx':'Word正报','sources':'逐条来源文档'}
        return [dict(kind=r['kind'],label=labels[r['kind']],filename=r['file'],sha256=r['sha256'],bytes=r['bytes'],url='/api/weekly-report/download?run_id='+run_id+'&artifact='+r['kind']) for r in release['artifacts']['artifacts']]

    def get(self,run_id=''):
        if not run_id:
            latest=self.root/'latest.json'
            if not latest.exists():return dict(available=False)
            run_id=read(latest)['run_id']
        root=self._run_path(run_id);state=read(root/'run-state.json');request=read(root/'inputs/request.json')
        plan=state.get('plan',[]);count=sum(t.get('status')=='completed' for t in plan)
        artifacts=[];release=root/'working/release-validation.json'
        if state.get('status')=='completed' and release.exists() and read(release).get('passed'):
            artifacts=self._artifact_rows(run_id,read(release))
        journal=root/'checkpoints.jsonl';events=[]
        if journal.exists():
            for line in journal.read_text(encoding='utf-8').splitlines()[-100:]:events.append(json.loads(line))
        return dict(available=True,run_id=run_id,status=state.get('status'),message=state.get('message',''),error=state.get('error',''),stage=state.get('stage'),steps=plan,events=events,progress=round(count/max(1,len(plan))*100),report_period=[request['start_date'],request['end_date']],items=state.get('items',0),summary_items=state.get('summary_items',0),artifacts=artifacts,package_hash=state['package_hash'],validation=state.get('validation'),recoverable=state.get('recoverable',True),project_id=state.get('project_id'))

    def download(self,run_id,kind):
        root=self._run_path(run_id);job=self.get(run_id)
        if job['status']!='completed' or not job['artifacts']:raise ValueError('本轮三件套尚未通过验收，暂不可下载。')
        row=next((r for r in job['artifacts'] if r['kind']==kind),None)
        if not row:raise ValueError('该交付物不存在。')
        path=(root/'outputs'/row['filename']).resolve();path.relative_to((root/'outputs').resolve())
        if not path.is_file() or digest(path)!=row['sha256']:raise ValueError('交付物与本轮验收指纹不一致，已停止下载。')
        return path
