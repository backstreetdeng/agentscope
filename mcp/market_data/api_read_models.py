"""Parameterised, transaction-consistent read models for fixed page queries."""
import base64
import io
import os
import re
from datetime import date
from openpyxl import Workbook
from .shared import pg_connect
from . import new_car_server, policy_server


class VersionChanged(ValueError): pass


def page(values):
    limit,offset=int(values.get('limit',20)),int(values.get('offset',0))
    if not 1 <= limit <= 100 or not 0 <= offset <= 100000: raise ValueError('分页参数超出范围')
    return limit,offset


def dicts(cursor):
    return [dict(zip([c[0] for c in cursor.description],r)) for r in cursor.fetchall()]


def read_pg(function):
    db=pg_connect()
    try:
        db.set_session(readonly=True,isolation_level='REPEATABLE READ')
        with db.cursor() as cursor: return function(cursor)
    finally: db.rollback(); db.close()


def revision(cursor,table):
    if table not in {'new_car_model','planned_new_car','policy_record'}: raise ValueError('非法表')
    cursor.execute(f"SELECT md5(COALESCE(string_agg(row_to_json(t)::text,',' ORDER BY row_to_json(t)::text),'')) FROM {table} t")
    return cursor.fetchone()[0]


def check_version(expected,current):
    if expected and expected != current: raise VersionChanged()


def paged(rows,total,limit,offset,version):
    more=offset+len(rows)<total
    return dict(success=True,source='api',items=rows,total_count=total,count=len(rows),offset=offset,
                has_more=more,next_offset=offset+len(rows) if more else None,data_version=version)


def new_car_list(values,planned=False,detail=False,snapshot=False):
    limit,offset=page(values)
    if snapshot: limit,offset=10000,0
    cls=new_car_server.PlannedCarSearchInput if planned else new_car_server.NewCarSearchInput
    params=cls(**{k:v for k,v in values.items() if k in cls.model_fields})
    if detail and not params.model: raise ValueError('缺少车型')
    table='planned_new_car' if planned else 'new_car_model'
    columns=('source_batch AS batch,source_row,origin_series AS series,enterprise,brand,model_code AS model,attr,vehicle_level,vehicle_type,energy_type,msrp,price_band,market_status,launch_year,launch_month,launch_quarter,selling_points,competitor,notes' if planned else 'model_style_id AS id,launch_year,launch_month,launch_date,region,brand,model,attr,vehicle_type,vehicle_level,series,enterprise,energy_type,import_batch,style_name')
    fields=[('brand','brand'),('model','model_code' if planned else 'model'),('energy_type','energy_type')]
    fields += [('market_status','market_status'),('launch_quarter','launch_quarter')] if planned else [('enterprise','enterprise'),('vehicle_type','vehicle_type')]
    clauses,args=[],[]
    for key,column in fields:
        value=getattr(params,key,'')
        if value:
            clauses.append(column+('=%s' if detail else ' ILIKE %s')); args.append(value if detail else '%'+value+'%')
    if planned and params.launch_year: clauses.append('launch_year=%s'); args.append(params.launch_year)
    if not planned:
        for value,op in [(params.launch_start,'>='),(params.launch_end,'<=')]:
            if value: clauses.append('launch_date '+op+' %s'); args.append(value)
    where=' WHERE '+' AND '.join(clauses) if clauses else ''
    order='source_batch DESC,source_row' if planned else 'launch_date DESC NULLS LAST,model_style_id'
    def read(cursor):
        version=revision(cursor,table); check_version(values.get('data_version'),version)
        cursor.execute('SELECT COUNT(*) FROM '+table+where,args); total=cursor.fetchone()[0]
        if snapshot and total>limit: raise ValueError('列表过大，请使用分页查询')
        cursor.execute('SELECT '+columns+' FROM '+table+where+' ORDER BY '+order+' LIMIT %s OFFSET %s',args+[limit,offset])
        return paged(dicts(cursor),total,limit,offset,version)
    return read_pg(read)


def new_car_dashboard():
    def read(cursor):
        cursor.execute('SELECT COUNT(*) AS spec_total,COUNT(DISTINCT (brand,model)) AS series_total,COUNT(DISTINCT brand) AS brand_total,MAX(import_batch) AS latest_batch FROM new_car_model'); stats=dicts(cursor)[0]
        cursor.execute('SELECT MAX(make_date(launch_year,launch_month,1)) FROM new_car_model WHERE launch_year BETWEEN 2000 AND 2100 AND launch_month BETWEEN 1 AND 12'); latest=cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM planned_new_car'); stats['planned_total']=cursor.fetchone()[0]
        cursor.execute("SELECT MAX(COALESCE(NULLIF(to_jsonb(n)->>'updated_at',''), NULLIF(to_jsonb(n)->>'imported_at',''), NULLIF(to_jsonb(n)->>'created_at',''), to_jsonb(n)->>'launch_date')::timestamptz)::date FROM new_car_model n")
        record_date=cursor.fetchone()[0]
        stats['latest_record_date']=record_date.isoformat() if record_date else None
        cursor.execute('SELECT COUNT(*) FROM new_car_model WHERE launch_year=%s AND launch_month=%s',(latest.year,latest.month) if latest else (None,None)); stats['recent_total']=cursor.fetchone()[0]
        stats.update(latest_month=latest.strftime('%Y-%m') if latest else None,field_count=15,last_successful_import=None,source='正式发布库 new_car_model（基础款型）')
        return dict(success=True,source='api',stats=stats,batch=stats['latest_batch'])
    return read_pg(read)


