import json, sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
from utils.weekly_report_jobs import read, write, validator
from skill_runtime import SkillRegistry
run=root/'runtime/weekly-report/weekly-20261014-101813-22d8a00c'
v=validator(SkillRegistry([run/'working/skill-package']).get('auto-weekly-report'))
req=read(run/'inputs/request.json'); sources=read(run/'working/sources.json')
coverage=v.coverage_for_period((run/'inputs/coverage_log.md').read_text(encoding='utf-8'),req['start_date'],req['end_date'])
raw=(root/'outputs/weekly-report-monitor/window-repair/model-output.txt').read_text(encoding='utf-8')
data=json.JSONDecoder().raw_decode(raw[raw.find('{'):])[0]
audit=[]
existing=[i for p in run.joinpath('working').glob('section-*.json') if 'partial' not in p.name for i in read(p).get('items',[])]
for block in data['sections']:
    sid=block['section_id']
    if sid not in ['executive','intelligent']:continue
    spec=next(s for s in v.SECTION_ROWS if s['id']==sid)
    accepted=[]
    for item in block['items']:
        item['date']=item['event_date'][5:].replace('-','.')
        if spec.get('preserve_title'):item['title']=sources[item['source_id']]['title']
        if sid=='executive' and item['event_date']=='2026-10-02':
            item['body']='10月2日，媒体据广汽集团发布的冯兴亚调研车展信息获悉，黄坚出任广汽丰田执行副总经理，李勇接任广汽传祺BU总裁。两人此前分别担任广汽传祺BU总裁、广汽商贸董事长。'
        if sid=='intelligent':
            item['body']='9月28日，速腾聚创宣布第二代全固态超广角激光雷达E2与超长距EM4正式接入NVIDIA Holoscan Sensor Bridge（HSB）。E2基于自研SPAD-SoC芯片，EM4最高2160线、测距600米，连接物理感知与AI计算链路。'
        errors=v.validate_item(item,spec,sources,req['start_date'],req['end_date'],coverage)
        if any(v.same_story(item,old) for old in existing):errors.append('与已验收正文重复')
        audit.append(dict(section=sid,title=item['title'],errors=errors))
        if not errors:accepted.append(item)
    if accepted and not v.section_issues(spec,accepted):
        dest=run/'working'/('section-'+sid+'.json')
        if dest.exists() and read(dest).get('items'):continue
        write(dest,dict(section=spec['section'],subsection=spec['subsection'],items=accepted,gap=''))
        existing.extend(accepted)
write(root/'outputs/weekly-report-monitor/window-repair/merge-validation.json',audit)
print(json.dumps(audit,ensure_ascii=False))
