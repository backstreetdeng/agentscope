"""Parameterised, transaction-consistent read models for fixed page queries."""
import base64
import io
import os
import re
from datetime import date
from openpyxl import Workbook

from .pg import pg_connect
from .contracts.new_car import NewCarSearchInput, PlannedCarSearchInput
from .contracts.policy import PolicySearchInput, PolicyChangeInput, PolicyCompareInput, PolicyExportInput
from .contracts.reputation import ReputationModelInput
from .contracts.rights import Export, RightsChangeInput, Search


class VersionChanged(ValueError): pass


def page(values):
    limit, offset = int(values.get('limit', 20)), int(values.get('offset', 0))
    if not 1 <= limit <= 100 or not 0 <= offset <= 100000: raise ValueError('分页参数超出范围')
    return limit, offset


def dicts(cursor):
    return [dict(zip([c[0] for c in cursor.description], r)) for r in cursor.fetchall()]


def read_pg(function):
    db = pg_connect()
    try:
        db.set_session(readonly=True, isolation_level='REPEATABLE READ')
        with db.cursor() as cursor: return function(cursor)
    finally:
        db.rollback(); db.close()


def revision(cursor, table):
    if table not in {'new_car_model', 'planned_new_car', 'policy_record'}: raise ValueError('非法表')
    cursor.execute(f"SELECT md5(COALESCE(string_agg(row_to_json(t)::text,',' ORDER BY row_to_json(t)::text),'')) FROM {table} t")
    return cursor.fetchone()[0]


def check_version(expected, current):
    if expected and expected != current: raise VersionChanged()


def paged(rows, total, limit, offset, version):
    more = offset + len(rows) < total
    return dict(success=True, source='api', items=rows, total_count=total, count=len(rows), offset=offset,
                has_more=more, next_offset=offset + len(rows) if more else None, data_version=version)


def new_car_list(values, planned=False, detail=False, snapshot=False):
    limit, offset = page(values)
    if snapshot: limit, offset = 10000, 0
    cls = PlannedCarSearchInput if planned else NewCarSearchInput
    params = cls(**{k: v for k, v in values.items() if k in cls.model_fields})
    if detail and not params.model: raise ValueError('缺少车型')
    table = 'planned_new_car' if planned else 'new_car_model'
    columns = ('source_batch AS batch,source_row,origin_series AS series,enterprise,brand,model_code AS model,attr,vehicle_level,vehicle_type,energy_type,msrp,price_band,market_status,launch_year,launch_month,launch_quarter,selling_points,competitor,notes' if planned else 'model_style_id AS id,launch_year,launch_month,launch_date,region,brand,model,attr,vehicle_type,vehicle_level,series,enterprise,energy_type,import_batch,style_name')
    fields = [('brand', 'brand'), ('model', 'model_code' if planned else 'model'), ('energy_type', 'energy_type')]
    fields += [('market_status', 'market_status'), ('launch_quarter', 'launch_quarter')] if planned else [('enterprise', 'enterprise'), ('vehicle_type', 'vehicle_type')]
    clauses, args = [], []
    for key, column in fields:
        value = getattr(params, key, '')
        if value:
            clauses.append(column + ('=%s' if detail else ' ILIKE %s')); args.append(value if detail else '%' + value + '%')
    if planned and params.launch_year: clauses.append('launch_year=%s'); args.append(params.launch_year)
    if not planned:
        for value, op in [(params.launch_start, '>='), (params.launch_end, '<=')]:
            if value: clauses.append('launch_date ' + op + ' %s'); args.append(value)
    where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
    order = 'source_batch DESC,source_row' if planned else 'launch_date DESC NULLS LAST,model_style_id'
    def read(cursor):
        version = revision(cursor, table); check_version(values.get('data_version'), version)
        cursor.execute('SELECT COUNT(*) FROM ' + table + where, args); total = cursor.fetchone()[0]
        if snapshot and total > limit: raise ValueError('列表过大，请使用分页查询')
        cursor.execute('SELECT ' + columns + ' FROM ' + table + where + ' ORDER BY ' + order + ' LIMIT %s OFFSET %s', args + [limit, offset])
        return paged(dicts(cursor), total, limit, offset, version)
    return read_pg(read)


