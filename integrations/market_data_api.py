"""Authenticated client for deterministic page-data queries.

This is intentionally separate from ``market_mcp_plugins``: page rendering
uses REST, while agents retain the MCP catalog and tool discovery path.
"""
from __future__ import annotations

import os
import asyncio
import base64
import weakref
from urllib.parse import urlsplit, urlunsplit
from typing import Any

import httpx

from .market_mcp_plugins import market_mcp_plugin_catalog

_clients = weakref.WeakKeyDictionary()
_client_locks = weakref.WeakKeyDictionary()

async def http_client(base,token):
    loop=asyncio.get_running_loop()
    clients=_clients.setdefault(loop,{})
    lock=_client_locks.setdefault(loop,asyncio.Lock())
    key=(base,token)
    async with lock:
        if key not in clients:
            # Windows certificate discovery is synchronous and expensive.
            # Construct once off the agent loop, then reuse pooled connections.
            clients[key]=await asyncio.to_thread(httpx.AsyncClient,timeout=30,headers={'Authorization':'Bearer '+token})
        return clients[key]


def api_base_url(config: dict[str, Any], plugin_id: str | None = None) -> tuple[str, str]:
    catalog = market_mcp_plugin_catalog(config)
    plugin = next((item for item in catalog if item.plugin_id == plugin_id), None)
    if plugin and not plugin.enabled: raise ValueError('数据插件未启用')
    base = ''
    if plugin:
        # Endpoint-specific overrides win. A global URL must never send a
        # cloud credential to the LAN gateway or silently change data sources.
        explicit = os.getenv("MARKET_DATA_" + plugin_id.upper().replace("-", "_") + "_API_URL", "").strip().rstrip("/")
        parts = urlsplit(plugin.url)
        root = parts.path.split('/mcp',1)[0].rstrip('/')
        base = explicit or urlunsplit((parts.scheme,parts.netloc,root+'/api/v1','',''))
        global_token_env=str(config.get('mcp_plugins',{}).get('token_env','MARKET_MCP_API_TOKEN'))
        if not explicit and plugin.token_env==global_token_env:
            base=os.getenv('MARKET_DATA_API_BASE_URL','').strip().rstrip('/') or base
    if not base:
        base = str(config.get("mcp_plugins", {}).get("default_base_url", "")).rstrip("/") + "/api/v1"
    token = plugin.resolve_token() if plugin else os.getenv(str(config.get("mcp_plugins", {}).get("token_env", "MARKET_MCP_API_TOKEN")), "")
    if not token:
        raise ValueError("未配置数据服务凭据")
    return base, token


async def get_data(config: dict[str, Any], resource: str, *, params: dict[str, Any] | None = None, plugin_id: str | None = None) -> dict[str, Any]:
    base, token = api_base_url(config, plugin_id)
    if plugin_id == 'rights':
        from .rights_tunnel import ensure_tunnel
        await asyncio.to_thread(ensure_tunnel, base)
    client=await http_client(base,token)
    response = await client.get(base + "/" + resource.lstrip("/"), params=params)
    response.raise_for_status()
    data = response.json()
    if not data.get("success", True):
        raise ValueError(data.get("error", "业务数据服务返回失败"))
    return data


async def get_all(config,resource,*,params=None,plugin_id=None):
    """Compatibility for client-filtered tables: complete, version-checked pages."""
    values=dict(params or {},limit=100,offset=0)
    rows=[]; version=None; total=None; headers=[]
    while True:
        payload=await get_data(config,resource,params=values,plugin_id=plugin_id)
        current=payload.get('data_version')
        if version is not None and (current!=version or payload['total_count']!=total):
            raise ValueError('数据在分页读取期间变化，请刷新')
        version=current; total=payload['total_count']; headers=payload.get('headers',headers)
        items=payload['items']; rows.extend(items)
        if not payload['has_more']: break
        next_offset=payload.get('next_offset')
        if not items or not isinstance(next_offset,int) or next_offset<=values['offset']: raise ValueError('分页进度异常')
        values.update(offset=next_offset,data_version=version)
    if len(rows)!=total: raise ValueError('数据分页数量不一致')
    return dict(success=True,source='api',items=rows,total_count=total,data_version=version,headers=headers)


async def get_snapshot(config,resource,*,params=None,plugin_id=None):
    payload=await get_data(config,resource+'/snapshot',params=params,plugin_id=plugin_id)
    rows=payload['items']
    if payload.get('has_more') or len(rows)!=payload['total_count']:
        raise ValueError('列表未返回完整数据')
    keys=[row.get('记录编号') or row.get('id') or (row.get('batch'),row.get('source_row')) for row in rows]
    if len(set(keys))!=len(keys): raise ValueError('列表记录编号重复')
    return payload


async def export_data(config,resource,params,plugin_id):
    base,token=api_base_url(config,plugin_id)
    if plugin_id=='rights':
        from .rights_tunnel import ensure_tunnel
        await asyncio.to_thread(ensure_tunnel,base)
    client=await http_client(base,token)
    response=await client.post(base+'/'+resource,json=params,timeout=60)
    response.raise_for_status(); data=response.json()
    if not data.get('success'): raise ValueError('数据导出失败')
    return base64.b64decode(data['file_base64'],validate=True),data['file_name']


async def close_clients():
    loop=asyncio.get_running_loop()
    clients=_clients.pop(loop,{})
    _client_locks.pop(loop,None)
    await asyncio.gather(*(client.aclose() for client in clients.values()),return_exceptions=True)
