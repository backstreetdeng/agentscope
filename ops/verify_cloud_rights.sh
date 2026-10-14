set -eu
cd /opt/price-monitor/rights-mcp/releases/20261011-v1
/opt/price-monitor/rights-mcp/venv/bin/python - <<'PY'
import asyncio,json,base64,io
from pathlib import Path
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from openpyxl import load_workbook
from market_data.cloud_rights import HEADERS
def decode(r):
    if r.isError:
        print('tool_failed',r.content[0].text[:350]);raise RuntimeError('tool_failed')
    return json.loads(r.content[0].text)
async def main():
    url='http://127.0.0.1:8812/mcp'
    async with httpx.AsyncClient() as client:
        for headers in ({},{'Authorization':'Bearer invalid'}):
            r=await client.post(url,headers=headers,json={});assert r.status_code==401
    token=Path('/opt/price-monitor/rights-mcp/token').read_text().strip()
    async with httpx.AsyncClient(headers={'Authorization':'Bearer '+token}) as client:
        async with streamable_http_client(url,http_client=client) as (read,write,_):
            async with ClientSession(read,write) as session:
                await session.initialize()
                tools=await session.list_tools();assert len(tools.tools)==7
                s=decode(await session.call_tool('rights_get_status',{}))
                assert s['storage_backend']=='mysql'
                print('STATUS',json.dumps({k:s[k] for k in ('record_count','as_of','latest_crawl_date','last_successful_run','overview')},ensure_ascii=False,default=str))
                ids=[];first=[];offset=0
                while True:
                    p=decode(await session.call_tool('rights_search_offers',{'params':{'limit':100,'offset':offset,'data_version':s['data_version']}}))
                    if not first:first=p['items'][:5]
                    ids.extend(r['记录编号'] for r in p['items'])
                    if not p['has_more']:break
                    offset=p['next_offset']
                assert len(ids)==len(set(ids))==s['record_count']
                detail=decode(await session.call_tool('rights_get_offer_detail',{'params':{'record_id':first[0]['记录编号']}}))
                assert detail['item']==first[0]
                for mode in ('any','all'):
                    p=decode(await session.call_tool('rights_search_offers',{'params':{'activity_types':['现金优惠','金融政策'],'activity_match':mode}}))
                    for row in p['items']:
                        types=set(row['当前活动类型（支持多选）'])
                        assert bool(types & {'现金优惠','金融政策'}) if mode=='any' else {'现金优惠','金融政策'}.issubset(types)
                for tool,params in [('rights_get_active_offers',{'limit':2}),('rights_compare_models',{'models':['ES6','L6']}),('rights_get_offer_changes',{'limit':2})]:
                    assert decode(await session.call_tool(tool,{'params':params}))['success']
                exported=decode(await session.call_tool('rights_export_offers',{'params':{'record_ids':[r['记录编号'] for r in first],'limit':5,'data_version':s['data_version']}}))
                book=load_workbook(io.BytesIO(base64.b64decode(exported['file_base64'])))
                assert list(next(book.active.values))==HEADERS
                assert book.active.max_row==6
                print('ACCEPTANCE_OK',json.dumps({'tools':7,'unique_records':len(ids),'headers':len(HEADERS),'export_rows':exported['row_count'],'auth':401}))
asyncio.run(main())
PY