def new_car_status():
    def read(cursor):
        cursor.execute('SELECT COUNT(*) FROM new_car_model'); model_count = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM planned_new_car'); planned_count = cursor.fetchone()[0]
        cursor.execute('SELECT MAX(import_batch) FROM new_car_model'); latest_batch = cursor.fetchone()[0]
        return dict(success=True, source='api', status='ready', model_count=model_count, planned_count=planned_count, latest_batch=latest_batch)
    return read_pg(read)


def new_car_detail(values):
    model_style_id = values.get('model_style_id', '') or ''
    model = values.get('model', '') or ''
    if not model_style_id and not model: raise ValueError('model_style_id 和 model 至少提供一个')
    def read(cursor):
        if model_style_id:
            cursor.execute('SELECT * FROM new_car_model WHERE model_style_id=%s LIMIT 1', (model_style_id,))
        else:
            cursor.execute('SELECT * FROM new_car_model WHERE model=%s ORDER BY launch_date DESC NULLS LAST LIMIT 1', (model,))
        item = dicts(cursor)
        version = revision(cursor, 'new_car_model')
        return dict(success=True, source='api', item=item[0] if item else None, data_version=version)
    return read_pg(read)


def new_car_compare(values):
    from .monthly_sales_read import read_sales
    models = values.get('models', [])
    if not models:
        models = [m.strip() for m in str(values.get('models', '')).split(',') if m.strip()]
    if not (2 <= len(models) <= 10): raise ValueError('车型数量需在 2-10 之间')
    def read(cursor):
        comparisons = []
        for m in models:
            cursor.execute('SELECT * FROM new_car_model WHERE model=%s ORDER BY launch_date DESC NULLS LAST LIMIT 1', (m,))
            detail_rows = dicts(cursor)
            detail = detail_rows[0] if detail_rows else None
            sales = read_sales(cursor, {'model': m})
            comparisons.append({'model': m, 'detail': detail, 'sales_total': sales['total_sales'], 'sales_months': len(sales['items'])})
        return dict(success=True, source='api', comparisons=comparisons)
    return read_pg(read)


def new_car_dashboard():
    def read(cursor):
        cursor.execute('SELECT COUNT(*) AS spec_total,COUNT(DISTINCT (brand,model)) AS series_total,COUNT(DISTINCT brand) AS brand_total,MAX(import_batch) AS latest_batch FROM new_car_model'); stats = dicts(cursor)[0]
        cursor.execute('SELECT MAX(make_date(launch_year,launch_month,1)) FROM new_car_model WHERE launch_year BETWEEN 2000 AND 2100 AND launch_month BETWEEN 1 AND 12'); latest = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM planned_new_car'); stats['planned_total'] = cursor.fetchone()[0]
        cursor.execute("SELECT MAX(COALESCE(NULLIF(to_jsonb(n)->>'updated_at',''), NULLIF(to_jsonb(n)->>'imported_at',''), NULLIF(to_jsonb(n)->>'created_at',''), to_jsonb(n)->>'launch_date')::timestamptz)::date FROM new_car_model n")
        record_date = cursor.fetchone()[0]
        stats['latest_record_date'] = record_date.isoformat() if record_date else None
        cursor.execute('SELECT COUNT(*) FROM new_car_model WHERE launch_year=%s AND launch_month=%s', (latest.year, latest.month) if latest else (None, None)); stats['recent_total'] = cursor.fetchone()[0]
        stats.update(latest_month=latest.strftime('%Y-%m') if latest else None, field_count=15, last_successful_import=None, source='正式发布库 new_car_model（基础款型）')
        return dict(success=True, source='api', stats=stats, batch=stats['latest_batch'])
    return read_pg(read)


def new_car_sales(values):
    from .monthly_sales_read import read_sales
    return read_pg(lambda cursor: read_sales(cursor, values))


