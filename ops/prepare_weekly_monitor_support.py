import sys,json,hashlib,importlib.util,re
from pathlib import Path
from datetime import datetime,timezone,timedelta
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
from tools.custom_tools import fetch_url_text
run=root/'runtime/weekly-report/weekly-20261014-101813-22d8a00c'
pkg=run/'working/skill-package/auto-weekly-report'
spec=importlib.util.spec_from_file_location('support_validator',pkg/'scripts/validate_weekly.py');v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
coverage=v.coverage_for_period((run/'inputs/coverage_log.md').read_text(encoding='utf-8'),'2026-09-26','2026-10-02')
out=root/'outputs/weekly-report-monitor/support';out.mkdir(parents=True,exist_ok=True)
candidates=[dict(section_id='macro',url='https://www.stats.gov.cn/xxgk/jd/sjjd2020/202609/t20260930_1965450.html',title='9月制造业PMI升至50.1%，经济景气水平回升',body='国家统计局9月30日发布中国采购经理指数。9月份制造业PMI为50.1%，比上月上升0.3个百分点，升至扩张区间；非制造业商务活动指数和综合PMI产出指数分别为50.2%和50.7%，均比上月上升1.2个百分点，经济景气水平有所回升。',company='国家统计局',date='2026-09-30'),dict(section_id='luxury',url='https://www.saic-audi.cn/audi-e/audi_brand/news/_-_0.html',title='',body='9月26日，上汽奥迪在上海推出面向新老车主的双节四重购车礼遇，包括价值20,000元整车终身质保、价值2,500元终身免费娱乐流量、增换购至高12,000元补贴，以及老车主推荐亲友成功购车至高价值2,000元奖励。此次品牌级活动面向国内消费者，围绕用车保障、增换购与车主推荐提供服务权益。',company='上汽奥迪',date='2026-09-26')]
result=[]
for c in candidates:
 text=fetch_url_text(c['url'],16000);title=re.search(r'(?m)^Title:\s*(.+)',text).group(1).strip();sid='src-'+hashlib.sha256(c['url'].encode()).hexdigest()[:24]
 path=out/(sid+'.txt');path.write_text(text,encoding='utf-8',newline='\n')
 source=dict(id=sid,url=c['url'],title=title,published=c['date'],text=text,fetched=True,fetched_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),fetch_method='web_fetch',text_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
 if c['section_id']=='macro':
  a=text.find('2026年9月30日国家统计局');b=text.find('个百分点，经济景气水平有所回升',a)+len('个百分点，经济景气水平有所回升。');quote=text[a:b]
 else:
  a=text.find('2026年9月26日，上海');b=text.find('共赴豪华出行新程',a)+len('共赴豪华出行新程。');quote=text[a:b]
 item=dict(title=c['title'] or title,body=c['body'],source_id=sid,source=c['url'],date=c['date'][5:].replace('-','.'),event_date=c['date'],event_quote=quote,event_key=c['company']+'|'+c['date']+'|'+(c['title'] or title),status='occurred',scope='china',company=c['company'])
 section=next(x for x in v.SECTION_ROWS if x['id']==c['section_id']);issues=v.validate_item(item,section,{sid:source},'2026-09-26','2026-10-02',coverage)
 result.append(dict(section_id=c['section_id'],item=item,source=source,source_file=str(path),issues=issues));print(c['section_id'],'issues',issues,'quote_chars',len(quote))
(out/'supplemental-facts.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
