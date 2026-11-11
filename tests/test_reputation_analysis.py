import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from maintenance.reputation_analysis import polarity, analyze_review, aggregate, compile_patterns


class ReputationAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.taxonomy={'整体造型':{'code':'L1','l1':'外观设计','l2':'造型'},'后备箱容量':{'code':'L2','l1':'空间','l2':'装载'}}
        self.patterns=compile_patterns({'整体造型':['外观'],'后备箱容量':['后备箱']})

    def review(self,text):
        return {'model':'车型A','source':'autohome','review_key':'1','review_text':text}

    def test_clear_praise_and_complaint(self):
        rows=analyze_review(self.review('外观很好看，后备箱太小'),self.taxonomy,self.patterns)
        self.assertEqual({(r['tertiary_label'],r['direction']) for r in rows},{('整体造型','positive'),('后备箱容量','negative')})
        self.assertTrue(all(r['excerpt'] in '外观很好看，后备箱太小' for r in rows))

    def test_neutral_or_rating_alone_not_tagged(self):
        for text in ['外观。后备箱500升','总评分4.9，外观','今年5月购车','']:
            self.assertEqual(analyze_review(self.review(text),self.taxonomy,self.patterns),[])

    def test_question_speculation_not_tagged(self):
        for text in ['外观好看吗？','听说外观不好看','希望后备箱更宽敞','如果后备箱太小']:
            self.assertEqual(analyze_review(self.review(text),self.taxonomy,self.patterns),[])

    def test_negative_positive_substring_not_counted_twice(self):
        self.assertEqual(polarity('外观不满意'),'negative')
        self.assertEqual(polarity('后备箱不够用'),'negative')
        self.assertEqual(polarity('没有异响'),'positive')
        self.assertEqual(polarity('并不舒服'),'negative')
        self.assertIsNone(polarity('外观很好看但是很差'))

    def test_explicit_other_model_is_not_owner_evidence(self):
        import re
        self.assertEqual(analyze_review(self.review('车型B外观很好看'),self.taxonomy,self.patterns,re.compile('车型A|车型B')),[])

    def test_cross_source_same_key_counts_twice_and_same_source_once(self):
        rows=[{'model':'车型A','source':'autohome'},{'model':'车型A','source':'dongchedi'}]
        tags=[{'model':'车型A','direction':'positive','source':source,'review_key':'same','primary_label':'外观设计','tertiary_label':'整体造型'} for source in ['autohome','dongchedi']]
        summaries,_=aggregate(rows,tags+tags,self.taxonomy,'b','v')
        self.assertEqual(summaries[0]['mention_count'],2)
        self.assertEqual(summaries[0]['mention_share'],1)

    def test_top_five_not_padded(self):
        summary,_=aggregate([{'model':'A','source':'autohome'}],[],self.taxonomy,'b','v')
        self.assertEqual(summary,[])

    def test_absence_of_problem_not_negative(self):
        self.assertIsNone(polarity('坐在车里几乎感觉不到太大颠簸'))
        self.assertIsNone(polarity('后备箱很大'))
        self.assertIsNone(polarity('车内用料环保异味小'))
        self.assertIsNone(polarity('坐车再也不会觉得颠簸难受'))
        self.assertIsNone(polarity('颠簸路段车身也没有多余的晃动'))
        self.assertIsNone(polarity('有车友说后悔没加钱'))
        self.assertIsNone(polarity('差点忘记还有颜值没说'))
        self.assertEqual(polarity('胎噪抑制优秀'),'positive')
        self.assertEqual(polarity('坑洼路面颠簸过滤得很到位'),'positive')

    def test_topic_not_borrowed_from_unrelated_opinion(self):
        from maintenance.reputation_analysis import relevant
        self.assertFalse(relevant('材质触感',{'l1':'内饰设计与做工'},'车漆的质感很好'))
        self.assertFalse(relevant('整体可靠性感受',{'l1':'总体评价'},'交接车辆都很省心'))
        self.assertFalse(relevant('保养费用',{'l1':'用车成本'},'保养更省心'))
        self.assertIsNone(polarity('动力在不在乎油耗的情况下还是够用'))

    def test_unpunctuated_aspects_do_not_share_wrong_polarity(self):
        from maintenance.reputation_analysis import topic_clauses
        self.assertEqual(list(topic_clauses('动力略有不足油耗还行')),['动力略有不足','油耗还行'])
        self.assertIsNone(polarity('外观好吗？'))


    def test_alias_layer_extends_existing_l3_without_new_label(self):
        patterns=compile_patterns({'座椅软硬与支撑':['座椅']},{'座椅软硬与支撑':['靠背太直','坐垫偏短']})
        rows=analyze_review(self.review('后排靠背太直不舒服'),{'座椅软硬与支撑':{'code':'L1','l1':'乘坐舒适性','l2':'座椅体验'}},patterns)
        self.assertEqual({(r['tertiary_label'],r['direction']) for r in rows},{('座椅软硬与支撑','negative')})

    def test_alias_layer_survives_strict_overrides(self):
        patterns=compile_patterns({'配置价值':['配置丰富']},{'配置价值':['减配','配置缺失']})
        rows=analyze_review(self.review('配置缺失很遗憾'),{'配置价值':{'code':'L2','l1':'价格与购买价值','l2':'购买价值'}},patterns)
        self.assertEqual({(r['tertiary_label'],r['direction']) for r in rows},{('配置价值','negative')})

    def test_alias_to_unknown_l3_is_rejected(self):
        with self.assertRaises(ValueError):
            compile_patterns({'整体造型':['外观']},{'不存在的点':['随便']})

    def test_custom_l3_is_marked_and_gated(self):
        taxonomy={'车身尺寸与灵活性':{'code':'L3','l1':'动力与操控','l2':'驾驶控制','custom':True}}
        patterns=compile_patterns({'车身尺寸与灵活性':['车身太宽','停车费劲']})
        rows=analyze_review(self.review('车身太宽，停车费劲'),taxonomy,patterns)
        self.assertEqual({(r['tertiary_label'],r['direction'],r['is_custom']) for r in rows},
                         {('车身尺寸与灵活性','negative',True)})
        self.assertEqual(analyze_review(self.review('车身太宽'),taxonomy,patterns),[])