def new_car_sales(values):
    from .monthly_sales_read import read_sales
    return read_pg(lambda cursor:read_sales(cursor,values))


def policy_list(values,snapshot=False):
    limit,offset=page(values)
    if snapshot: limit,offset=10000,0
    params=policy_server.PolicySearchInput(**{k:v for k,v in values.items() if k in policy_server.PolicySearchInput.model_fields})
    def read(cursor):
        version=revision(cursor,'policy_record'); check_version(values.get('data_version'),version)
        clauses,args=[],[]
        for key,column in [('province','province'),('city','city')]:
            if getattr(params,key): clauses.append(column+' ILIKE %s'); args.append('%'+getattr(params,key)+'%')
        if params.keyword: clauses.append('EXISTS (SELECT 1 FROM jsonb_each_text(payload) p WHERE p.value ILIKE %s)'); args.append('%'+params.keyword+'%')
        if params.policy_type:
            clauses.append("(payload->>'促消费类型（统一表准/不统一标准）' ILIKE %s OR payload->>'适用客群（首购/增换购；个人/单位消费者；新能源/燃油车）' ILIKE %s)"); args.extend(['%'+params.policy_type+'%']*2)
        for value,op in [(params.start_date,'>='),(params.end_date,'<=')]:
            if value: clauses.append('monitor_date '+op+' %s'); args.append(value)
        where=' WHERE '+' AND '.join(clauses) if clauses else ''
        cursor.execute('SELECT COUNT(*) FROM policy_record'+where,args); total=cursor.fetchone()[0]
        if snapshot and total>limit: raise ValueError('列表过大，请使用分页查询')
        cursor.execute('SELECT payload FROM policy_record'+where+' ORDER BY monitor_date DESC NULLS LAST,record_id LIMIT %s OFFSET %s',args+[limit,offset]); rows=[r[0] for r in cursor.fetchall()]
        cursor.execute("SELECT headers FROM market_dataset_meta WHERE domain='policy'"); meta=cursor.fetchone()
        return dict(paged(rows,total,limit,offset,version),headers=meta[0] if meta else [])
    return read_pg(read)


def policy_overview():
    def read(cursor):
        cursor.execute("SELECT source_name FROM market_dataset_meta WHERE domain='policy'"); meta=cursor.fetchone()
        cursor.execute('SELECT COUNT(*) AS total,COUNT(*) FILTER (WHERE EXTRACT(YEAR FROM monitor_date)=%s) AS year_count,COUNT(DISTINCT NULLIF(province,\'\')) AS provinces,COUNT(DISTINCT (province,city)) FILTER (WHERE city<>\'\') AS cities,MAX(monitor_date) AS latest FROM policy_record',(date.today().year,)); s=dicts(cursor)[0]
        cursor.execute('SELECT payload FROM policy_record WHERE policy_name<>\'\' ORDER BY monitor_date DESC NULLS LAST,record_id LIMIT 1'); latest=[r[0] for r in cursor.fetchall()]
        topics=[]
        for label,pattern in [('购车补贴','购车补贴|汽车补贴|补助'),('消费券','消费券'),('以旧换新','以旧换新|报废更新|置换'),('金融贴息','贴息|贷款|金融'),('新能源专项','新能源|纯电|电动汽车')]:
            cursor.execute("SELECT COUNT(*) FROM policy_record WHERE concat_ws(' ',payload->>'政策名称',payload->>'当前政策补贴内容',payload->>'适用客群（首购/增换购；个人/单位消费者；新能源/燃油车）') ~ %s",(pattern,)); topics.append(dict(label=label,count=cursor.fetchone()[0]))
        cursor.execute('SELECT COUNT(DISTINCT k) FROM policy_record CROSS JOIN LATERAL jsonb_object_keys(payload) k'); fields=cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM policy_record WHERE COALESCE(payload->>'政策名称','')='' AND COALESCE(payload->>'省份','')='' AND COALESCE(payload->>'城市','')='' AND COALESCE(payload->>'当前政策补贴内容','')='' AND COALESCE(payload->>'信息来源链接','')=''"); blanks=cursor.fetchone()[0]
        return dict(success=True,source='api',policy=dict(total=s['total'],year=str(date.today().year),yearCount=s['year_count'],provinceCount=s['provinces'],cityCount=s['cities'],latest=latest,topics=topics,fieldCount=fields,blankCount=blanks,source=meta[0] if meta else '',storage='postgres',latestCollectionDate=str(s['latest'] or '未提供')))
    return read_pg(read)


