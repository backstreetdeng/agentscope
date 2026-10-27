# -*- coding: utf-8 -*-
"""M2 主力：全局 LightGBM 分位数回归（P10/P50/P90），递归多步预测。
全局模型：bev/phev/hev/ice/total 各自训练，特征含全部序列的滞后（跨序列信息）。
"""
import lightgbm as lgb
import numpy as np
import pandas as pd

from features.build_features import COLS, build_training, feature_row, ym_index

QUANTILES = (0.1, 0.5, 0.9)


class M2Quantile:
    def __init__(self):
        self.models = {}
        self.t0 = None
        self.columns = None
        self.band = {}

    def fit(self, df):
        X, ys = build_training(df)
        self.t0 = ym_index(df.index[0])
        self.columns = list(X.columns)
        self._calibrate(df)
        for col in COLS:
            for q in QUANTILES:
                m = lgb.LGBMRegressor(
                    objective="quantile", alpha=q, n_estimators=250,
                    learning_rate=0.05, num_leaves=7, min_child_samples=8,
                    subsample=0.9, colsample_bytree=0.9, random_state=42,
                    verbose=-1)
                m.fit(X, ys[col])
                self.models[(col, q)] = m
        return self

    def _calibrate(self, df):
        """conformal式带宽校准：以季节naive残差std为基准，加膨胀系数。
        模型分位数区间在小样本上偏窄，用历史残差规模兜底。
        """
        for c in COLS:
            s = df[c].values
            if len(s) >= 24:
                resid = s[12:] - s[:-12]
                sigma = float(np.std(resid))
            else:
                sigma = 0.05 * float(np.mean(s))
            # 1.2816*sigma = 80%区间半宽(正态)；1.25为预测期膨胀系数
            self.band[c] = 1.2816 * sigma * 1.25

    def predict(self, hist, horizon_yms):
        """hist: 宽表(全部历史)；返回 DataFrame(index=ym, columns=MultiIndex[col,q])。"""
        h = hist.copy()
        t0 = self.t0 if self.t0 is not None else ym_index(h.index[0])
        recs = []
        for k, ym in enumerate(horizon_yms):
            x = pd.DataFrame([feature_row(h, ym, t0)])[self.columns]
            row = {}
            for col in COLS:
                for q in QUANTILES:
                    p = float(self.models[(col, q)].predict(x)[0])
                    row[(col, q)] = p
                # 带宽随horizon扩大（递归误差累积）
                half = self.band.get(col, 0) * (1 + 0.25 * k)
                p50 = row[(col, 0.5)]
                row[(col, 0.1)] = min(row[(col, 0.1)], p50 - half)
                row[(col, 0.9)] = max(row[(col, 0.9)], p50 + half)
                for q in QUANTILES:
                    row[(col, q)] = max(row[(col, q)], 1.0)
            recs.append(row)
            h.loc[ym] = {c: row[(c, 0.5)] for c in COLS}
        out = pd.DataFrame(recs, index=horizon_yms)
        out.columns = pd.MultiIndex.from_tuples(out.columns)
        return out
