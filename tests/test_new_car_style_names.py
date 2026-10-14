import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ops.publish_new_car_style_names import plan,base

class NameEnrichmentTests(unittest.TestCase):
    def test_exact_id_only_and_source_extra_not_inserted(self):
        changes,conflicts,missing,extra=plan([{'model_style_id':1},{'model_style_id':2}],{'names':[{'id':1,'name':'真实款型'},{'id':3,'name':'源表新增款型'}]})
        self.assertEqual(changes,[(1,'真实款型')]);self.assertEqual(missing,[2]);self.assertEqual(extra,[3]);self.assertEqual(conflicts,[])
    def test_same_input_no_updates(self):
        self.assertEqual(plan([{'model_style_id':1,'style_name':'真实款型'}],{'names':[{'id':1,'name':'真实款型'}]})[0],[])
    def test_changed_existing_name_not_overwritten(self):
        changes,conflicts,_,_=plan([{'model_style_id':1,'style_name':'旧名称'}],{'names':[{'id':1,'name':'新名称'}]})
        self.assertEqual(changes,[]);self.assertEqual(len(conflicts),1)
    def test_preservation_excludes_only_new_name(self):
        self.assertEqual(base([{'model_style_id':1,'model':'A','style_name':'版本名'}]),[{'model_style_id':1,'model':'A'}])
