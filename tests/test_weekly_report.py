from __future__ import annotations
from pathlib import Path
from copy import deepcopy
from tempfile import TemporaryDirectory
from unittest.mock import patch
from threading import Event
import unittest,json,hashlib,shutil
from datetime import date,timedelta
from skill_runtime import SkillRegistry
from utils.weekly_report_jobs import WeeklyReportJobs,read,write,validator
ROOT=Path(__file__).resolve().parents[1]
SKILL=ROOT/'skills/auto-weekly-report'

def seal(root):
    for filename in ('weekly_report_jobs.py','weekly_report_research.py'):
        shutil.copy2(ROOT/'utils'/filename,root/'scripts/web_runtime'/filename)
    values={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='package-integrity.json' and p.suffix not in {'.pyc','.pyo'}}
    write(root/'package-integrity.json',values)

# Deliberately synthetic evidence is confined to test temporary workspaces.
# Real script execution and template cloning are exercised, not claimed as research.
def fixture(ctx, spec, request, coverage, check_cancel):
    all_sources=read(ctx.working_dir/'sources.json') if (ctx.working_dir/'sources.json').exists() else {}
    items=[]
    for index in range(3 if spec['id']=='joint' else 2):
        title=spec['section']+spec['subsection']+f'离线测试事项{index+1}'
        event=date.fromisoformat(request['start_date'])+timedelta(days=3)
        quote=f'{event.year}年{event.month}月{event.day}日，测试企业正式发布本土产品技术方案，明确了技术参数和量产投产安排。'
        body=quote+'该方案由企业在中国正式推出，包含具体产品应用范围、实施节点与合作主体，公开内容已由本次测试来源逐项记录。'
        source_id='test-'+spec['id']+str(index);url='https://example.com/'+source_id
        item=dict(title=title,body=body,source_id=source_id,source=url,event_date=event.isoformat(),date=event.strftime('%m.%d'),event_quote=quote,event_key=source_id,status='occurred',scope='china',company='测试主体'+str(index))
        text=title+'\n'+body
        path=ctx.working_dir/'source-text'/(source_id+'.txt');path.parent.mkdir(exist_ok=True);path.write_text(text,encoding='utf-8',newline='\n')
        all_sources[source_id]=dict(id=source_id,url=url,title=title,text=text,fetched=True,published=event.isoformat(),text_path=path.relative_to(ctx.root).as_posix(),text_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        if spec['id']=='newcar':
            proof_id=source_id+'-series';proof_text=f'{title}测试全新车系于{event.year}年{event.month}月{event.day}日正式上市，该车系首次建立，无历史车型记录。'
            proof_path=ctx.working_dir/'source-text'/(proof_id+'.txt');proof_path.write_text(proof_text,encoding='utf-8',newline='\n')
            all_sources[proof_id]=dict(id=proof_id,url='https://www.autohome.com.cn/'+proof_id,title=title+'测试车系记录',text=proof_text,fetched=True,published=event.isoformat(),text_path=proof_path.relative_to(ctx.root).as_posix(),text_sha256=hashlib.sha256(proof_path.read_bytes()).hexdigest())
            item['series_history']=dict(series_name=title,source_id=proof_id,quote=proof_text,is_new_series=True)
        items.append(item)
    write(ctx.working_dir/'sources.json',all_sources)
    return dict(section=spec['section'],subsection=spec['subsection'],items=items)

class WeeklyPackageTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.skill=self.root/'skills/auto-weekly-report';shutil.copytree(SKILL,self.skill,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        seal(self.skill)
        self.manager=WeeklyReportJobs(self.root,self.skill,lambda provider:{},fixture,office_validation=False)
    def start(self):
        with patch.object(self.manager,'_launch'):
            return self.manager.start(dict(start_date='2025-09-06',end_date='2025-09-12',model_provider='test'))
    def test_cancelled_same_period_reuses_verified_sources_and_completed_section(self):
        from skill_runtime import SkillRunContext
        job=self.start();root=self.manager._run_path(job['run_id']);package=self.manager._package(root)
        ctx=SkillRunContext(package,self.manager.root,job['run_id'])
        spec=read(package.resolve('references/sections.json'))[0];request=read(ctx.inputs_dir/'request.json')
        section=fixture(ctx,spec,request,[],lambda:None)
        write(ctx.working_dir/'section-policy.json',section)
        state=ctx.load_state();state['status']='cancelled';ctx.save_state(state)
        with patch.object(self.manager,'_launch'):
            next_job=self.manager.start(request)
        self.assertNotEqual(next_job['run_id'],job['run_id'])
        new_root=self.manager._run_path(next_job['run_id'])
        self.assertEqual(read(new_root/'working/section-policy.json'),section)
        self.assertEqual(read(new_root/'working/sources.json'),read(root/'working/sources.json'))
        self.assertFalse(validator(package).validate_source_files(read(new_root/'working/sources.json'),new_root))

    def test_article_timestamp_is_not_an_event_date_and_literal_signoff_is_supported(self):
        rules=validator(SkillRegistry([self.skill.parent]).get('auto-weekly-report'))
        source={'published':'2025-04-21','text':'2025-04-21\n中共中央、国务院近日印发意见，支持道路测试。'}
        self.assertFalse(rules.occurrence_supported('2025-04-21',source['text'],source))
        signed='现将汽车置换更新实施细则印发给你们，请认真按照执行。\n上海市商务委员会\n2025 年 4 月 23 日'
        self.assertTrue(rules.occurrence_supported('2025-04-23',signed,{'text':signed}))
        self.assertFalse(rules.occurrence_supported('2025-04-29','2025-04-29\n南京将于5月1日启动补贴。',{'text':'2025年'}))

    def test_two_workers_cannot_execute_the_same_run(self):
        from utils.weekly_report_jobs import ExecutionLock
        job=self.start();root=self.manager._run_path(job['run_id'])
        held=ExecutionLock(root/'.execution.lock');self.assertTrue(held.acquire())
        try:
            with patch.object(self.manager,'_execute_owned') as execute:
                self.manager._execute(job['run_id']);execute.assert_not_called()
        finally:held.close()
        with patch.object(self.manager,'_execute_owned') as execute:
            self.manager._execute(job['run_id']);execute.assert_called_once()

    def test_empty_tool_submission_is_authoritative_and_keeps_gap(self):
        import asyncio
        from agentscope.message import UserMsg
        from utils.weekly_report_research import run_section,WeeklySubmitTool
        from skill_runtime import SkillRunContext
        job=self.start();ctx=SkillRunContext(self.manager._package(self.manager._run_path(job['run_id'])),self.manager.root,job['run_id'])
        spec=read(ctx.package.resolve('references/sections.json'))[1];request=read(ctx.inputs_dir/'request.json')
        class EmptyAgent:
            def __init__(self,**kwargs):pass
            async def reply(self,*args):
                # Exercise real submission tool: final prose is intentionally not JSON.
                await submit[0].call([],gap='已检索本期官方来源，尚无可核验的本期事实。')
                return UserMsg(name='agent',content='已提交空结果及原因。')
        submit=[]
        original=WeeklySubmitTool.__init__
        def capture(tool,store):original(tool,store);submit.append(tool)
        with patch('utils.weekly_report_research.EvidenceStore.search',return_value={'results':[{'url':'https://example.com'}]}),patch('utils.weekly_report_research.Agent',EmptyAgent),patch('utils.weekly_report_research.build_model'),patch.object(WeeklySubmitTool,'__init__',capture):
            result=run_section(ctx,spec,request,[],lambda:None,{})
        self.assertEqual(result['items'],[])
        self.assertIn('已检索本期官方来源',result['gap'])
        self.assertNotIn('JSON',result['gap'])
        self.assertTrue((ctx.working_dir/'submission-macro-001.json').exists())
        self.assertFalse((ctx.working_dir/'model-check-macro-attempt-2.json').exists())

    def test_resume_executor_upgrade_creates_replacement_without_mutating_snapshot(self):
        job=self.start();root=self.manager._run_path(job['run_id']);original=(root/'working/skill-package/auto-weekly-report/SKILL.md').read_bytes()
        state=read(root/'run-state.json');state['status']='cancelled';write(root/'run-state.json',state)
        with patch.object(self.manager,'_package',side_effect=ValueError('执行器版本与本轮锁定版本不一致；已保留原任务与全部证据。')),patch.object(self.manager,'_launch'):
            replacement=self.manager.resume(job['run_id'])
        self.assertNotEqual(replacement['run_id'],job['run_id'])
        new=read(self.manager._run_path(replacement['run_id'])/'run-state.json')
        self.assertEqual(new['supersedes_run_id'],job['run_id'])
        self.assertEqual((root/'working/skill-package/auto-weekly-report/SKILL.md').read_bytes(),original)

    def test_fetched_literal_macro_event_is_exposed_without_using_article_timestamp(self):
        from utils.weekly_report_research import event_excerpts
        rules=validator(SkillRegistry([self.skill.parent]).get('auto-weekly-report'))
        source={'published':'2026-10-09','title':'汇率政策立场','text':'发布日期：2026年10月9日\n10月8日，中国人民银行对外发布政策立场，明确中国没有必要，也无意通过汇率贬值获取贸易竞争优势。'}
        result=event_excerpts(source,{'start_date':'2026-10-03','end_date':'2026-10-09'},rules)
        self.assertEqual([r['event_date'] for r in result],['2026-10-08'])
        self.assertIn(result[0]['event_quote'],source['text'])

    def test_model_prose_and_scaffolding_do_not_replace_the_final_json(self):
        from utils.weekly_report_research import extract_weekly_output
        text='I will build JSON. {"items":[{"title":"example"}]}\nFinal result: {"items":[{"title":"actual","event_date":"2025-04-23"}]}'
        self.assertEqual(extract_weekly_output(text)['items'][0]['title'],'actual')
        with self.assertRaises(ValueError):extract_weekly_output('{"items":[{"title":"unfinished", ...}]}')

    def test_structured_submit_keeps_verified_items_and_reports_numeric_error(self):
        import asyncio
        from types import SimpleNamespace
        from skill_runtime import SkillRunContext
        from utils.weekly_report_research import WeeklySubmitTool
        job=self.start();root=self.manager._run_path(job['run_id']);package=self.manager._package(root)
        ctx=SkillRunContext(package,self.manager.root,job['run_id']);spec=read(package.resolve('references/sections.json'))[0];request=read(ctx.inputs_dir/'request.json')
        section=fixture(ctx,spec,request,[],lambda:None);items=deepcopy(section['items']);items[1]['body']+=' 未经来源支持的金额999999元。'
        store=SimpleNamespace(ctx=ctx,spec=spec,request=request,sources=read(ctx.working_dir/'sources.json'),check_cancel=lambda:None,submission={'items':[],'gap':''},stagnant_submissions=0,submission_count=0,rejections=[])
        reply=asyncio.run(WeeklySubmitTool(store).call(items=items))
        self.assertEqual(len(store.submission['items']),1)
        self.assertEqual(read(ctx.working_dir/'section-partial-policy.json')['items'],store.submission['items'])
        self.assertIn('999999',str(reply))

    def test_series_identity_does_not_guess_related_names(self):
        from utils.weekly_report_research import exact_series_matches
        candidates=[dict(key='阿维塔06',wordid=7752,wordtype=3),dict(key='阿维塔06T',wordid=8538,wordtype=3)]
        self.assertEqual(exact_series_matches(candidates,'阿维塔 06')[0]['wordid'],7752)
        self.assertFalse(exact_series_matches([dict(key='吉利几何E萤火虫',wordid=6639,wordtype=3)],'萤火虫'))
        self.assertFalse(exact_series_matches([dict(key='Model Y L',wordid=1,wordtype=3)],'Model Y'))

    def test_same_signing_story_across_brand_aliases_is_not_reported_twice(self):
        rules=validator(SkillRegistry([self.skill.parent]).get('auto-weekly-report'))
        left=dict(source='https://example.com/a',event_key='a',event_date='2025-04-22',company='丰田雷克萨斯',body='4月22日，丰田参与签约，测试雷克萨斯（上海）新能源有限公司项目落地。')
        right=dict(source='https://example.com/b',event_key='b',event_date='2025-04-22',company='丰田汽车',body='4月22日，丰田签署协议，测试雷克萨斯（上海）新能源有限公司正式落地。')
        self.assertTrue(rules.same_story(left,right))
        right['company']='本田中国';self.assertFalse(rules.same_story(left,right))
        right['company']='丰田汽车';right['event_date']='2025-04-23';self.assertFalse(rules.same_story(left,right))
        self.assertTrue(rules.section_issues({'id':'joint'},[{'company':'丰田'},{'company':'本田'}]))

    def test_same_period_completed_facts_regenerate_layout_without_research(self):
        job=self.start();run=job['run_id'];self.manager.cancel_events[run]=Event();self.manager._execute(run)
        self.assertEqual(self.manager.get(run)['status'],'completed')
        request=read(self.manager._run_path(run)/'inputs/request.json');request['force_new']=True
        with patch.object(self.manager,'_launch'):next_job=self.manager.start(request)
        self.manager.cancel_events[next_job['run_id']]=Event()
        def no_research(*args):raise AssertionError('Completed facts must not be researched again')
        self.manager.section_runner=no_research;self.manager._execute(next_job['run_id'])
        self.assertEqual(self.manager.get(next_job['run_id'])['status'],'completed',self.manager.get(next_job['run_id'])['error'])

    def test_full_package_manifest_has_original_docs_scripts_template_and_integrity(self):
        status=self.manager.status();self.assertTrue(status['available']);self.assertGreaterEqual(status['resources'],18)
        package=SkillRegistry([self.skill.parent]).get('auto-weekly-report')
        for path in ('assets/周报提示词.docx','references/周报提示词-原文.md','references/original-SKILL.md','assets/weekly-template.docx','scripts/gen_report.py','scripts/gen_visual_html.py','scripts/gen_sources.py','scripts/validate_weekly.py'):self.assertTrue(package.resolve(path).is_file())
        (self.skill/'references/runtime-contract.md').write_text('changed',encoding='utf-8')
        self.assertFalse(self.manager.status()['available'])
    def test_real_script_execution_produces_verified_three_artifacts_and_reuses_same_run(self):
        job=self.start();run=job['run_id'];self.manager.cancel_events[run]=Event();self.manager._execute(run)
        final=self.manager.get(run);self.assertEqual(final['status'],'completed',final['error'])
        self.assertEqual([a['kind'] for a in final['artifacts']],['html','docx','sources']);self.assertEqual(final['items'],29)
        self.assertEqual(final['validation']['status'],'passed');self.assertEqual(final['summary_items'],10)
        paths=[self.manager.download(run,kind) for kind in ('html','docx','sources')]
        times=[p.stat().st_mtime_ns for p in paths]
        self.assertEqual(self.start()['run_id'],run)
        self.assertEqual(self.manager.resume(run)['run_id'],run)
        self.assertEqual([p.stat().st_mtime_ns for p in paths],times)
        original_hash=hashlib.sha256((self.skill/'references/coverage_log.md').read_bytes()).hexdigest()
        baseline=read(self.skill/'package-integrity.json')['references/coverage_log.md'];self.assertEqual(original_hash,baseline)
        self.assertIn('<!-- run:'+run+' -->',(self.root/'data/weekly-report/coverage_log.md').read_text(encoding='utf-8'))
        paths[0].write_text('modified',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'指纹'):self.manager.download(run,'html')
    def test_restart_resume_keeps_completed_section_and_exact_package(self):
        calls=[]
        def interrupted(ctx,spec,*args):
            calls.append(spec['id'])
            if spec['id']=='macro':raise RuntimeError('test interruption')
            return fixture(ctx,spec,*args)
        self.manager.section_runner=interrupted;job=self.start();run=job['run_id'];self.manager._execute(run)
        self.assertEqual(self.manager.get(run)['status'],'failed');self.assertEqual(calls,['policy','macro'])
        calls.clear()
        def continued(ctx,spec,*args):calls.append(spec['id']);return fixture(ctx,spec,*args)
        manager=WeeklyReportJobs(self.root,self.skill,lambda provider:{},continued,office_validation=False)
        with patch.object(manager,'_launch'):manager.resume(run)
        manager._execute(run);self.assertEqual(manager.get(run)['status'],'completed',manager.get(run)['error']);self.assertNotIn('policy',calls)
    def test_missing_source_blocks_output_with_precise_errors(self):
        def bad(ctx,spec,*args):
            section=fixture(ctx,spec,*args);
            for item in section['items']:item['source_id']='never-fetched'
            return section
        self.manager.section_runner=bad;job=self.start();self.manager._execute(job['run_id'])
        final=self.manager.get(job['run_id']);self.assertEqual(final['status'],'needs_review');self.assertEqual(final['artifacts'],[])
        self.assertIn('实际抓取',final['error'])
    def test_date_quote_title_duplicate_and_new_series_checks(self):
        job=self.start();root=self.manager._run_path(job['run_id']);pkg=self.manager._package(root)
        from skill_runtime import SkillRunContext
        ctx=SkillRunContext(pkg,self.manager.root,job['run_id']);spec=read(pkg.resolve('references/sections.json'))[3]
        section=fixture(ctx,spec,dict(start_date='2025-09-06',end_date='2025-09-12'),[],lambda:None);item=section['items'][0];sources=read(ctx.working_dir/'sources.json');v=validator(pkg)
        self.assertEqual(v.validate_item(item,spec,sources,'2025-09-06','2025-09-12',[]),[])
        mutations=[('event_date','2025-08-09','窗口'),('body',item['body']+'新增参数987654321。','数字'),('title','任意重写标题','原标题'),('event_quote','2025年9月9日发生的编造合作事项。','逐字'),('status','planned','已发生')]
        for key,value,message in mutations:
            changed=deepcopy(item);changed[key]=value
            self.assertTrue(any(message in error for error in v.validate_item(changed,spec,sources,'2025-09-06','2025-09-12',[])))
        self.assertTrue(any('已报道' in e for e in v.validate_item(item,spec,sources,'2025-09-06','2025-09-12',[dict(title=item['title'],source=item['source'])])))
        sources[item['source_id']]['text']+='tampered'
        self.assertTrue(v.validate_source_files(sources,ctx.root))
    def test_cross_year_cover_and_source_dates_and_coverage_parse(self):
        with patch.object(self.manager,'_launch'):
            job=self.manager.start(dict(start_date='2025-12-27',end_date='2026-01-02',model_provider='test'))
        self.manager._execute(job['run_id']);result=self.manager.get(job['run_id'])
        self.assertEqual(result['status'],'completed',result['error'])
        from docx import Document
        document=Document(self.manager.download(job['run_id'],'docx'))
        cover=''.join(t.text or '' for t in document.element.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t'))
        self.assertEqual(cover.count('2025.12.27-2026.01.02'),2)
        self.assertNotIn('2026.010.',cover)
        rules=validator(self.manager._package(self.manager._run_path(job['run_id'])))
        entries=rules.coverage_entries((self.root/'data/weekly-report/coverage_log.md').read_text(encoding='utf-8'))
        self.assertTrue(any(item['period']=='2025.1227-2026.0102' for item in entries))

    def test_archive_retry_keeps_existing_three_files_and_completed_research(self):
        attempts=[]
        def archive(*args):
            attempts.append(True)
            if len(attempts)==1:raise RuntimeError('archive interruption')
            return 'test-project'
        self.manager.on_complete=archive;job=self.start();run=job['run_id'];self.manager._execute(run)
        self.assertEqual(self.manager.get(run)['status'],'failed')
        root=self.manager._run_path(run);times={p.name:p.stat().st_mtime_ns for p in (root/'outputs').iterdir()}
        self.manager.section_runner=lambda *args: (_ for _ in ()).throw(AssertionError('must not repeat research'))
        self.manager._execute(run);result=self.manager.get(run)
        self.assertEqual(result['status'],'completed',result['error'])
        self.assertEqual({p.name:p.stat().st_mtime_ns for p in (root/'outputs').iterdir()},times)
        self.assertEqual(result['project_id'],'test-project')

    def test_future_and_bad_dates_rejected_before_creating_tasks(self):
        for start,end in [('2099-01-01','2099-01-07'),('2025-09-12','2025-09-06')]:
            with self.assertRaises(ValueError):self.manager.start(dict(start_date=start,end_date=end))
        self.assertFalse(self.manager.root.exists())

    def test_authorized_historical_recompile_keeps_persistent_ledger(self):
        self.manager.data_dir.mkdir(parents=True,exist_ok=True)
        ledger=self.manager.data_dir/'coverage_log.md'
        text='| 2025.0906-0910 | 政策法规 | 窗口内已报 | 09.08 | https://example.com/inside |\n| 2025.0830-0905 | 政策法规 | 窗口外旧闻 | 09.01 | https://example.com/outside |\n'
        ledger.write_text(text,encoding='utf-8')
        with patch.object(self.manager,'_launch'):
            job=self.manager.start(dict(start_date='2025-09-06',end_date='2025-09-12',model_provider='test',historical_recompile=True))
        inputs=self.manager._run_path(job['run_id'])/'inputs'
        self.assertEqual(ledger.read_text(encoding='utf-8'),text)
        self.assertEqual((inputs/'coverage_log-before-recompile.md').read_text(encoding='utf-8'),text)
        self.assertNotIn('窗口内已报',(inputs/'coverage_log.md').read_text(encoding='utf-8'))
        self.assertIn('窗口外旧闻',(inputs/'coverage_log.md').read_text(encoding='utf-8'))

if __name__=='__main__':unittest.main()
