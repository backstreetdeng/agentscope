"""Produce an auditable maintenance workbook; neither database is modified."""
import asyncio
from datetime import date, datetime
import json
from pathlib import Path
from collections import Counter
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from audit_new_car_publication import local_snapshot, remote_snapshot, sid, ROOT

CUTOFF = date(2026, 10, 1)
HEADERS = ['汽车之家款型ID','车系ID','品牌','车系名称','款型名称','厂商','车型级别','上市日期','指导价原文','维护状态','交付文件名或路径','来源及核验说明']

def base_row(r, state):
    return [sid(r['spec_id']),sid(r['series_id']),r['brand_name'],r['series_name'],r['spec_name'],r['factory_name'],r['vehicle_class'],r['launch_date'],r['min_price'],state,'','']

def put_sheet(wb, name, headers, rows):
    ws = wb.create_sheet(name)
    ws.append(headers)
    for row in rows:
        ws.append(row)
    ws.freeze_panes = 'A2'
    ws.auto_filter.ref = ws.dimensions
    ws.sheet_view.showGridLines = False
    ws.row_dimensions[1].height = 30
    for cell in ws[1]:
        cell.font = Font(name='Microsoft YaHei', size=10, bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='24466B')
        cell.alignment = Alignment(vertical='center', wrap_text=True)
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.font = Font(name='Microsoft YaHei', size=10)
            cell.alignment = Alignment(vertical='top', wrap_text=True)
            if isinstance(cell.value, str):
                cell.data_type = 's'
            if isinstance(cell.value, date):
                cell.number_format = 'yyyy-mm-dd'
            if cell.row % 2 == 0:
                cell.fill = PatternFill('solid', fgColor='F1F5FA')
    for i, header in enumerate(headers, 1):
        ws.column_dimensions[get_column_letter(i)].width = 22 if '名称' in header else 17
    if '维护状态' in headers:
        col = get_column_letter(headers.index('维护状态')+1)
        validation = DataValidation(type='list', formula1='"待补配置,已有ODS待整理,有成果待核验,已整理待校验,已核验,不适用待确认,旧库待确认,边界待确认"')
        ws.add_data_validation(validation)
        validation.add(f'{col}2:{col}{max(2,ws.max_row)}')
        for row in ws.iter_rows(min_row=2, min_col=headers.index('维护状态')+1):
            for cell in row:
                cell.fill = PatternFill('solid', fgColor='FFF5D9')
    return ws

