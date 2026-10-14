"""All rights presentation routes share the agent's cloud MCP configuration."""
import asyncio
import base64
import json
from .market_data_api import get_data

def decode(result):
    if result.isError: raise ValueError('权益 MCP 查询失败')
    for block in result.content:
        if getattr(block,'type','')=='text':
            data=json.loads(block.text)
            if data.get('success') is not True: raise ValueError('权益 MCP 返回失败')
            return data
    raise ValueError('权益 MCP 返回格式错误')

async def call_rights(config,tool,args):
    if tool == 'rights_get_status':
        return (await get_data(config, 'rights/overview', plugin_id='rights'))['status']
    if tool == 'rights_search_offers':
        params = dict(args.get('params') or {})
        types = params.pop('activity_types', [])
        if types:
            params['activity_type'] = types
        return await get_data(config, 'rights', params=params, plugin_id='rights')
    raise ValueError('权益导出尚未迁移到业务 API')

async def overview(config):
    return await get_data(config, 'rights/overview', plugin_id='rights')

async def export(config,params):
    from .market_data_api import export_data
    return await export_data(config,'rights/export',params,'rights')
