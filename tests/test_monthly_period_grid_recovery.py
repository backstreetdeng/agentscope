import asyncio
import gzip
from email.message import Message
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock,MagicMock,patch

from tools.monthly_report_browser import MonthlyReportBrowserConnector
from tools.custom_tools import fetch_url_text
from utils.monthly_research_dag import entity_present


class PeriodRecoveryTests(IsolatedAsyncioTestCase):
    async def test_old_viewport_is_refreshed_before_cached_delay_is_reused(self):
        connector=MonthlyReportBrowserConnector();connector._direct_page=object()
        connector._ensure_direct_connected=AsyncMock(return_value=object())
        old='P2-1.1：乘用车月报-车型类别\n日期组合 (月)\n数量\n轿车\nSUV\n2026-08\n622835\n849107\n'
        cached={'report_month':'2026-09','cards':[{'code':'P2-1.1','text':old}],'generation_ready':True}
        grid={'complete':True,'month':'2026-09','headers':[],
              'cells':[{'row':21,'col':0,'text':'2026-09'},{'row':21,'col':1,'text':'658170'}]}
        with patch('scripts.capture_monthly_ppt_grids.capture',new=AsyncMock(return_value=grid)) as capture, \
             patch.object(connector,'_save_data_package'), \
             patch('tools.monthly_report_browser._page_card_codes',return_value=['P2-1.1']):
            result=await connector._refresh_cached_delays(cached,{'report_month':'2026-09'})
        capture.assert_awaited_once()
        self.assertEqual(result['delayed_cards'],[])
        self.assertEqual(result['card_validation']['P2-1.1']['status'],'valid')
        self.assertIn('2026-09',result['cards'][0]['text'])

    async def test_historical_package_is_not_replaced_by_newer_live_context(self):
        c=MonthlyReportBrowserConnector();c._direct_page=object()
        cached={'report_month':'2026-08'}
        self.assertIs(await c._refresh_cached_delays(cached,{'report_month':'2026-09'}),cached)


class SourceDecodeTests(TestCase):
    def test_gzip_official_page_is_readable_before_research_acceptance(self):
        headers=Message();headers['Content-Type']='text/html; charset=utf-8';headers['Content-Encoding']='gzip'
        response=MagicMock();response.headers=headers
        response.read.return_value=gzip.compress('<html><title>官方原文</title><body>当月活动有效期说明</body></html>'.encode())
        response.__enter__.return_value=response
        with patch('tools.custom_tools.urlopen',return_value=response):
            text=fetch_url_text('https://official.example/report',6000)
        self.assertIn('当月活动有效期说明',text)
        self.assertNotIn('\ufffd',text)

    def test_level_letter_does_not_match_brand_word(self):
        self.assertFalse(entity_present('A','{"brand":"ARCFOX"}'))
        self.assertTrue(entity_present('A','{"vehicle_level":"A"}'))
