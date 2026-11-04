import unittest
from integrations.chronos2_forecast import next_month
from integrations.sarimax_exogenous import prepare


def fixture(lag=0):
    months=[next_month('2019-12',i+1) for i in range(60)]
    history=[(ym,1000+i) for i,ym in enumerate(months)]
    records=[dict(period=ym,available_at=ym+'-01',value=10+i,
                  verified=True,vintage_verified=True) for i,ym in enumerate(months)]
    return history,[dict(name='oil',lag=lag,unit='unit',records=records)]


class ExogenousAsOfTests(unittest.TestCase):
    def test_freeze_uses_last_known_not_future_real_or_late_revision(self):
        history,variables=fixture()
        origin=history[-1][0]
        variables[0]['records'].append(dict(period=origin,available_at=next_month(origin)+'-01',
                                            value=9999,verified=True,vintage_verified=True))
        variables[0]['records'].append(dict(period=next_month(origin),available_at=next_month(origin)+'-01',
                                            value=8888,verified=True,vintage_verified=True))
        result=prepare(history,variables,3,as_of_date='2024-12-31')
        self.assertEqual(result['future_features'],[[69.0],[69.0],[69.0]])
        self.assertEqual(result['assumptions']['oil']['period'],origin)

    def test_lag_uses_observed_origin_then_frozen_future(self):
        history,variables=fixture(lag=1)
        result=prepare(history,variables,2,as_of_date='2024-12-31')
        self.assertEqual(result['discarded_months'],1)
        self.assertEqual(result['future_features'],[[69.0],[69.0]])
        self.assertEqual(result['future_details'][0]['kind'],'已核验历史')

    def test_unverified_history_is_not_a_zero(self):
        history,variables=fixture()
        variables[0]['records'][-1]['vintage_verified']=False
        with self.assertRaisesRegex(ValueError,'不足'):
            prepare(history,variables,3,as_of_date='2024-12-31')

    def test_duplicate_same_date_conflict_rejected(self):
        history,variables=fixture()
        bad=dict(variables[0]['records'][-1],value=1234)
        variables[0]['records'].append(bad)
        with self.assertRaisesRegex(ValueError,'冲突'):
            prepare(history,variables,3,as_of_date='2024-12-31')

    def test_nonfinite_and_wrong_horizon_rejected(self):
        history,variables=fixture()
        variables[0]['records'][0]['value']=float('nan')
        with self.assertRaises(ValueError): prepare(history,variables,3,as_of_date='2024-12-31')
        history,variables=fixture()
        with self.assertRaises(ValueError): prepare(history,variables,13,as_of_date='2024-12-31')

    def test_as_of_date_must_be_explicit_and_after_origin(self):
        history,variables=fixture()
        with self.assertRaises(TypeError): prepare(history,variables,3)
        with self.assertRaises(ValueError): prepare(history,variables,3,as_of_date='2024-12-01')


if __name__=='__main__': unittest.main()
