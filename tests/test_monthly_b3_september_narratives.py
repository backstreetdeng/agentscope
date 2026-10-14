"""Replay September B3 facts locally, with no browser or model calls."""
import json
import unittest
from copy import deepcopy
from pathlib import Path

from utils.monthly_report_narrative import (
    _card_lookup, _normalize_batch, _page_payload, _validate_batch_facts,
    load_page_card_map,
)

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'outputs/monthly-report-data/data-source-package-20261013-011831.json'


@unittest.skipUnless(PACKAGE.is_file(), 'September captured package unavailable')
class SeptemberB3Regression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assets = ROOT / 'skills/market-analysis-skill/passenger-car-monthly-report/assets'
        package = json.loads(PACKAGE.read_text(encoding='utf-8'))
        payload = _page_payload((13, 14, 15), load_page_card_map(assets / '乘用车月报-数据源映射指标.xlsx'),
                                _card_lookup(package), {}, '2026-09')
        cls.payload = {p['slide']: p for p in payload}

    def validate(self, page, headline=None, payload=None):
        p = deepcopy(payload or self.payload[page])
        draft = p['fact_grounded_draft']
        if headline:
            draft['headline'] = headline
        batch = _normalize_batch({'slides': [draft], 'evidence': []}, 'B3', (page,), '2026-09')
        _validate_batch_facts(batch, [p])

    def test_all_three_local_drafts_pass_fact_and_layout_gates(self):
        for page in (13, 14, 15):
            with self.subTest(page=page):
                self.validate(page)

    def test_named_pair_can_use_single_month_wording(self):
        self.validate(13, '10-15万与10万以下单月同比均下降')

    def test_positive_or_uncited_member_cannot_pass_pair_direction_gate(self):
        p = deepcopy(self.payload[13])
        for r in p['business_facts']:
            if r['entity'] == '10万以下' and r['scope'] == 'single_month' and r['period'] == '2026-09':
                r['yoy_pct'] = 1.0
        with self.assertRaisesRegex(ValueError, '比较集合未支持'):
            self.validate(13, '10-15万与10万以下单月同比均下降', p)
        with self.assertRaisesRegex(ValueError, '比较集合未支持'):
            self.validate(13, '10-15万与35万以上单月同比均下降')

    def test_wrong_strongest_decline_still_fails(self):
        with self.assertRaisesRegex(ValueError, '比较集合未支持'):
            self.validate(14, '中部收缩最深、西部份额逆势提升')

    def test_overlong_title_still_fails(self):
        with self.assertRaisesRegex(ValueError, '单行预算'):
            self.validate(15, '新一线与二线单月同比均下降，环比回升叠加累计承压，区域结构出现较大变化并且需要关注后续走势')
