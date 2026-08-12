# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Regression tests for signal feature pipeline volume metrics."""

from __future__ import annotations

import numpy as np
import pandas as pd

from analytics.signals.pipeline import FeaturePipelineConfig, SignalFeaturePipeline


def test_volume_z_constant_volume_zero_variance() -> None:
    """Constant-volume windows should keep ``volume_z`` finite."""

    window = 20
    periods = window + 5
    index = pd.date_range("2024-01-01", periods=periods, freq="1h")
    frame = pd.DataFrame(
        {
            "close": np.linspace(100.0, 110.0, num=periods),
            "high": np.linspace(100.5, 110.5, num=periods),
            "low": np.linspace(99.5, 109.5, num=periods),
            "volume": np.full(periods, 1_000.0),
        },
        index=index,
    )

    pipeline = SignalFeaturePipeline(FeaturePipelineConfig(volatility_window=window))
    features = pipeline.transform(frame)

    volume_z = features["volume_z"]
    assert volume_z.isna().sum() == window - 1
    observed = volume_z.dropna()
    assert not np.isinf(observed).any()
    np.testing.assert_allclose(observed.to_numpy(), 0.0)
