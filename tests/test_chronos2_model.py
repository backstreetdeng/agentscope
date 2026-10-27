# -*- coding: utf-8 -*-
"""M3Chronos.predict 的边界单测与本地 CPU 离线有效输入回归（CHRONOS-001 T001）。

覆盖 TASK v1.1 §10.4：
- 非法输入（空/NaN/±Inf/二维/horizon 非法/分位数非法）在调用 pipeline 前以 ValueError 拒绝；
- 非法输出（错误形状/NaN/Inf/分位数交叉）以 RuntimeError 拒绝；
- 有效输入：默认三分位返回键及各 (6,) 数组，与 R1 基线浮点容差一致；
- 原能力保留：本地加载与进程内缓存复用。

mock 用例不加载真实模型（object.__new__ 绕过 __init__），仅真实回归类加载一次本地权重。
"""
import os
import sys
import math
import unittest
from unittest import mock

import numpy as np

_FE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                  "forecast-engine")
if _FE not in sys.path:
    sys.path.insert(0, _FE)

from models.m3_chronos import M3Chronos  # noqa: E402


def _mock_m3():
    """构造不加载真实模型的 M3Chronos，pipe 为 MagicMock。"""
    m3 = object.__new__(M3Chronos)
    m3.pipe = mock.MagicMock()
    m3.model_name = "mock"
    return m3


VALID_HIST = [100 * (1 + 0.012 * i) + 18 * math.sin(2 * math.pi * i / 12)
              for i in range(36)]
DEFAULT_Q = (0.1, 0.5, 0.9)


class TestInvalidInputs(unittest.TestCase):
    """非法输入必须在调用 pipeline 前以 ValueError 拒绝。"""

    def setUp(self):
        self.m3 = _mock_m3()

    def _assert_reject(self, hist, horizon, quantiles):
        with self.assertRaises(ValueError):
            self.m3.predict(hist, horizon, quantiles)
        self.m3.pipe.predict_quantiles.assert_not_called()

    def test_empty_history(self):
        self._assert_reject([], 6, DEFAULT_Q)

    def test_nan_history(self):
        self._assert_reject([float("nan")] * 36, 6, DEFAULT_Q)

    def test_pos_inf_history(self):
        self._assert_reject([float("inf")] * 36, 6, DEFAULT_Q)

    def test_neg_inf_history(self):
        self._assert_reject([float("-inf")] * 36, 6, DEFAULT_Q)

    def test_2d_history(self):
        self._assert_reject([[1.0, 2.0], [3.0, 4.0]], 6, DEFAULT_Q)

    def test_history_not_convertible_to_number(self):
        self._assert_reject(object(), 6, DEFAULT_Q)

    def test_float32_overflow_history(self):
        for value in (1e100, -1e100):
            with self.subTest(value=value):
                self._assert_reject([value] * 36, 6, DEFAULT_Q)

    def test_horizon_zero(self):
        self._assert_reject(VALID_HIST, 0, DEFAULT_Q)

    def test_horizon_negative(self):
        self._assert_reject(VALID_HIST, -1, DEFAULT_Q)

    def test_horizon_bool(self):
        self._assert_reject(VALID_HIST, True, DEFAULT_Q)

    def test_horizon_non_integer(self):
        self._assert_reject(VALID_HIST, 6.5, DEFAULT_Q)

    def test_quantiles_empty(self):
        self._assert_reject(VALID_HIST, 6, ())

    def test_quantiles_nan(self):
        self._assert_reject(VALID_HIST, 6, (0.1, float("nan"), 0.9))

    def test_quantiles_inf(self):
        self._assert_reject(VALID_HIST, 6, (0.1, float("inf"), 0.9))

    def test_quantiles_out_of_range(self):
        self._assert_reject(VALID_HIST, 6, (0.0, 0.5, 0.9))
        self._assert_reject(VALID_HIST, 6, (0.1, 0.5, 1.0))

    def test_quantiles_duplicate(self):
        self._assert_reject(VALID_HIST, 6, (0.5, 0.5, 0.9))

    def test_quantiles_unordered(self):
        self._assert_reject(VALID_HIST, 6, (0.9, 0.5, 0.1))

    def test_quantiles_not_convertible_to_number(self):
        self._assert_reject(VALID_HIST, 6, object())


