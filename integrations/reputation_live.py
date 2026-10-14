"""All reputation consumers share the agent's remote reputation MCP plugin."""
import asyncio
import json


def decode(result):
    if result.isError:
        raise ValueError('口碑 MCP 查询失败')
    for block in result.content:
        if block.type=='text':
            data=json.loads(block.text)
            if data.get('success') is True: return data
    raise ValueError('口碑 MCP 未返回成功数据')


def summary_payload(model, analysis, raw):
    groups={direction:[{'rank':r['rank'],'label':r['primary_label'],'tertiary':r['tertiary_labels'],
                        'mentions':r['mention_count'],'share':float(r['mention_share']),
                        'source_mentions':r['source_mentions']} for r in rows]
            for direction,rows in analysis.get('groups',{}).items()}
    first=next((r for rows in analysis.get('groups',{}).values() for r in rows),{})
    analyzed_sources={'autohome':first.get('autohome_count',0),'dongchedi':first.get('dongchedi_count',0)}
    sources={'autohome':0,'dongchedi':0}
    sources.update({r['source']:r['review_count'] for r in raw['sources']})
    current=bool(analysis.get('analysis_current') and analysis.get('analysis_source_version')==raw['data_version'])
    return {'success':True,'source':'mcp','model':model,'available':bool(raw['total_count'] or first),
            'analysis_available':bool(first),'total_reviews':sum(analyzed_sources.values()),
            'sources':analyzed_sources,'raw_sources':sources,'raw_total':raw['total_count'],
            'raw_rows':raw['items'],'raw_version':raw['data_version'],
            'batch':first.get('import_batch') or analysis.get('analysis_batch'),
            'taxonomy_version':str(first.get('taxonomy_version') or '').split('/')[0],
            'analysis_current':current,'analysis_processed':current,'analysis_method':analysis.get('analysis_method','legacy_poc'),
            'groups':groups,'analysis_scope':'本批全部原文已扫描；仅明确观点入标签' if current else '当前为历史分析结果；原文更新后需维护端增量分析'}


def tree_payload(model, data):
    raw={'positive':{},'negative':{}}
    for r in data['items']:
        l1=raw[r['direction']].setdefault(r['primary_label'],{})
        l2=l1.setdefault(r['secondary_label'],[])
        l2.append({'name':r['tertiary_label'],'count':r['review_count'],'code':r['taxonomy_code'],'custom':r['is_custom']})
    # Aggregated MCP counts are per leaf and can overlap. Do not falsely sum them
    # and label the sum as unique reviews at parent levels.
    directions={direction:[{'name':p,'count':None,'children':[
        {'name':s,'count':None,'children':leaves} for s,leaves in secondaries.items()]}
        for p,secondaries in primaries.items()] for direction,primaries in raw.items()}
    return {'success':True,'source':'mcp','available':bool(data['items']),'model':model,'directions':directions}


async def fetch_reputation(config, operation='overview', params=None):
    params=params or {}
    from .market_data_api import get_data
    if operation == 'overview':
        return await get_data(config, 'reputation/overview', plugin_id='reputation')
    if operation == 'reviews':
        return await get_data(config, 'reputation/reviews', params=params, plugin_id='reputation')
    model = str(params.get('model', '')).strip()
    if not model: raise ValueError('缺少有效车型名称')
    if operation == 'summary':
        analysis, raw = await asyncio.gather(get_data(config, 'reputation/summary', params={'model': model}, plugin_id='reputation'), get_data(config, 'reputation/reviews', params={'model': model, 'limit': 20}, plugin_id='reputation'))
        return {**summary_payload(model, analysis, raw), 'source': 'api'}
    if operation == 'tree':
        return {**tree_payload(model, await get_data(config, 'reputation/tree', params={'model': model}, plugin_id='reputation')), 'source': 'api'}
    if operation == 'evidence':
        page=max(1,int(params.get('page',1)))
        data=await get_data(config, 'reputation/evidence', params={'model':model,'direction':params.get('direction',''),'tag':params.get('tag',''),'limit':20,'offset':(page-1)*20}, plugin_id='reputation')
        rows=[{'source':r['source'],'review_key':r['review_key'],'primary':r['primary_label'],'secondary':r['secondary_label'],'tertiary':r['tertiary_label'],'code':r['taxonomy_code'],'custom':r['is_custom'],'excerpt':r['excerpt'],'text':r['review_text']} for r in data['items']]
        return {'success':True,'source':'api','available':bool(rows),'rows':rows,'total':data['total_count'],'page':page,'page_size':20}
    raise ValueError('Unsupported reputation operation')


async def load_reputation(config, operation='overview', params=None):
    return await asyncio.wait_for(fetch_reputation(config,operation,params),timeout=90)
