# -*- coding: utf-8 -*-
"""M3：Chronos-2 时序基础模型（零样本）。

权重本地落点：<repo>/forecast-engine/_models/amazon__chronos-2（不随 Git 提交）。
首次下载：设 HF_ENDPOINT=https://hf-mirror.com 后
    huggingface-cli download amazon/chronos-2 \
        --local-dir <repo>/forecast-engine/_models/amazon__chronos-2
之后默认离线运行（HF_HUB_OFFLINE=1），直接读本地目录，不依赖 HF 缓存。
"""
import os

os.environ.setdefault("HF_HUB_OFFLINE", "1")

import numpy as np

try:
    import torch
    from chronos import Chronos2Pipeline
    CHRONOS_AVAILABLE = True
except ImportError:
    CHRONOS_AVAILABLE = False

_MODEL_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "_models", "amazon__chronos-2"))

# 优先本地权重；缺失时回退 HF 缓存（amazon/chronos-2）。
# 更轻量的 bolt-base 需 ChronosBoltPipeline，此处暂不支持。
CANDIDATES = [_MODEL_DIR, "amazon/chronos-2"]

# 进程内单例缓存：同一模型只加载一次，跨 M3Chronos 实例复用。
_pipe_cache = {}


def _load_pipeline(name):
    pipe = _pipe_cache.get(name)
    if pipe is None:
        pipe = Chronos2Pipeline.from_pretrained(name)
        _pipe_cache[name] = pipe
    return pipe


class M3Chronos:
    def __init__(self, model_name=None):
        if not CHRONOS_AVAILABLE:
            raise RuntimeError("chronos-forecasting 未安装: "
                               "pip install chronos-forecasting")
        self.pipe = None
        names = [model_name] if model_name else CANDIDATES
        errors = []
        for name in names:
            try:
                self.pipe = _load_pipeline(name)
                self.model_name = name
                break
            except Exception as e:  # noqa: BLE001
                errors.append("%s: %s" % (name, e))
        if self.pipe is None:
            raise RuntimeError("Chronos 模型加载失败: %s" % errors)

    def predict(self, hist_values, horizon, quantiles=(0.1, 0.5, 0.9)):
        """单序列零样本分位数预测。返回 {q: ndarray(horizon)}。

        Chronos-2 API：inputs 需 3D (n_series, n_variates, history_length)，
        返回 tuple[list[Tensor], list[Tensor]]，取 q[0].squeeze(0) 即单序列。

        边界校验：拒绝空/多维/含 NaN 或 Inf 的历史、非正整数 horizon，
        以及空/越界/重复/非递增/非有限的分位数；在调用底层 pipeline 前以
        ValueError 拒绝。对模型输出再校验形状、有限性与分位数顺序，异常以
        RuntimeError 拒绝，不被下限截断掩盖。
        """
        # --- 输入校验 ---
        try:
            hist = np.asarray(hist_values, dtype=np.float64)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("hist_values 必须是一维数值序列") from exc
        if hist.ndim != 1:
            raise ValueError("hist_values 必须是一维数值序列，收到 %d 维"
                             % hist.ndim)
        if hist.size == 0:
            raise ValueError("hist_values 不能为空")
        if not np.isfinite(hist).all():
            raise ValueError("hist_values 含 NaN 或 Inf")

        if isinstance(horizon, bool) or not isinstance(horizon, (int, np.integer)):
            raise ValueError("horizon 必须为正整数，收到 %r" % (horizon,))
        if int(horizon) <= 0:
            raise ValueError("horizon 必须为正整数，收到 %r" % (horizon,))

        try:
            qs = np.asarray(quantiles, dtype=np.float64)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("quantiles 必须为数值序列") from exc
        if qs.ndim != 1 or qs.size == 0:
            raise ValueError("quantiles 必须为非空一维序列")
        if not np.isfinite(qs).all():
            raise ValueError("quantiles 含 NaN 或 Inf")
        if ((qs <= 0.0) | (qs >= 1.0)).any():
            raise ValueError("quantiles 必须位于 (0,1) 开区间")
        if (np.diff(qs) <= 0.0).any():
            raise ValueError("quantiles 必须严格递增且不重复")

        # --- 调用底层 ---
        ctx = torch.tensor(hist, dtype=torch.float32).reshape(1, 1, -1)
        if not torch.isfinite(ctx).all():
            raise ValueError("hist_values 转换为 float32 后含非有限值")
        q, _mean = self.pipe.predict_quantiles(
            inputs=ctx, prediction_length=int(horizon),
            quantile_levels=qs.tolist())

        # --- 输出校验 ---
        if not isinstance(q, (list, tuple)) or len(q) == 0:
            raise RuntimeError("模型输出为空或非预期序列类型")
        first = q[0]
        if not isinstance(first, torch.Tensor):
            raise RuntimeError("模型输出首元素不是 Tensor")
        arr = first.squeeze(0).numpy().astype(np.float64)
        expected = (int(horizon), qs.size)
        if arr.shape != expected:
            raise RuntimeError("模型输出形状 %s 与期望 %s 不符"
                               % (arr.shape, expected))
        if not np.isfinite(arr).all():
            raise RuntimeError("模型输出含 NaN 或 Inf")
        if arr.shape[1] > 1 and (np.diff(arr, axis=1) < 0.0).any():
            raise RuntimeError("模型输出分位数顺序错误（非单调不减）")

        keys = qs.tolist()
        return {keys[i]: np.maximum(arr[:, i], 1.0) for i in range(qs.size)}
