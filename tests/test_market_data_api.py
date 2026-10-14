import asyncio
import base64
from datetime import date
from decimal import Decimal
import io
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, patch
import httpx
from openpyxl import load_workbook
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'mcp'))
from market_data import api_server,api_read_models
from integrations.market_data_api import api_base_url,get_all


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def request(self,path,token='test-token',method='GET',data=None):
        with patch.dict(os.environ,{'MCP_API_TOKEN':'test-token','RIGHTS_MCP_TOKEN_FILE':''}):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api_server.app),base_url='http://test') as client:
                return await client.request(method,path,headers={'Authorization':'Bearer '+token},json=data)

    async def test_auth_precedes_queries(self):
        with patch.object(api_read_models,'new_car_dashboard') as read:
            response=await self.request('/api/v1/new-cars/dashboard',token='wrong')
            self.assertEqual(response.status_code,401); read.assert_not_called()

    async def test_database_dates_decimals_serialize(self):
        with patch.object(api_read_models,'new_car_sales',return_value={'success':True,'items':[{'month':date(2026,9,1),'sales':Decimal('42')}]}):
            response=await self.request('/api/v1/new-cars/sales?model=A')
            self.assertEqual(response.status_code,200); self.assertEqual(response.json()['items'][0]['month'],'2026-09-01')

    async def test_invalid_page_and_version_conflict(self):
        self.assertEqual((await self.request('/api/v1/new-cars?limit=oops')).status_code,400)
        with patch.object(api_read_models,'new_car_list',side_effect=api_read_models.VersionChanged):
            self.assertEqual((await self.request('/api/v1/new-cars?data_version=old')).status_code,409)

    async def test_overview_coalesces_parallel_requests(self):
        api_server._cache.clear()
        with patch.object(api_read_models,'new_car_dashboard',return_value={'success':True,'stats':{}}) as read:
            await asyncio.gather(*[self.request('/api/v1/new-cars/dashboard') for _ in range(4)])
            self.assertEqual(read.call_count,1)

    async def test_complete_pagination_over_100_rows_and_change(self):
        pages=[dict(success=True,items=[{'id':i} for i in range(100)],total_count=125,data_version='v1',has_more=True,next_offset=100),dict(success=True,items=[{'id':i} for i in range(100,125)],total_count=125,data_version='v1',has_more=False,next_offset=None)]
        with patch('integrations.market_data_api.get_data',new=AsyncMock(side_effect=pages)) as read:
            payload=await get_all({},'new-cars',plugin_id='new-car')
            self.assertEqual(len(payload['items']),125)
            self.assertEqual(read.call_args.kwargs['params']['data_version'],'v1')
        pages[1]['data_version']='v2'
        with patch('integrations.market_data_api.get_data',new=AsyncMock(side_effect=pages)):
            with self.assertRaises(ValueError): await get_all({},'new-cars')

    def test_cloud_url_and_credential_not_routed_to_lan(self):
        with patch.dict(os.environ,{'MARKET_MCP_RIGHTS_URL':'http://127.0.0.1:18812/mcp','MARKET_MCP_RIGHTS_API_TOKEN':'cloud','MARKET_DATA_API_BASE_URL':'http://lan/api/v1'},clear=True):
            base,token=api_base_url({'mcp_plugins':{}},'rights')
            self.assertEqual(base,'http://127.0.0.1:18812/api/v1'); self.assertEqual(token,'cloud')

    def test_export_literal_cells_prevent_formula_injection(self):
        data=api_read_models.workbook([{'field':'=1+2'}],['field'],'test.xlsx')
        wb=load_workbook(io.BytesIO(base64.b64decode(data['file_base64'])))
        self.assertEqual(wb.active['A2'].data_type,'s')
        self.assertEqual(wb.active['A2'].value,'=1+2')

    async def test_snapshot_rejects_partial_and_duplicate_records(self):
        from integrations.market_data_api import get_snapshot
        for payload in [dict(items=[{'id':1}],total_count=2,has_more=True),dict(items=[{'id':1},{'id':1}],total_count=2,has_more=False)]:
            with patch('integrations.market_data_api.get_data',new=AsyncMock(return_value=payload)):
                with self.assertRaises(ValueError): await get_snapshot({},'new-cars')


if __name__=='__main__': unittest.main()
