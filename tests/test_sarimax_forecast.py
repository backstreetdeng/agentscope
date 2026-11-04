"""SARIMAX chronological and comparison contracts; no external requests."""
import copy
import unittest

from integrations.chronos2_forecast import next_month
from integrations.sarimax_forecast import calculate, compare_backtests, MODEL_NAME, validate


class Workbook:
    source_hash = 'test-hash'
    def __init__(self):
        self.values = [(next_month('2010-12', i+1), 1000 + i) for i in range(100)]
    def series(self, province, energy, cutoff=None):
        return [row for row in self.values if cutoff is None or row[0] <= cutoff]


class SarimaxTests(unittest.TestCase):
    def setUp(self):
        self.wb = Workbook()
        self.base = dict(operation='backtest', province='广东', energy='插电式混合动力',
                         cutoff=None, horizon=6)

    def test_rolling_training_never_contains_future(self):
        lengths = []
        def predictor(history, horizon):
            lengths.append(len(history))
            return [dict(p10=10.,p50=20.,p90=30.,lower_clipped=False) for _ in range(horizon)]
        result = calculate(self.wb, self.base, predictor)
        self.assertEqual(lengths, list(range(77,89)))
        self.assertEqual(len(result['backtest']['records']),144)
        first = result['backtest']['records'][0]
        self.assertEqual(first['origin'],self.wb.values[76][0])
        self.assertEqual(first['month'],self.wb.values[77][0])
        self.assertEqual(first['actual'],self.wb.values[77][1])
        self.assertEqual(first['seasonal_naive'],self.wb.values[65][1])
        self.assertEqual(set(result['backtest']['by_horizon']),{'1','3','6','12'})

    def test_future_exogenous_cannot_be_silently_ignored(self):
        with self.assertRaises(ValueError):
            validate(dict(self.base, exog={'future':123}))

    def test_forecast_starts_after_cutoff(self):
        def predictor(history, horizon):
            return [dict(p10=10.,p50=20.,p90=30.,lower_clipped=False) for _ in range(horizon)]
        result = calculate(self.wb, dict(self.base,operation='forecast',horizon=3), predictor)
        self.assertEqual(result['forecast'][0]['month'],next_month(result['data_cutoff']))
        self.assertEqual(len(result['forecast']),3)
        self.assertIn('无外部变量',result['scenario'])

    def jobs(self):
        def predictor(history, horizon):
            return [dict(p10=10.,p50=20.,p90=30.,lower_clipped=False) for _ in range(horizon)]
        s = calculate(self.wb,self.base,predictor)
        c = copy.deepcopy(s); c['model']='amazon/chronos-2'
        return ({'status':'completed','operation':'backtest','data':c},
                {'status':'completed','operation':'backtest','data':s})

    def test_comparison_requires_identical_origins_and_actuals(self):
        c,s=self.jobs()
        result=compare_backtests(c,s)
        self.assertEqual([r['horizon'] for r in result['rows']],[1,3,6,12])
        self.assertTrue(all(r['observations']==12 for r in result['rows']))
        for mutation in ('hash','actual','origin','model','incomplete'):
            changed=copy.deepcopy(s)
            if mutation=='hash': changed['data']['source_sha256']='other'
            if mutation=='actual': changed['data']['backtest']['records'][0]['actual']+=1
            if mutation=='origin': changed['data']['backtest']['records'][0]['origin']='2000-01'
            if mutation=='model': changed['data']['model']='other'
            if mutation=='incomplete': changed['data']['backtest']['records'].pop()
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                compare_backtests(c,changed)

    def test_short_history_fails(self):
        self.wb.values = self.wb.values[:60]
        with self.assertRaises(ValueError): calculate(self.wb,self.base,lambda *_:[])


if __name__ == '__main__': unittest.main()