def policy_list(values, snapshot=False):
    limit, offset = page(values)
    if snapshot: limit, offset = 10000, 0
    params = PolicySearchInput(**{k: v for k, v in values.items() if k in PolicySearchInput.model_fields})
    def read(cursor):
        version = revision(cursor, 'policy_record'); check_version(values.get('data_version'), version)
        clauses, args = [], []
        for key, column in [('province', 'province'), ('city', 'city')]:
            if getattr(params, key): clauses.append(column + ' ILIKE %s'); args.append('%' + getattr(params, key) + '%')
        if params.keyword: clauses.append('EXISTS (SELECT 1 FROM jsonb_each_text(payload) p WHERE p.value ILIKE %s)'); args.append('%' + params.keyword + '%')
        if params.policy_type:
            clauses.append("(payload->>'促消费类型（统一表准/不统一标准）' ILIKE %s OR payload->>'适用客群（首购/增换购；个人/单位消费者；新能源/燃油车）' ILIKE %s)"); args.extend(['%' + params.policy_type + '%'] * 2)
        for value, op in [(params.start_date, '>='), (params.end_date, '<=')]:
            if value: clauses.append('monitor_date ' + op + ' %s'); args.append(value)
        where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
        cursor.execute('SELECT COUNT(*) FROM policy_record' + where, args); total = cursor.fetchone()[0]
        if snapshot and total > limit: raise ValueError('列表过大，请使用分页查询')
        cursor.execute('SELECT payload FROM policy_record' + where + ' ORDER BY monitor_date DESC NULLS LAST,record_id LIMIT %s OFFSET %s', args + [limit, offset]); rows = [r[0] for r in cursor.fetchall()]
        cursor.execute("SELECT headers FROM market_dataset_meta WHERE domain='policy'"); meta = cursor.fetchone()
        return dict(paged(rows, total, limit, offset, version), headers=meta[0] if meta else [])
    return read_pg(read)


def policy_status():
    def read(cursor):
        cursor.execute("SELECT source_name, generated_at, as_of_date, extraction_method FROM market_dataset_meta WHERE domain='policy'")
        row = cursor.fetchone()
        cursor.execute('SELECT COUNT(*) FROM policy_record'); total = cursor.fetchone()[0]
        version = revision(cursor, 'policy_record')
        return dict(success=True, source='api', status='ready', storage_backend='postgres', storage_table='policy_record',
                    record_count=total, data_version=version,
                    as_of=row[2] if row else '', source_name=row[0] if row else '', extraction_method=row[3] if row else '')
    return read_pg(read)


def policy_detail(values):
    record_id = values.get('record_id', '') or ''
    if not record_id: raise ValueError('缺少记录编号')
    def read(cursor):
        cursor.execute('SELECT payload FROM policy_record WHERE record_id=%s LIMIT 1', (record_id,))
        rows = [r[0] for r in cursor.fetchall()]
        version = revision(cursor, 'policy_record')
        return dict(success=True, source='api', item=rows[0] if rows else None, data_version=version)
    return read_pg(read)


def policy_changes(values):
    from .protocol import text_contains, date_in_range
    limit, offset = page(values)
    params = PolicyChangeInput(**{k: v for k, v in values.items() if k in PolicyChangeInput.model_fields})
    def read(cursor):
        version = revision(cursor, 'policy_record'); check_version(values.get('data_version'), version)
        cursor.execute('SELECT payload FROM policy_record ORDER BY monitor_date DESC NULLS LAST,record_id')
        records = [r[0] for r in cursor.fetchall()]
        matched = [r for r in records
                   if text_contains(r.get('省份'), params.province)
                   and text_contains(r.get('较上期变化类型'), params.change_type)
                   and (r.get('较上期变化类型') or r.get('较上期变化详情'))
                   and date_in_range(r.get('监测日期/发布日期'), params.start_date, params.end_date)]
        return paged(matched, len(matched), limit, offset, version)
    return read_pg(read)


def policy_compare(values):
    from .protocol import text_contains, any_text_contains, parse_date
    params = PolicyCompareInput(**{k: v for k, v in values.items() if k in PolicyCompareInput.model_fields})
    active_on = params.active_on
    def read(cursor):
        version = revision(cursor, 'policy_record')
        cursor.execute('SELECT payload FROM policy_record ORDER BY monitor_date DESC NULLS LAST,record_id')
        records = [r[0] for r in cursor.fetchall()]
        comparisons = []
        for region in params.regions:
            matched = [r for r in records
                       if (text_contains(r.get('省份'), region) or text_contains(r.get('城市'), region))
                       and any_text_contains(r, params.keyword)]
            if active_on:
                matched = [r for r in matched
                           if (parse_date(r.get('政策开始时间')) is None or parse_date(r.get('政策开始时间')) <= active_on)
                           and (parse_date(r.get('政策结束时间')) is None or parse_date(r.get('政策结束时间')) >= active_on)]
            comparisons.append({'region': region, 'count': len(matched), 'items': matched[:params.limit_per_region]})
        return dict(success=True, source='api', comparisons=comparisons, data_version=version)
    return read_pg(read)


