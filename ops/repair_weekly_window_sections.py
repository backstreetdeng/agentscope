import json,sys,importlib.util,re
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
from utils.config import load_json_config,expand_env
from utils.weekly_report_jobs import read,validator
from utils.weekly_report_research import event_excerpts,extract_weekly_output
from skill_runtime import SkillRegistry
import os
run=root/'runtime/weekly-report/weekly-20261014-101813-22d8a00c';pkg=SkillRegistry([run/'working/skill-package']).get('auto-weekly-report');v=validator(pkg);req=read(run/'inputs/request.json');sources=read(run/'working/sources.json');coverage=v.coverage_for_period((run/'inputs/coverage_log.md').read_text(encoding='utf-8'),req['start_date'],req['end_date'])
inputs=[]
for spec in v.SECTION_ROWS:
 if spec['id'] in ['policy','macro','industry','luxury','newcar']:continue
 path=run/'working'/('candidate-'+spec['id']+'.json')
 if not path.exists():continue
 records=[]
 for row in read(path)['items']:
  source=sources.get(row['source_id']);quotes=event_excerpts(source,req,v) if source else []
  if not source or not quotes:continue
  # Literal source around matching dates, including enough context to detect background/preview.
  records.append(dict(source_id=source['id'],url=source['url'],title=source['title'],text=source['text'][-9500:],verified_event_excerpts=quotes,historical_candidate=row))
 if records:inputs.append(dict(spec=spec,sources=records[:5]))
for filename in ['.env','.env.bailian']:load_dotenv(root/filename,override=True)
config=load_json_config();provider=config['providers']['bailian_token_plan'];client=OpenAI(api_key=os.environ[provider['api_key_env']],base_url=provider['base_url'],timeout=180)
instructions=(pkg.resolve('references/search_prompts.md').read_text(encoding='utf-8'))[:6500]
system='你协助修复已停止/待完成的周报板块草稿，只从实际读取的来源中编排，不联网，不生成文件。用户要2026年9月26日至10月2日这一周。已报过但发生在本窗口的事实可重编；本轮内部不重复。'+instructions+'\n返回严格JSON {sections:[{section_id,items:[{title,body,source_id,source,event_date,event_quote,event_key,status,scope,company}],gap}]}。来源ID必须原样沿用，事件引用逐字连续复制对应日期的verified_event_excerpts，必须确实对应本条主体动作。历史候选的标题和日期可能错误，不能以报道日期代发生日；原文显示9月24日/9月23日或早年成果一律剔除。宏观和合资body最多150字，其他40到200字。不使用广告促销凑本轮多个主体。合资真实主体必须不同至少3家，不够就写实际缺口。技术必须中国境内产业化事实。企业车型上市、预告、海外、财报销量统计都剔除。preserve_title的板块title原样使用source.title。不补造first_occurrence_proof；需要首秀/全球首发表述的无历史证据直接剔除。无可信事实输出空数组。'
response=client.chat.completions.create(model=expand_env(provider['model']),messages=[dict(role='system',content=system),dict(role='user',content=json.dumps(dict(task='仅从已读来源修正文稿',sections=inputs,existing=[x for f in run.joinpath('working').glob('section-*.json') if 'partial' not in f.name for x in read(f).get('items',[])]),ensure_ascii=False))],max_tokens=10000,extra_body=provider.get('extra_body') or {})
text=response.choices[0].message.content or '';out=root/'outputs/weekly-report-monitor/window-repair';out.mkdir(exist_ok=True);(out/'model-output.txt').write_text(text,encoding='utf-8')
try:data=json.loads(text.strip().strip('`').removeprefix('json').strip())
except: data=json.JSONDecoder().raw_decode(text[text.find('{'):])[0]
accepted=[];audit=[]
for block in data.get('sections',[]):
 spec=next(s for s in v.SECTION_ROWS if s['id']==block['section_id']);valid=[]
 for item in block.get('items',[]):
  item['date']=item.get('event_date','')[5:].replace('-','.')
  errors=v.validate_item(item,spec,sources,req['start_date'],req['end_date'],coverage)
  if errors:audit.append(dict(section=spec['id'],title=item.get('title'),errors=errors))
  else:valid.append(item)
 accepted.append(dict(section_id=spec['id'],section=spec['section'],subsection=spec['subsection'],items=valid,gap=block.get('gap','')))
(out/'sections.json').write_text(json.dumps(accepted,ensure_ascii=False,indent=2),encoding='utf-8');(out/'validation.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8');print('validated_counts',[(x['section_id'],len(x['items'])) for x in accepted]);print('rejected',len(audit))
