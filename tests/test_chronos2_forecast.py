"""Forecast/backtest protocol: deterministic model stub, no network or weights."""
import unittest
from integrations.chronos2_forecast import calculate, metrics, next_month, validate


class FakeData:
    source_hash = 'snapshot-test'
    def series(self, province, energy, cutoff):
        months = [(next_month('2021-01', i), float(i + 1)) for i in range(50)]
        return [row for row in months if not cutoff or row[0] <= cutoff]


class FakePredictor:
    def __init__(self): self.histories = []
    def predict(self, values, horizon):
        self.histories.append(list(values))
        return {0.1: [values[-1]]*horizon, 0.5: [values[-1]+1]*horizon, 0.9: [values[-1]+2]*horizon}


class ChronosProtocolTests(unittest.TestCase):
    def test_forecast_uses_cutoff_and_follows_calendar(self):
        predictor = FakePredictor()
        result = calculate(FakeData(), dict(province='甲', energy='纯电动', operation='forecast',
                                            cutoff='2024-12', horizon=2), predictor)
        self.assertEqual(result['data_cutoff'], '2024-12')
        self.assertEqual([r['month'] for r in result['forecast']], ['2025-01', '2025-02'])
        self.assertEqual(len(predictor.histories[0]), 48)

    def test_backtest_never_uses_future_values(self):
        predictor = FakePredictor()
        result = calculate(FakeData(), dict(province='甲', energy='纯电动', operation='backtest'), predictor)
        backtest = result['backtest']
        self.assertEqual((backtest['origins'], backtest['horizon'], backtest['observations']), (12, 12, 144))
        self.assertEqual(set(backtest['by_horizon']), {'1', '3', '6', '12'})
        self.assertEqual(len(predictor.histories), 24)
        for n, hist in enumerate(predictor.histories[:12]):
            records = backtest['records'][n*12:(n+1)*12]
            self.assertEqual(records[0]['actual'], hist[-1]+1)
            self.assertEqual(records[0]['origin'], next_month('2021-01', len(hist)-1))
            self.assertEqual(records[-1]['seasonal_naive'], hist[-1])
        self.assertEqual(backtest['reference_1_6']['observations'], 72)
        self.assertEqual(backtest['reference_1_6_records'][-1]['month'], result['data_cutoff'])
        for n, hist in enumerate(predictor.histories[12:]):
            records = backtest['reference_1_6_records'][n*6:(n+1)*6]
            self.assertEqual(records[0]['actual'], hist[-1]+1)

    def test_reject_bad_horizon(self):
        for n in (0, 25, True, '6'):
            with self.assertRaises(ValueError): validate(dict(operation='forecast', province='甲', energy='纯电动', horizon=n))

    def test_zero_actual_metric_is_explicit(self):
        records = [dict(actual=0, p10=0, p50=2, p90=3, seasonal_naive=1),
                   dict(actual=4, p10=3, p50=5, p90=6, seasonal_naive=2)]
        result = metrics(records)
        self.assertEqual((result['mape_eligible'], result['zero_actual_excluded']), (1, 1))
        self.assertEqual(result['mae'], 1.5)
        self.assertEqual(result['wape_pct'], 75.0)
        self.assertEqual(result['seasonal_naive_wape_pct'], 75.0)
        self.assertEqual(result['interval_coverage_pct'], 100.0)

    def test_reject_other_models(self):
        with self.assertRaises(ValueError):
            validate(dict(operation='forecast', province='甲', energy='纯电动', model='m2'))


if __name__ == '__main__': unittest.main()