def policy_overview():
    def read(cursor):
        cursor.execute("SELECT source_name FROM market_dataset_meta WHERE domain='policy'"); meta = cursor.fetchone()
        cursor.execute('SELECT COUNT(*) AS total,COUNT(*) FILTER (WHERE EXTRACT(YEAR FROM monitor_date)=%s) AS year_count,COUNT(DISTINCT NULLIF(province,\'\')) AS provinces,COUNT(DISTINCT (province,city)) FILTER (WHERE city<>\'\') AS cities,MAX(monitor_date) AS latest FROM policy_record', (date.today().year,)); s = dicts(cursor)[0]
        cursor.execute('SELECT payload FROM policy_record WHERE policy_name<>\'\' ORDER BY monitor_date DESC NULLS LAST,record_id LIMIT 1'); latest = [r[0] for r in cursor.fetchall()]
        topics = []
        for label, pattern in [('购车补贴', '购车补贴|汽车补贴|补助'), ('消费券', '消费券'), ('以旧换新', '以旧换新|报废更新|置换'), ('金融贴息', '贴息|贷款|金融'), ('新能源专项', '新能源|纯电|电动汽车')]:
            cursor.execute("SELECT COUNT(*) FROM policy_record WHERE concat_ws(' ',payload->>'政策名称',payload->>'当前政策补贴内容',payload->>'适用客群（首购/增换购；个人/单位消费者；新能源/燃油车）') ~ %s", (pattern,)); topics.append(dict(label=label, count=cursor.fetchone()[0]))
        cursor.execute('SELECT COUNT(DISTINCT k) FROM policy_record CROSS JOIN LATERAL jsonb_object_keys(payload) k'); fields = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM policy_record WHERE COALESCE(payload->>'政策名称','')='' AND COALESCE(payload->>'省份','')='' AND COALESCE(payload->>'城市','')='' AND COALESCE(payload->>'当前政策补贴内容','')='' AND COALESCE(payload->>'信息来源链接','')=''"); blanks = cursor.fetchone()[0]
        return dict(success=True, source='api', policy=dict(total=s['total'], year=str(date.today().year), yearCount=s['year_count'], provinceCount=s['provinces'], cityCount=s['cities'], latest=latest, topics=topics, fieldCount=fields, blankCount=blanks, source=meta[0] if meta else '', storage='postgres', latestCollectionDate=str(s['latest'] or '未提供')))
    return read_pg(read)


def workbook(rows, headers, filename):
    wb = Workbook(); sheet = wb.active; sheet.append(headers)
    for row in rows: sheet.append(['、'.join(str(v) for v in row.get(h, [])) if isinstance(row.get(h), list) else str(row.get(h) or '') for h in headers])
    for row in sheet:
        for cell in row:
            if isinstance(cell.value, str): cell.data_type = 's'
    sheet.freeze_panes = 'A2'; sheet.auto_filter.ref = sheet.dimensions
    output = io.BytesIO(); wb.save(output)
    return dict(success=True, source='api', file_name=filename, file_base64=base64.b64encode(output.getvalue()).decode(), row_count=len(rows))


def policy_export(values):
    from .protocol import text_contains, any_text_contains, date_in_range
    params = PolicyExportInput(**{k: v for k, v in values.items() if k in PolicyExportInput.model_fields})
    def read(cursor):
        cursor.execute('SELECT payload FROM policy_record ORDER BY monitor_date DESC NULLS LAST,record_id')
        records = [r[0] for r in cursor.fetchall()]
        matched = [r for r in records
                   if text_contains(r.get('省份'), params.province)
                   and text_contains(r.get('城市'), params.city)
                   and any_text_contains(r, params.keyword)]
        if params.policy_type:
            matched = [r for r in matched if text_contains(r.get('促消费类型（统一表准/不统一标准）'), params.policy_type)
                       or text_contains(r.get('适用客群（首购/增换购；个人/单位消费者；新能源/燃油车）'), params.policy_type)]
        matched = [r for r in matched if date_in_range(r.get('监测日期/发布日期'), params.start_date, params.end_date)]
        if params.record_ids:
            selected = set(params.record_ids)
            matched = [r for r in matched if r.get('记录编号') in selected]
        matched = matched[:params.limit]
        cursor.execute("SELECT headers FROM market_dataset_meta WHERE domain='policy'")
        row = cursor.fetchone()
        headers = row[0] if row else []
        if not headers and matched: headers = list(matched[0].keys())
        return workbook(matched, headers, '政策情报明细.xlsx')
    return read_pg(read)


