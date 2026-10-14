import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'mcp'))
from integrations.reputation_live import summary_payload, tree_payload, decode
from market_data.reputation_sources import SourceReviewInput, search_source_reviews


class ReputationLiveTests(unittest.TestCase):
    def test_full_scan_without_tags_is_processed_not_missing(self):
        data=summary_payload('A',{'groups':{},'analysis_current':True,'analysis_source_version':'v','analysis_method':'explicit_evidence_rules'},
            {'total_count':3,'sources':[],'items':[],'data_version':'v'})
        self.assertTrue(data['available'])
        self.assertTrue(data['analysis_processed'])
        self.assertFalse(data['analysis_available'])

    def test_changed_raw_revision_is_not_current(self):
        data=summary_payload('A',{'groups':{},'analysis_current':True,'analysis_source_version':'old'},
            {'total_count':3,'sources':[],'items':[],'data_version':'new'})
        self.assertFalse(data['analysis_current'])

    def test_raw_samples_without_analysis_not_reported_missing(self):
        raw={'total_count':49,'sources':[{'source':'autohome','review_count':49}], 'items':[], 'data_version':'v'}
        data=summary_payload('星光730新能源',{'groups':{'positive':[],'negative':[]}},raw)
        self.assertTrue(data['available'])
        self.assertFalse(data['analysis_available'])
        self.assertEqual(data['raw_total'],49)
        self.assertEqual(data['total_reviews'],0)

    def test_analysis_denominator_not_latest_raw_total(self):
        row={'rank':1,'primary_label':'空间','tertiary_labels':[],'mention_count':18,'mention_share':'0.4091',
             'source_mentions':{},'autohome_count':7,'dongchedi_count':37,'import_batch':'20260928'}
        data=summary_payload('理想i8',{'groups':{'positive':[row]}},
             {'total_count':48,'sources':[{'source':'autohome','review_count':7},{'source':'dongchedi','review_count':41}], 'items':[], 'data_version':'v'})
        self.assertEqual((data['total_reviews'],data['raw_total']),(44,48))
        self.assertEqual(data['groups']['positive'][0]['share'],.4091)

    def test_genuine_empty_is_separate_from_failure(self):
        data=summary_payload('不存在',{'groups':{}},{'total_count':0,'sources':[],'items':[],'data_version':'v'})
        self.assertFalse(data['available'])
        with self.assertRaises(ValueError): decode(SimpleNamespace(isError=True,content=[]))

    def test_tree_does_not_sum_overlapping_leaf_reviews(self):
        data=tree_payload('A',{'items':[{'direction':'positive','primary_label':'空间','secondary_label':'座椅',
            'tertiary_label':'舒适','review_count':4,'taxonomy_code':'x','is_custom':False}]})
        self.assertIsNone(data['directions']['positive'][0]['count'])
        self.assertEqual(data['directions']['positive'][0]['children'][0]['children'][0]['count'],4)

    def test_source_and_paging_constraints(self):
        for kwargs in [{'source':'unknown'},{'limit':101},{'offset':-1}]:
            with self.assertRaises(ValueError): SourceReviewInput(**kwargs)

    def test_raw_query_exact_match_bound_parameters_and_database_paging(self):
        calls=[]
        class Cursor:
            description=[]
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def execute(self,*a):calls.append(a)
        class Conn:
            def set_session(self,**kwargs):self.options=kwargs
            def cursor(self):return Cursor()
            def rollback(self):pass
            def close(self):pass
        with patch('market_data.reputation_sources.pg_connect',return_value=Conn()),\
             patch('market_data.reputation_sources._revision',return_value='v'),\
             patch('market_data.reputation_sources._dicts',side_effect=[[{'source':'autohome','review_count':30}],[]]):
            data=search_source_reviews(SourceReviewInput(model="x' OR TRUE",source='autohome',limit=20,offset=20))
        self.assertEqual(data['total_count'],30)
        self.assertIn('LIMIT %s OFFSET %s',calls[-1][0])
        self.assertNotIn("x' OR TRUE",calls[-1][0])
        self.assertEqual(calls[-1][1][-2:],(20,20))


if __name__=='__main__':unittest.main()
