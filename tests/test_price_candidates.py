import unittest
from integrations.price_candidates import monitor_candidate, historical_candidate


class CandidateTests(unittest.TestCase):
    def test_new_monitor_schema_keeps_three_dates_separate(self):
        row={'现金优惠':'1000元','监测目标日期':'2026-10-31',
             '文章发布日期':'2026-11-01','采集日期':'2026-11-02'}
        result=monitor_candidate(row,sheet='s',row=2,source='source.xlsx')
        self.assertEqual(result['monitor_target_at'],'2026-10-31')
        self.assertEqual(result['article_published_at'],'2026-11-01')
        self.assertEqual(result['captured_at'],'2026-11-02')
        self.assertIsNone(result['observed_or_published'])

    def test_cash_and_conditional_benefits_stay_separate(self):
        row={'现金优惠':'现金优惠或有条件','置换及增购补贴':'需要旧车',
             '金融政策':'贷款条件','原指导价':'区间描述'}
        result=monitor_candidate(row,sheet='s',row=2,source='source.xlsx')
        self.assertEqual(result['fields']['cash_discount'],'现金优惠或有条件')
        self.assertEqual(result['fields']['replacement'],'需要旧车')
        self.assertEqual(result['fields']['finance'],'贷款条件')
        self.assertIsNone(result['fields']['new_price'])
        self.assertIn('未核验',result['review'])

    def test_blank_is_unknown_not_zero(self):
        self.assertIsNone(monitor_candidate({},sheet='s',row=2,source='x'))
        row=historical_candidate({'降幅（万元）':'优惠描述'},sheet='s',row=4,source='x')
        self.assertIsNone(row['date_raw'])
        self.assertIn('未分类',row['review'])


if __name__ == '__main__': unittest.main()