def workbook(rows,headers,filename):
    wb=Workbook(); sheet=wb.active; sheet.append(headers)
    for row in rows: sheet.append(['、'.join(str(v) for v in row.get(h,[])) if isinstance(row.get(h),list) else str(row.get(h) or '') for h in headers])
    for row in sheet:
        for cell in row:
            if isinstance(cell.value,str): cell.data_type='s'
    sheet.freeze_panes='A2'; sheet.auto_filter.ref=sheet.dimensions
    output=io.BytesIO(); wb.save(output)
    return dict(success=True,source='api',file_name=filename,file_base64=base64.b64encode(output.getvalue()).decode(),row_count=len(rows))


def policy_export(values):
    ids=values.get('record_ids',[])
    if not isinstance(ids,list) or not ids or len(ids)>5000 or not values.get('data_version'): raise ValueError('导出参数无效')
    def read(cursor):
        check_version(values['data_version'],revision(cursor,'policy_record'))
        cursor.execute('SELECT payload FROM policy_record WHERE record_id=ANY(%s) ORDER BY monitor_date DESC NULLS LAST,record_id',(ids,)); rows=[r[0] for r in cursor.fetchall()]
        if len(rows)!=len(set(ids)): raise VersionChanged()
        cursor.execute("SELECT headers FROM market_dataset_meta WHERE domain='policy'"); headers=cursor.fetchone()[0]
        return workbook(rows,headers,'政策情报明细.xlsx')
    return read_pg(read)


def cloud():
    if os.getenv('MARKET_RIGHTS_BACKEND')!='mysql': raise ValueError('权益 API 需连接腾讯云正式服务')
    from . import cloud_rights
    return cloud_rights


def rights_overview():
    status=cloud().status()
    return dict(success=True,source='api',rights=status['overview'],status=status)


def rights_list(values):
    module=cloud(); params=module.Search(**values)
    db=module.connect()
    try:
        payload=module.query(params,connection=db)
        with db.cursor() as c:
            c.execute('SELECT DISTINCT brand FROM ledger ORDER BY brand'); brands=[r['brand'] for r in c.fetchall()]
            c.execute("SELECT DISTINCT model_name FROM ledger WHERE model_name IS NOT NULL AND model_name<>'' ORDER BY model_name"); models=[r['model_name'] for r in c.fetchall()]
            c.execute("SELECT DISTINCT power_type FROM ledger WHERE power_type IS NOT NULL AND power_type<>'' ORDER BY power_type"); powers=[r['power_type'] for r in c.fetchall()]
        return dict(payload,source='api',headers=module.HEADERS,options=dict(brands=brands,models=models,powers=powers))
    finally: db.close()


def rights_export(values):
    module=cloud()
    if not values.get('data_version'): raise ValueError('缺少数据版本')
    return dict(module.export_payload(module.Export(**values)),source='api')


def reputation_read(path,values):
    from .reputation_sources import source_status
    model=new_car_server.ModelInput(model=values.get('model','')).model
    limit,offset=page(values)
    def read(cursor):
        if path.endswith('summary'):
            cursor.execute('SELECT direction,rank,primary_label,tertiary_labels,mention_count,mention_share,dongchedi_count,autohome_count,source_mentions,import_batch,taxonomy_version FROM new_car_reputation_taxonomy_summary WHERE model=%s ORDER BY direction,rank',(model,)); rows=dicts(cursor)
            metadata=source_status()
            return dict(success=True,source='api',groups={d:[r for r in rows if r['direction']==d] for d in ['positive','negative']},**{k:metadata[k] for k in ['analysis_current','analysis_source_version','analysis_method','analysis_batch']})
        if path.endswith('tree'):
            cursor.execute('SELECT direction,primary_label,secondary_label,tertiary_label,taxonomy_code,is_custom,COUNT(DISTINCT review_key) AS review_count FROM new_car_reputation_review_tag WHERE model=%s GROUP BY direction,primary_label,secondary_label,tertiary_label,taxonomy_code,is_custom ORDER BY direction,primary_label,secondary_label,review_count DESC',(model,)); return dict(success=True,source='api',items=dicts(cursor))
        direction,tag=values.get('direction'),values.get('tag','')
        if direction not in {'positive','negative'} or not tag: raise ValueError('标签或方向无效')
        args=(model,direction,tag)
        cursor.execute('SELECT COUNT(*) FROM new_car_reputation_review_tag WHERE model=%s AND direction=%s AND tertiary_label=%s',args); total=cursor.fetchone()[0]
        cursor.execute('SELECT source,review_key,primary_label,secondary_label,tertiary_label,taxonomy_code,is_custom,excerpt,review_text FROM new_car_reputation_review_tag WHERE model=%s AND direction=%s AND tertiary_label=%s ORDER BY source,review_key LIMIT %s OFFSET %s',args+(limit,offset)); return paged(dicts(cursor),total,limit,offset,'')
    return read_pg(read)