def cloud():
    if os.getenv('MARKET_RIGHTS_BACKEND') != 'mysql': raise ValueError('权益 API 需连接腾讯云正式服务')
    from . import cloud_rights
    return cloud_rights


def rights_overview():
    status = cloud().status()
    return dict(success=True, source='api', rights=status['overview'], status=status)


def rights_list(values):
    module = cloud(); params = module.Search(**values)
    db = module.connect()
    try:
        payload = module.query(params, connection=db)
        with db.cursor() as c:
            c.execute('SELECT DISTINCT brand FROM ledger ORDER BY brand'); brands = [r['brand'] for r in c.fetchall()]
            c.execute("SELECT DISTINCT model_name FROM ledger WHERE model_name IS NOT NULL AND model_name<>'' ORDER BY model_name"); models = [r['model_name'] for r in c.fetchall()]
            c.execute("SELECT DISTINCT power_type FROM ledger WHERE power_type IS NOT NULL AND power_type<>'' ORDER BY power_type"); powers = [r['power_type'] for r in c.fetchall()]
        return dict(payload, source='api', headers=module.HEADERS, options=dict(brands=brands, models=models, powers=powers))
    finally:
        db.close()


def rights_export(values):
    module = cloud()
    if not values.get('data_version'): raise ValueError('缺少数据版本')
    return dict(module.export_payload(module.Export(**values)), source='api')


def rights_detail(values):
    record_id = values.get('record_id', '') or ''
    if not record_id.startswith('MYSQL-') or not record_id[6:].isdigit():
        raise ValueError('请使用查询返回的 MYSQL-主键编号')
    module = cloud()
    payload = module.query(Search(limit=1), 'id = %s', (int(record_id[6:]),))
    item = payload['items'][0] if payload['items'] else None
    return dict(success=True, source='api', item=item, data_version=payload['data_version'])


def rights_active(values):
    module = cloud()
    params = Search(**{k: v for k, v in values.items() if k in Search.model_fields})
    if not params.active_on:
        params = params.model_copy(update={'active_on': date.today()})
    return dict(module.query(params), source='api')


def rights_compare(values):
    module = cloud()
    models = values.get('models', []) or []
    if not models:
        models = [m.strip() for m in str(values.get('models', '')).split(',') if m.strip()]
    if not (2 <= len(models) <= 10): raise ValueError('车型数量需在 2-10 之间')
    active_on = values.get('active_on')
    comparisons = []
    for model in models:
        result = module.query(Search(model=model, active_on=active_on, limit=10))
        comparisons.append({'model': model, 'offer_count': result['total_count'],
                            'activity_counts': result['categories'], 'items': result['items']})
    return dict(success=True, source='api', comparisons=comparisons)


def rights_changes(values):
    module = cloud()
    params = RightsChangeInput(**{k: v for k, v in values.items() if k in RightsChangeInput.model_fields})
    payload = module.query(Search(brand=params.brand, limit=params.limit, offset=params.offset),
                           "(COALESCE(change_type,'') <> '' OR COALESCE(change_detail,'') <> '') AND LOCATE(%s,COALESCE(change_type,'')) > 0",
                           (params.change_type,))
    return dict(payload, source='api')


