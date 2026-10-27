import json,hashlib,shutil,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
from utils.weekly_report_jobs import read,write,validator
from skill_runtime import SkillRegistry,SkillRunContext
run_id='weekly-20261014-101813-22d8a00c';run=root/'runtime/weekly-report'/run_id
state=read(run/'run-state.json');assert state['status'] in ['failed','needs_review','cancelled']
package=SkillRegistry([run/'working/skill-package']).get('auto-weekly-report');assert package.package_hash==state['package_hash']
ctx=SkillRunContext(package,root/'runtime/weekly-report',run_id);v=validator(package)
backup=root/'outputs/weekly-report-monitor/before-support';backup.mkdir(parents=True,exist_ok=True)
for name in ['sources.json','section-macro.json','section-luxury.json']:
 p=ctx.working_dir/name
 if p.exists():shutil.copy2(p,backup/name)
shutil.copy2(ctx.inputs_dir/'request.json',backup/'request.json')
sources=read(ctx.working_dir/'sources.json');rows=read(root/'outputs/weekly-report-monitor/support/supplemental-facts.json')
coverage=v.coverage_for_period((ctx.inputs_dir/'coverage_log.md').read_text(encoding='utf-8'),'2026-09-26','2026-10-02')
for row in rows:
 assert not row['issues'];source=row['source'];sid=source['id'];text_path=ctx.working_dir/'source-text'/(sid+'.txt');shutil.copy2(row['source_file'],text_path)
 assert hashlib.sha256(text_path.read_bytes()).hexdigest()==source['text_sha256']
 source['text_path']=text_path.relative_to(run).as_posix();sources[sid]=source
 spec=next(x for x in v.SECTION_ROWS if x['id']==row['section_id']);issues=v.validate_item(row['item'],spec,sources,'2026-09-26','2026-10-02',coverage);assert not issues,issues
 write(ctx.working_dir/('section-'+row['section_id']+'.json'),dict(section=spec['section'],subsection=spec['subsection'],items=[row['item']],gap=''))
 ctx.checkpoint('监控补源通过原事实验收',dict(section=row['section_id'],source_id=sid,url=source['url'],validation_errors=issues))
write(ctx.working_dir/'sources.json',sources)
request=read(ctx.inputs_dir/'request.json');request['model_provider']='bailian_token_plan';request['question']=(request.get('question','')+' 监控恢复：原MiniMax在合资板块返回422并停止；改用已配置百炼继续。用户要求今天上午形成下午汇报版本，优先检索最重要且可验证的境内既成事实，达到有效提交后及时结束板块；不要重复提交已经明确缺少日期证据的同一条目。宏观PMI及豪华品牌服务权益已补充原文并通过原验收器。已验收板块复用。')
write(ctx.inputs_dir/'request.json',request);ctx.checkpoint('模型故障恢复选项已记录',dict(previous_provider='minimax',provider='bailian_token_plan',reason='HTTP422 input new_sensitive 1026',preserved_package_hash=package.package_hash))
print('supplemented_macro_luxury_original_gates_passed; provider=bailian_token_plan')