async def main():
    counts, base, configs, history, ods, runs, success = local_snapshot()
    remote_status, old = await remote_snapshot()
    current = {sid(r['spec_id']):r for r in base}
    chosen = {}
    for r in sorted(history, key=lambda x:str(x.get('snapshot_at') or '')):
        chosen[sid(r['汽车之家款型id'])] = (r,'历史归档',str(r.get('snapshot_at') or ''))
    for r in configs:
        chosen[sid(r['汽车之家款型id'])] = (r,'当前周表','本次读取的当前成果')
    before = sorted((r for r in base if r['launch_date'] and r['launch_date'] < CUTOFF),key=lambda r:(r['launch_date'],r['series_name'],r['spec_id']))
    missing = [r for r in before if sid(r['spec_id']) not in chosen]
    raw_ids = ods.get('ods_pz_base_info',set()) & ods.get('ods_pz_detail_info',set())
    raw_pending = [r for r in missing if sid(r['spec_id']) in raw_ids]
    need_files = [r for r in missing if sid(r['spec_id']) not in raw_ids]
    existing = [r for r in before if sid(r['spec_id']) in chosen]
    boundary = [r for r in base if r['launch_date'] and r['launch_date'] >= CUTOFF]
    legacy_only = [r for r in old if sid(r['id']) not in current]
    wb = Workbook()
    wb.remove(wb.active)
    notes = [
        ['定版口径','仅按上市日期：2026-01-01至2026-09-30；10月1日当天单列。不是还原9月30日当天数据库快照。'],
        ['统计来源','本机postgres/public只读快照＋146现有新车MCP；读取时点以配套JSON为准。'],
        ['优先处理','缺配置款型含两类：已有ODS待整理，不必重采；待补配置请先查找历史原始Excel。黄色列填写状态、交付路径及说明。'],
        ['已有配置','仅证明有当前或历史成果，不代表76列全部完整；该表提示基础信息缺失和未定属性。'],
        ['原始格式','保留下游爬虫Excel的格式：第一列配置项目、后续列各款型；包含车型名称、款型名称、款型ID等原始识别行。不用把全部配置手工抄进清单。'],
        ['字段边界','缺失保留为空；无/不适用与未采集分开，燃油和电动车配置不要求相同。不要猜测属性或用0代替缺失。'],
        ['原始文件','保留文件名、采集日期、来源链接（如有）。允许一次交付多个款型的配置，但每款必须可对应唯一款型ID。'],
        ['旧库独有','先确认18个旧库款型是否仍属于正式范围；不直接删除，不自动当成必须重采的新款型。'],
        ['新车属性','全新/换代/年型/增补/改款为业务维护分类，不能由年款推断。已有分类应保留，缺失由业务确认。'],
        ['已有成果','本工作簿附当前76列成果及当前＋历史选取的配置档案，均为数据库原值；没有自动拼补旧版空字段。'],
        ['周度维护','新增款型、旧款型修订、迟到历史配置都进入批次增量；不能只筛上市日期晚于10月1日。'],
        ['安全边界','本次只生成文件，不采集、不导入、不清空数据库或爬虫Excel目录。'],
    ]
    put_sheet(wb,'使用说明',['项目','说明'],notes).column_dimensions['B'].width = 105
    put_sheet(wb,'缺配置款型',HEADERS,[base_row(r,'已有ODS待整理' if sid(r['spec_id']) in raw_ids else '待补配置') for r in missing])
    put_sheet(wb,'已有ODS待整理',HEADERS,[base_row(r,'已有ODS待整理') for r in raw_pending])
    groups={}
    for r in need_files:
        groups.setdefault((r['series_id'],r['brand_name'],r['series_name']),[]).append(r)
    put_sheet(wb,'补充文件按车系',['车系ID','品牌','车系名称','需补原始配置款型ID','维护状态','交付文件名或路径','说明'],[
        [sid(key[0]),key[1],key[2],' / '.join(sid(r['spec_id']) for r in items),'待补配置','','优先复用历史文件，不要求重新采集']
        for key,items in sorted(groups.items(),key=lambda item:(item[0][1],item[0][2]))])
    extra = ['成果来源','成果快照','基础字段缺失','新车属性']
    known = []
    for r in existing:
        record, origin, snapshot = chosen[sid(r['spec_id'])]
        blank = [f for f in ['汽车之家款型名称','指导价','品牌','车型','企业','车型级别'] if not str(record.get(f) or '').strip()]
        known.append(base_row(r,'有成果待核验')+[origin,snapshot,'、'.join(blank),record.get('属性') or '待业务确认'])
    put_sheet(wb,'已有配置待核验',HEADERS+extra,known)
    put_sheet(wb,'10月1日及以后',HEADERS,[base_row(r,'边界待确认') for r in boundary])
    put_sheet(wb,'旧库独有待确认',['汽车之家款型ID','品牌','车型','企业','上市日期旧值','属性旧值','维护状态','确认说明'],[
        [sid(r['id']),r['brand'],r['model'],r['enterprise'],str(r['launch_date'] or ''),r['attr'],'旧库待确认',''] for r in legacy_only])
    fields = list(configs[0]) if configs else [f for f in history[0] if f!='snapshot_at']
    assert len(fields)==76
    put_sheet(wb,'当前76列成果',fields,[[r.get(f) for f in fields] for r in configs])
    cumulative = [chosen[key] for key in sorted(chosen,key=lambda x:int(x) if x.isdigit() else 0)]
    put_sheet(wb,'累计配置档案',fields+['成果来源','快照说明'],[[r.get(f) for f in fields]+[origin,snapshot] for r,origin,snapshot in cumulative])
    put_sheet(wb,'76列字段说明',['序号','数据库字段','维护要求'],[[i,f,'以原始配置或业务确认填写；缺失、不适用分开，不猜测'] for i,f in enumerate(fields,1)])
    folder=ROOT/'outputs'/'new-car-baseline'
    folder.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now().strftime('%Y%m%d-%H%M%S')
    path=folder/f'新车历史定版与配置补齐清单-{stamp}.xlsx'
    wb.save(path)
    check=load_workbook(path,read_only=True,data_only=False)
    assert check['缺配置款型'].max_row-1==len(missing)
    assert check['当前76列成果'].max_column==76
    assert check['累计配置档案'].max_row-1==len(chosen)
    assert len({row[0] for row in check['缺配置款型'].iter_rows(min_row=2,values_only=True)})==len(missing)
    errors={'#REF!','#DIV/0!','#VALUE!','#N/A','#NAME?','#NUM!','#NULL!'}
    assert not any(c.data_type in ('f','e') or str(c.value) in errors for sheet in check for row in sheet for c in row)
    check.close()
    summary={'created_at':datetime.now().astimezone().isoformat(),'cutoff_exclusive':str(CUTOFF),'baseline_candidates':len(before),'missing_config':len(missing),'existing_config':len(existing),'existing_ods_pending':len(raw_pending),'need_source_files':len(need_files),'need_source_series':len(groups),'october_first_or_later':len(boundary),'legacy_only_to_confirm':len(legacy_only),'all_local_base':len(base),'current_config_rows':len(configs),'cumulative_config_ids':len(chosen),'workbook':str(path),'database_modified':False,'validation':'passed; no formulas or Excel errors'}
    path.with_suffix('.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':
    asyncio.run(main())
