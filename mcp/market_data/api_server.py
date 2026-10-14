"""Page HTTP endpoints over shared read models. No MCP transport on this path."""
from __future__ import annotations
import asyncio
import json
import os
import secrets
import time
from pathlib import Path

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from . import api_read_models as reads
from .reputation_sources import SourceReviewInput, search_source_reviews, source_status


class DataJSON(JSONResponse):
    def render(self, content):
        return json.dumps(content, ensure_ascii=False, allow_nan=False, default=str).encode('utf-8')


_cache = {}
_locks = {}
async def cached(key, function, refresh=False):
    async with _locks.setdefault(key, asyncio.Lock()):
        if not refresh and key in _cache and time.monotonic()-_cache[key][0] < 60:
            return _cache[key][1]
        data = await asyncio.to_thread(function)
        _cache[key] = (time.monotonic(), data)
        return data


async def dispatch(request):
    path = request.path_params['resource'].strip('/')
    values = dict(request.query_params)
    try:
        if os.getenv('MARKET_RIGHTS_BACKEND') == 'mysql' and not path.startswith('rights'):
            return DataJSON(dict(success=False,error='未定义的业务资源'),status_code=404)
        if request.method == 'POST':
            body = await request.json()
            if path == 'policies/export': payload = await asyncio.to_thread(reads.policy_export, body)
            elif path == 'rights/export': payload = await asyncio.to_thread(reads.rights_export, body)
            else: return DataJSON(dict(success=False,error='未定义的业务资源'),status_code=404)
            return DataJSON(payload)
        overview = {'policy/overview': reads.policy_overview, 'new-cars/dashboard': reads.new_car_dashboard,
                    'rights/overview': reads.rights_overview, 'reputation/overview': source_status}
        if path in overview:
            payload = await cached(path, overview[path], values.get('refresh') == '1')
            if path == 'reputation/overview': payload = dict(success=True,source='api',status=payload)
        elif path == 'policies': payload = await asyncio.to_thread(reads.policy_list, values)
        elif path == 'policies/snapshot': payload = await asyncio.to_thread(reads.policy_list,values,True)
        elif path == 'rights':
            if request.query_params.getlist('activity_type'): values['activity_types'] = request.query_params.getlist('activity_type')
            values.pop('activity_type', None)
            payload = await asyncio.to_thread(reads.rights_list, values)
        elif path in {'new-cars','new-cars/planned','new-cars/detail'}:
            payload = await asyncio.to_thread(reads.new_car_list,values,path.endswith('planned'),path.endswith('detail'))
        elif path in {'new-cars/snapshot','new-cars/planned/snapshot','new-cars/detail/snapshot'}:
            resource=path.removesuffix('/snapshot')
            payload=await asyncio.to_thread(reads.new_car_list,values,resource.endswith('planned'),resource.endswith('detail'),True)
        elif path == 'new-cars/sales': payload = await asyncio.to_thread(reads.new_car_sales,values)
        elif path == 'reputation/reviews': payload = dict(await asyncio.to_thread(search_source_reviews,SourceReviewInput(**values)),source='api')
        elif path in {'reputation/summary','reputation/tree','reputation/evidence'}: payload = await asyncio.to_thread(reads.reputation_read,path,values)
        else: return DataJSON(dict(success=False,error='未定义的业务资源'),status_code=404)
        return DataJSON(payload)
    except reads.VersionChanged:
        return DataJSON(dict(success=False,error='数据版本已变化，请重新查询'),status_code=409)
    except (ValueError,TypeError,KeyError):
        return DataJSON(dict(success=False,error='查询参数无效'),status_code=400)
    except Exception:
        return DataJSON(dict(success=False,error='数据服务暂不可用'),status_code=502)


class TokenAuth:
    def __init__(self,app): self.app=app
    async def __call__(self,scope,receive,send):
        token=os.getenv('MCP_API_TOKEN','')
        token_file=os.getenv('RIGHTS_MCP_TOKEN_FILE')
        if token_file: token=Path(token_file).read_text().strip()
        if scope['type']=='http':
            auth=dict(scope.get('headers',[])).get(b'authorization',b'')
            if not token or not secrets.compare_digest(auth,b'Bearer '+token.encode()):
                await DataJSON(dict(error='unauthorized'),status_code=401)(scope,receive,send); return
        await self.app(scope,receive,send)


api_routes=[Route('/api/v1/{resource:path}',dispatch,methods=['GET','POST'])]
app=TokenAuth(Starlette(routes=api_routes))

if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host=os.getenv('DATA_API_HOST','0.0.0.0'),port=int(os.getenv('DATA_API_PORT','8815')),access_log=False)