class TestInvalidOutputs(unittest.TestCase):
    """模型返回无效输出必须以 RuntimeError 失败，不伪成功。"""

    def setUp(self):
        self.m3 = _mock_m3()

    def _assert_output_reject(self, tensor):
        self.m3.pipe.predict_quantiles.return_value = ([tensor], None)
        with self.assertRaises(RuntimeError):
            self.m3.predict(VALID_HIST, 6, DEFAULT_Q)

    def test_wrong_shape(self):
        import torch
        self._assert_output_reject(torch.zeros(1, 6, 2))  # 期望 (1,6,3)

    def test_nan_output(self):
        import torch
        self._assert_output_reject(torch.full((1, 6, 3), float("nan")))

    def test_inf_output(self):
        import torch
        self._assert_output_reject(torch.full((1, 6, 3), float("inf")))

    def test_crossing_quantiles(self):
        import torch
        t = torch.zeros(1, 6, 3)
        t[:, :, 0] = 0.9  # P10 位置 > P50，交叉
        t[:, :, 1] = 0.5
        t[:, :, 2] = 0.1
        self._assert_output_reject(t)


class TestValidOutputMock(unittest.TestCase):
    """有效输出在 mock 下应正常返回 dict，输出校验不误伤。"""

    def test_valid_mock_returns_dict(self):
        import torch
        m3 = _mock_m3()
        t = torch.zeros(1, 6, 3)
        t[:, :, 0] = 0.1
        t[:, :, 1] = 0.5
        t[:, :, 2] = 0.9
        m3.pipe.predict_quantiles.return_value = ([t], None)
        out = m3.predict(VALID_HIST, 6, DEFAULT_Q)
        self.assertEqual(set(out.keys()), {0.1, 0.5, 0.9})
        for k in DEFAULT_Q:
            self.assertEqual(out[k].shape, (6,))


class TestRealRegression(unittest.TestCase):
    """本地 CPU 离线有效输入回归 + 缓存复用。加载真实本地权重一次。"""

    @classmethod
    def setUpClass(cls):
        cls.m3 = M3Chronos()  # 复用 _models/amazon__chronos-2

    def test_valid_inference_matches_baseline(self):
        out = self.m3.predict(VALID_HIST, 6)
        self.assertEqual(set(out.keys()), {0.1, 0.5, 0.9})
        p10, p50, p90 = out[0.1], out[0.5], out[0.9]
        for a in (p10, p50, p90):
            self.assertEqual(a.shape, (6,))
            self.assertTrue(np.isfinite(a).all())
        self.assertTrue((p10 <= p50).all() and (p50 <= p90).all())

        base_p10 = np.array([139.6339, 149.6982, 157.5976,
                             161.6514, 159.5545, 153.7747])
        base_p50 = np.array([142.1882, 153.4277, 162.3583,
                             166.3419, 166.0435, 159.8734])
        base_p90 = np.array([144.2358, 155.9022, 165.6247,
                             171.0334, 170.3235, 164.5274])
        np.testing.assert_allclose(p10, base_p10, rtol=1e-3, atol=0.05)
        np.testing.assert_allclose(p50, base_p50, rtol=1e-3, atol=0.05)
        np.testing.assert_allclose(p90, base_p90, rtol=1e-3, atol=0.05)

    def test_cache_reuse(self):
        m3b = M3Chronos()
        self.assertIs(self.m3.pipe, m3b.pipe)


if __name__ == "__main__":
    unittest.main()
