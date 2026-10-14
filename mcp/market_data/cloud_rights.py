"""Tencent ledger adapter. Fixed read-only SQL; no local dataset fallback."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
from pathlib import Path
from datetime import date
from typing import Literal

from mcp.server.fastmcp import FastMCP
from openpyxl import Workbook
from pydantic import BaseModel, ConfigDict, Field
from .shared import READ_ONLY_ANNOTATIONS, PageInput, ResponseFormat, render_response, single

HEADERS = ['记录编号','监测日期/发布日期','车企/品牌','车型','年款及版本','动力类型','活动名称','活动开始日期','活动结束日期','适用地区及渠道','适用客群','原指导价','现指导价','当前活动价及口径','当前活动类型（支持多选）','活动内容','叠加及限制条件','较上期变化类型','较上期变化详情','信息来源链接','采集日期']
COLUMNS = ['id','monitor_date','brand','model_name','model_version','power_type','activity_name','activity_start','activity_end','region_channel','target_customer','original_msrp','current_msrp','current_price_note',None,None,'stacking_conditions','change_type','change_detail','source_url','crawl_date']
TYPES = {'现金优惠':'cash_discount','置换及增购补贴':'trade_in_subsidy','保险补贴':'insurance_subsidy','购置税补贴':'purchase_tax_subsidy','金融政策':'finance_policy','其他权益':'other_benefits'}
ROOT = Path('/opt/price-monitor')

class RightsIdInput(BaseModel):
    model_config=ConfigDict(str_strip_whitespace=True,extra='forbid')
    record_id: str=Field(min_length=1,max_length=80)
    response_format: ResponseFormat=ResponseFormat.JSON

class RightsCompareInput(BaseModel):
    model_config=ConfigDict(str_strip_whitespace=True,extra='forbid')
    models: list[str]=Field(min_length=2,max_length=10)
    active_on: date | None=None
    response_format: ResponseFormat=ResponseFormat.JSON

class RightsChangeInput(PageInput):
    brand: str=Field(default='',max_length=80)
    change_type: str=Field(default='',max_length=80)

class Search(PageInput):
    brand: str=Field(default='',max_length=80)
    model: str=Field(default='',max_length=100)
    keyword: str=Field(default='',max_length=200)
    activity_types: list[str]=Field(default_factory=list,max_length=6)
    region: str=Field(default='',max_length=100)
    active_on: date | None=None
    activity_match: Literal['any','all'] = 'any'
    power: str = Field(default='', max_length=80)
    start_date: date | None = None
    end_date: date | None = None
    exact_names: bool = False
    data_version: str = Field(default='', max_length=100)

class Export(Search):
    record_ids: list[str] = Field(default_factory=list, max_length=5000)
    limit: int = Field(default=5000, ge=1, le=5000)

def connect():
    import pymysql
    cfg = json.loads(Path(os.getenv('PRICE_MONITOR_CONFIG', ROOT/'config.json')).read_text())
    db = pymysql.connect(**cfg['mysql'], charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor)
    with db.cursor() as c:
        c.execute('START TRANSACTION READ ONLY')
    return db

def version(c):
    c.execute('SELECT COUNT(*) AS n, MAX(id) AS last_id, MAX(updated_at) AS changed, SUM(UNIX_TIMESTAMP(updated_at)) AS stamp FROM ledger')
    row = c.fetchone()
    return hashlib.sha256(json.dumps(row,default=str,sort_keys=True).encode()).hexdigest()[:32]

def present(row):
    result = {h: str(row.get(col) or '') for h,col in zip(HEADERS,COLUMNS) if col}
    result['记录编号'] = 'MYSQL-' + str(row['id'])
    result['原始记录编号'] = row.get('record_no') or ''
    result['当前活动类型（支持多选）'] = [h for h,col in TYPES.items() if str(row.get(col) or '').strip()]
    result['活动内容'] = '；'.join(f'{h}：{row[col]}' for h,col in TYPES.items() if str(row.get(col) or '').strip())
    result['有效期完整性'] = '已提供起止日期' if row.get('activity_start') and row.get('activity_end') else '日期不完整，生效状态待确认'
    return result

def where(params):
    parts,args = [],[]
    for attr,col in [('brand','brand'),('model','model_name'),('region','region_channel'),('power','power_type')]:
        value = getattr(params,attr,'')
        if value:
            parts.append(f'{col} = %s' if params.exact_names else f'LOCATE(%s, {col}) > 0')
            args.append(value)
    if params.keyword:
        fields = list(dict.fromkeys([c for c in COLUMNS if c and c!='id'] + list(TYPES.values()) + ['record_no']))
        parts.append('('+' OR '.join(f'LOCATE(%s, COALESCE({c},\'\')) > 0' for c in fields)+')')
        args.extend([params.keyword]*len(fields))
    if set(params.activity_types)-set(TYPES):
        raise ValueError('不支持的活动类型')
    if params.activity_types:
        joiner = ' OR ' if params.activity_match=='any' else ' AND '
        parts.append('('+joiner.join(f"TRIM(COALESCE({TYPES[t]},'')) <> ''" for t in params.activity_types)+')')
    for value,op in [(params.start_date,'>='),(params.end_date,'<=')]:
        if value:
            parts.append(f'monitor_date {op} %s'); args.append(value)
    if params.start_date and params.end_date and params.start_date>params.end_date:
        raise ValueError('起始日期不能晚于截止日期')
    if params.active_on:
        parts.extend(['(activity_start IS NULL OR activity_start <= %s)','(activity_end IS NULL OR activity_end >= %s)'])
        args.extend([params.active_on,params.active_on])
    return parts,args

def query(params, extra=None, extra_args=(), export=False, connection=None):
    db=connection or connect()
    try:
        with db.cursor() as c:
            v=version(c)
            if params.data_version and params.data_version!=v:
                raise ValueError('数据版本已变化，请刷新后重新查询或导出')
            parts,args=where(params)
            if extra: parts.append(extra); args.extend(extra_args)
            condition=' WHERE '+' AND '.join(parts) if parts else ''
            c.execute('SELECT COUNT(*) AS total FROM ledger'+condition,args)
            total=c.fetchone()['total']
            if export and total>params.limit:
                raise ValueError('导出超过上限，请缩小查询范围；未截断数据')
            c.execute('SELECT * FROM ledger'+condition+' ORDER BY monitor_date DESC, id DESC LIMIT %s OFFSET %s',args+[params.limit,0 if export else params.offset])
            items=[present(row) for row in c.fetchall()]
            c.execute('SELECT COUNT(DISTINCT brand) AS brands, COUNT(DISTINCT brand,model_name) AS models FROM ledger'+condition,args)
            metrics=c.fetchone()
            counts={t:f"SUM(TRIM(COALESCE({col},'')) <> '') AS t{i}" for i,(t,col) in enumerate(TYPES.items())}
            multi=' + '.join(f"(TRIM(COALESCE({col},'')) <> '')" for col in TYPES.values())
            c.execute('SELECT '+', '.join(counts.values())+f', SUM(({multi}) > 1) AS multi FROM ledger'+condition,args)
            activity=c.fetchone()
            return {'success':True,'data_source':'rights','data_version':v,'total_count':total,'count':len(items),'offset':params.offset,
                    'has_more':params.offset+len(items)<total,'next_offset':params.offset+len(items) if params.offset+len(items)<total else None,
                    'items':items,'metrics':dict(metrics,multi=int(activity['multi'] or 0)),
                    'categories':[{'label':t,'count':int(activity[f't{i}'] or 0)} for i,t in enumerate(TYPES)],
                    'warnings':['累计监测台账；不是去重活动数，也不代表全部正在生效。缺有效期记录属于待确认。']}
    finally:
        if connection is None: db.close()

def status():
    db=connect()
    try:
        result=query(Search(limit=1),connection=db)
        with db.cursor() as c:
            c.execute('SELECT MAX(monitor_date) AS monitor, MAX(crawl_date) AS crawl FROM ledger')
            dates={k:str(v or '') for k,v in c.fetchone().items()}
            c.execute('SELECT DISTINCT brand FROM ledger ORDER BY brand'); brands=[r['brand'] for r in c.fetchall()]
            c.execute("SELECT DISTINCT model_name FROM ledger WHERE model_name IS NOT NULL AND model_name<>'' ORDER BY model_name"); models=[r['model_name'] for r in c.fetchall()]
            c.execute("SELECT DISTINCT power_type FROM ledger WHERE power_type IS NOT NULL AND power_type<>'' ORDER BY power_type"); powers=[r['power_type'] for r in c.fetchall()]
        successful=[]
        for path in sorted((ROOT/'runs').glob('*/SUCCESS.json'),reverse=True):
            info=json.loads(path.read_text())
            if info.get('status')=='success' or info.get('done')==info.get('total'):
                successful=[{'target_date':info.get('target_date'), 'completed_at':info.get('completed_at'),'done':info.get('done'),'total':info.get('total')}]; break
        return dict(success=True,data_source='rights',status='ready',storage_backend='mysql',storage_table='price_monitor.ledger',
                    source='腾讯云每日价格权益监测台账',record_count=result['total_count'],data_version=result['data_version'],
                    as_of=dates['monitor'],latest_crawl_date=dates['crawl'],last_successful_import=None,last_successful_run=successful[0] if successful else None,
                    headers=HEADERS,activity_types=list(TYPES),options={'brands':brands,'models':models,'powers':powers},
                    overview={'total':result['total_count'],'brandCount':result['metrics']['brands'],'modelCount':result['metrics']['models'],
                              'multiTypeCount':result['metrics']['multi'],'categories':result['categories'],'latest':result['items']},warnings=result['warnings'])
    finally: db.close()

mcp=FastMCP('rights_mcp',host='127.0.0.1',port=8812,streamable_http_path='/mcp',stateless_http=True,json_response=True)

@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def rights_get_status(response_format:ResponseFormat=ResponseFormat.JSON)->str:
    """Return real MySQL storage, cumulative ledger metrics, batch status and filter options."""
    return render_response(status(),response_format)

@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def rights_search_offers(params:Search)->str:
    """Search cumulative ledger using database pagination. Activity types match any by default; dates filter monitor_date."""
    return render_response(query(params),params.response_format)

@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def rights_get_offer_detail(params:RightsIdInput)->str:
    """Get one row by stable MYSQL-primary-key ID; original record numbers may be duplicated."""
    if not params.record_id.startswith('MYSQL-') or not params.record_id[6:].isdigit():
        raise ValueError('请使用查询返回的 MYSQL-主键编号')
    result=query(Search(limit=1),'id = %s',(int(params.record_id[6:]),))
    return render_response(single(result['items'][0] if result['items'] else None,source='rights',version=result['data_version']),params.response_format)

@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def rights_get_active_offers(params:Search)->str:
    """Find candidates for active_on (defaults to today); undated rows are explicitly unconfirmed."""
    return render_response(query(params.model_copy(update={'active_on':params.active_on or date.today()})),params.response_format)

@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def rights_compare_models(params:RightsCompareInput)->str:
    """Compare stored cumulative ledger rows for two to ten model names, not unique live campaigns."""
    comparisons=[]
    for model in params.models:
        result=query(Search(model=model,active_on=params.active_on,limit=10))
        comparisons.append({'model':model,'offer_count':result['total_count'],'activity_counts':result['categories'],'items':result['items']})
    return render_response({'success':True,'data_source':'rights','comparisons':comparisons},params.response_format)

@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def rights_get_offer_changes(params:RightsChangeInput)->str:
    """List only explicit stored change fields; no inferred day-over-day changes."""
    result=query(Search(brand=params.brand,limit=params.limit,offset=params.offset),
                 "(COALESCE(change_type,'') <> '' OR COALESCE(change_detail,'') <> '') AND LOCATE(%s,COALESCE(change_type,'')) > 0",(params.change_type,))
    return render_response(result,params.response_format)

@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def rights_export_offers(params:Export)->str:
    """Export the identical query/version to approved 21-column Excel, base64 bytes; refuses truncation."""
    return render_response(export_payload(params),params.response_format)

def export_payload(params:Export)->dict:
    extra,args=None,()
    if params.record_ids:
        ids=[]
        for record_id in params.record_ids:
            if not record_id.startswith('MYSQL-') or not record_id[6:].isdigit(): raise ValueError('编号格式错误')
            ids.append(int(record_id[6:]))
        extra='id IN ('+','.join(['%s']*len(ids))+')'; args=tuple(ids)
    result=query(params,extra,args,export=True)
    if params.record_ids and result['count']!=len(set(params.record_ids)): raise ValueError('所选记录已变化或与筛选条件不符')
    workbook=Workbook(); sheet=workbook.active; sheet.title='权益明细'; sheet.append(HEADERS)
    for row in result['items']:
        sheet.append(['、'.join(row[h]) if isinstance(row[h],list) else row[h] for h in HEADERS])
    for row in sheet.iter_rows():
        for cell in row:
            if isinstance(cell.value,str): cell.data_type='s'
    sheet.freeze_panes='A2'; sheet.auto_filter.ref=sheet.dimensions
    out=io.BytesIO(); workbook.save(out)
    return {'success':True,'data_source':'rights','row_count':result['count'],'data_version':result['data_version'],
            'file_name':'权益情报明细.xlsx','file_base64':base64.b64encode(out.getvalue()).decode()}

class Auth:
    def __init__(self,app):
        self.app=app
        self.token=Path(os.environ['RIGHTS_MCP_TOKEN_FILE']).read_text().strip()
        if len(self.token)<32: raise RuntimeError('专用凭据缺失')
    async def __call__(self,scope,receive,send):
        import secrets
        if scope['type']=='http':
            auth=dict(scope.get('headers',[])).get(b'authorization',b'')
            if not secrets.compare_digest(auth,b'Bearer '+self.token.encode()):
                await send({'type':'http.response.start','status':401,'headers':[(b'content-type',b'application/json')]})
                await send({'type':'http.response.body','body':b'{"error":"unauthorized"}'})
                return
        await self.app(scope,receive,send)

if __name__=='__main__':
    import uvicorn
    from starlette.routing import Mount
    from .api_server import api_routes
    os.environ['MARKET_RIGHTS_BACKEND']='mysql'
    application=mcp.streamable_http_app()
    # The MCP application owns its lifespan; route HTTP reads on the same
    # loopback listener so the existing encrypted SSH channel remains usable.
    application.router.routes[0:0]=api_routes
    uvicorn.run(Auth(application),host='127.0.0.1',port=8812,access_log=False)
