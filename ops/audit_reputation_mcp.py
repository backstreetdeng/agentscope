"""Read-only inspection of the effective reputation MCP and existing detail APIs."""
import asyncio
import json
from pathlib import Path
import sys

import httpx
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from integrations.market_mcp_plugins import market_mcp_plugin_catalog
from utils.config import load_json_config


async def main():
    load_dotenv(ROOT/'.env',override=True)
    plugin=next(p for p in market_mcp_plugin_catalog(load_json_config()) if p.plugin_id=='reputation')
    print('endpoint',plugin.url)
    async with httpx.AsyncClient(headers={'Authorization':'Bearer '+plugin.resolve_token()},timeout=60) as client:
        async with streamable_http_client(plugin.url,http_client=client) as (read,write,_):
            async with ClientSession(read,write) as session:
                await session.initialize()
                requests=[('reputation_get_status',{'response_format':'json'}),
                          ('reputation_search_models',{'params':{'limit':100,'offset':0,'response_format':'json'}})]
                requests.extend(('reputation_get_model_summary',{'params':{'model':model,'response_format':'json'}})
                                for model in ['理想i8','星光730新能源'])
                for tool,args in requests:
                    result=await session.call_tool(tool,args)
                    for block in result.content:
                        if block.type=='text':
                            data=json.loads(block.text)
                            if tool=='reputation_get_model_summary':
                                data['groups']={k:v[:1] for k,v in data.get('groups',{}).items()}
                            print(tool,json.dumps(data,ensure_ascii=False))


if __name__=='__main__':
    asyncio.run(main())
