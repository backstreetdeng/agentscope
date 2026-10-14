import asyncio
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'mcp'))
from market_data.cloud_rights import Search,where,present,Auth,HEADERS

class CloudRightsTests(unittest.TestCase):
    def test_stable_id_keeps_duplicate_source_ids_distinct(self):
        one=present({'id':1,'record_no':'duplicate'}); two=present({'id':2,'record_no':'duplicate'})
        self.assertNotEqual(one['记录编号'],two['记录编号'])
        self.assertEqual(one['原始记录编号'],two['原始记录编号'])
    def test_header_compatibility(self):
        self.assertEqual(len(HEADERS),21)
        self.assertTrue(set(HEADERS).issubset(present({'id':1})))
    def test_types_and_content_use_explicit_columns(self):
        row=present({'id':1,'cash_discount':'1000元','finance_policy':'0息'})
        self.assertEqual(row['当前活动类型（支持多选）'],['现金优惠','金融政策'])
        self.assertIn('1000元',row['活动内容'])
    def test_unknown_dates_not_claimed_active(self):
        self.assertIn('待确认',present({'id':1})['有效期完整性'])
    def test_any_and_all_are_explicit(self):
        a,_=where(Search(activity_types=['现金优惠','金融政策']))
        b,_=where(Search(activity_types=['现金优惠','金融政策'],activity_match='all'))
        self.assertIn(' OR ',a[0]); self.assertIn(' AND ',b[0])
    def test_sql_values_bound_not_interpolated(self):
        attack="' OR 1=1 --"
        parts,args=where(Search(brand=attack,exact_names=True))
        self.assertNotIn(attack,' '.join(parts)); self.assertEqual(args,[attack])
    def test_invalid_type_rejected(self):
        with self.assertRaises(ValueError): where(Search(activity_types=['未知']))
    def test_invalid_date_order_rejected(self):
        with self.assertRaises(ValueError): where(Search(start_date='2026-10-10',end_date='2026-10-09'))
    def test_date_filters_exclude_null_not_retain_as_match(self):
        parts,args=where(Search(start_date='2026-10-09'))
        self.assertEqual(parts,['monitor_date >= %s'])
    def test_auth_rejects_before_application(self):
        async def check():
            called=[];sent=[]
            async def app(*args):called.append(True)
            async def send(v):sent.append(v)
            with tempfile.TemporaryDirectory() as folder:
                token=Path(folder)/'token';token.write_text('a'*64)
                with patch.dict(os.environ,{'RIGHTS_MCP_TOKEN_FILE':str(token)}):auth=Auth(app)
                await auth({'type':'http','headers':[]},None,send)
            self.assertFalse(called);self.assertEqual(sent[0]['status'],401)
        asyncio.run(check())

if __name__=='__main__': unittest.main()
