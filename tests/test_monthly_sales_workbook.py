import tempfile,unittest
import sys
from pathlib import Path
from openpyxl import Workbook
from tools.monthly_sales_workbook import read_workbook
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'mcp'))
from market_data.monthly_sales_read import combine,model_candidates

class SalesTest(unittest.TestCase):
    def test_brand_prefix_overlap_without_fuzzy_model_matching(self):
        self.assertIn('上汽大通g10',model_candidates('大通G10','上汽大通'))
        self.assertIn('东风eπ007',model_candidates('eπ007','东风奕派',True))
        self.assertNotIn('s5',model_candidates('S5','另一品牌',True))
    def test_exact_quantity_aggregation_and_invalid_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'sales.xlsx';w=Workbook();s=w.active
            s.append(['年','月','车型','新能源类型','数量'])
            for r in [(2026,1,'A','纯电动',7),(2026,1,'A','纯电动',3),(2026,1,'A','插电式混合动力',20),(2026,2,718,'传统燃料',0)]:s.append(r)
            w.save(p);d=read_workbook(p)
            self.assertEqual((d['raw_rows'],d['records'],d['total_sales']),(4,3,30))
            self.assertEqual(next(r for r in d['rows'] if r['model']=='A' and r['energy_type']=='纯电动')['sales'],10)
            s.append([2026,2,'A','纯电动',None]);w.save(p)
            with self.assertRaises(ValueError):read_workbook(p)

    def test_revision_preserves_later_legacy_month_and_separates_energy(self):
        excel=[{'month':'2026-01-01','sales':10,'energy_type':'纯电动','import_batch':'new'},
               {'month':'2026-01-01','sales':20,'energy_type':'插电式混合动力','import_batch':'new'}]
        legacy=[{'month':'2026-01-01','sales':9,'import_batch':'old'},{'month':'2026-03-01','sales':5,'import_batch':'old'}]
        d=combine(excel,legacy,'纯电动',['纯电动'])
        self.assertEqual(d['total_sales'],15);self.assertEqual([r['month'] for r in d['items']],['2026-01-01','2026-03-01'])
        self.assertEqual(d['legacy_months_retained'],1);self.assertEqual(len(d['revisions']),1)
        self.assertEqual(combine(excel,legacy,'纯电动',['插电式混合动力'])['total_sales'],20)
        self.assertFalse(any(r['month']=='2026-02-01' for r in d['items']))