def reputation_read(path, values):
    from .reputation_sources import source_status
    model = ReputationModelInput(model=values.get('model', '')).model
    limit, offset = page(values)
    def read(cursor):
        if path.endswith('summary'):
            cursor.execute('SELECT direction,rank,primary_label,tertiary_labels,mention_count,mention_share,dongchedi_count,autohome_count,source_mentions,import_batch,taxonomy_version FROM new_car_reputation_taxonomy_summary WHERE model=%s ORDER BY direction,rank', (model,)); rows = dicts(cursor)
            metadata = source_status()
            return dict(success=True, source='api', groups={d: [r for r in rows if r['direction'] == d] for d in ['positive', 'negative']}, **{k: metadata[k] for k in ['analysis_current', 'analysis_source_version', 'analysis_method', 'analysis_batch']})
        if path.endswith('tree'):
            cursor.execute('SELECT direction,primary_label,secondary_label,tertiary_label,taxonomy_code,is_custom,COUNT(DISTINCT review_key) AS review_count FROM new_car_reputation_review_tag WHERE model=%s GROUP BY direction,primary_label,secondary_label,tertiary_label,taxonomy_code,is_custom ORDER BY direction,primary_label,secondary_label,review_count DESC', (model,)); return dict(success=True, source='api', items=dicts(cursor))
        direction, tag = values.get('direction'), values.get('tag', '')
        if direction not in {'positive', 'negative'} or not tag: raise ValueError('标签或方向无效')
        args = (model, direction, tag)
        cursor.execute('SELECT COUNT(*) FROM new_car_reputation_review_tag WHERE model=%s AND direction=%s AND tertiary_label=%s', args); total = cursor.fetchone()[0]
        cursor.execute('SELECT source,review_key,primary_label,secondary_label,tertiary_label,taxonomy_code,is_custom,excerpt,review_text FROM new_car_reputation_review_tag WHERE model=%s AND direction=%s AND tertiary_label=%s ORDER BY source,review_key LIMIT %s OFFSET %s', args + (limit, offset)); return paged(dicts(cursor), total, limit, offset, '')
    return read_pg(read)


def reputation_models(values):
    """列出当前有标签化口碑证据的车型（对应 reputation_search_models）。"""
    limit, offset = page(values)
    def read(cursor):
        cursor.execute('SELECT COUNT(DISTINCT model) AS total FROM new_car_reputation_review_tag'); total = cursor.fetchone()[0]
        cursor.execute('SELECT model, COUNT(DISTINCT review_key) AS review_count, MAX(import_batch) AS latest_batch FROM new_car_reputation_review_tag GROUP BY model ORDER BY review_count DESC, model LIMIT %s OFFSET %s', (limit, offset))
        return paged(dicts(cursor), total, limit, offset, '')
    return read_pg(read)


def reputation_tagged_reviews(values):
    """标签化评论检索（对应 reputation_search_reviews），读标签明细表而非原始表。"""
    limit, offset = page(values)
    direction = values.get('direction', '')
    if direction and direction not in {'positive', 'negative'}: raise ValueError('方向无效')
    clauses = ['TRUE']; args = []
    for column in ('model', 'primary_label', 'secondary_label', 'tertiary_label', 'source'):
        value = values.get(column, '')
        if value: clauses.append(column + ' ILIKE %s'); args.append('%' + value + '%')
    if direction: clauses.append('direction=%s'); args.append(direction)
    keyword = values.get('keyword', '')
    if keyword: clauses.append('(excerpt ILIKE %s OR review_text ILIKE %s)'); args.extend(['%' + keyword + '%', '%' + keyword + '%'])
    where = ' AND '.join(clauses)
    def read(cursor):
        cursor.execute('SELECT COUNT(*) FROM new_car_reputation_review_tag WHERE ' + where, tuple(args)); total = cursor.fetchone()[0]
        cursor.execute('SELECT model, direction, source, review_key, primary_label, secondary_label, tertiary_label, taxonomy_code, is_custom, excerpt, review_text, import_batch FROM new_car_reputation_review_tag WHERE ' + where + ' ORDER BY model, direction, source, review_key LIMIT %s OFFSET %s', tuple(args) + [limit, offset])
        return paged(dicts(cursor), total, limit, offset, '')
    return read_pg(read)


def reputation_compare(values):
    """多车型正负面口碑主题对比（对应 reputation_compare_models）。"""
    models = [m for m in values.get('models', []) if m]
    if not models:
        models = [m.strip() for m in values.get('models', '').split(',') if m.strip()]
    if not (2 <= len(models) <= 10): raise ValueError('车型数量需在 2-10 之间')
    top_n = min(max(int(values.get('top_n', '5')), 1), 10)
    def read(cursor):
        comparisons = []
        for m in models:
            cursor.execute('SELECT direction, rank, primary_label, mention_count, mention_share, source_mentions FROM new_car_reputation_taxonomy_summary WHERE model=%s AND rank<=%s ORDER BY direction, rank', (m, top_n))
            comparisons.append({'model': m, 'topics': dicts(cursor)})
        return dict(success=True, source='api', comparisons=comparisons)
    return read_pg(read)