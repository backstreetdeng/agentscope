"""Numeric regression of fixed log transform; tests need isolated stats deps."""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runtime'/'sarimax-deps'))
from integrations.oil_log_model import fit_log


class LogModelTests(unittest.TestCase):
    def test_mean_is_bias_corrected_and_not_mislabelled_median(self):
        pred=SimpleNamespace(predicted_mean=np.array([4.]),var_pred_mean=np.array([.04]),
            conf_int=lambda alpha:np.array([[3.7,4.3]]))
        fitted=SimpleNamespace(mle_retvals={'converged':True},params=[.1],get_forecast=lambda **kw:pred)
        with patch('statsmodels.tsa.statespace.sarimax.SARIMAX') as cls:
            cls.return_value.fit.return_value=fitted
            result=fit_log(list(range(100,160)),1)
        self.assertAlmostEqual(result['forecast'][0]['mean'],np.expm1(4.02))
        self.assertAlmostEqual(result['forecast'][0]['lower'],np.expm1(3.7))
        self.assertTrue(cls.call_args.kwargs['enforce_invertibility'])

    def test_no_convergence_is_not_success_after_fallback(self):
        with patch('statsmodels.tsa.statespace.sarimax.SARIMAX') as cls:
            cls.return_value.fit.return_value.mle_retvals={'converged':False}
            with self.assertRaisesRegex(ValueError,'未收敛'):fit_log(list(range(100,160)),1)
            self.assertEqual(cls.return_value.fit.call_count,2)

    def test_invalid_input_and_feature_shapes_rejected(self):
        for y in ([1]*60,[1]*59+[float('nan')],[-1]*60):
            with self.assertRaises(ValueError):fit_log(y,1)
        with self.assertRaises(ValueError):fit_log(list(range(60)),1,[[1]]*59,[[1]])

    def test_actual_synthetic_decline_fits_without_negative_point_clipping(self):
        y=[10000*np.exp(-.005*i+.15*np.sin(2*np.pi*i/12)) for i in range(96)]
        result=fit_log(y,12)
        self.assertTrue(result['converged'])
        self.assertEqual(len(result['forecast']),12)
        self.assertTrue(all(0<r['mean']<20000 and r['lower']<=r['mean']<=r['upper'] for r in result['forecast']))


if __name__=='__main__':unittest.main()
