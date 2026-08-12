# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import numpy as np
import pandas as pd

from runtime.filters.vlpo_core_filter import VLPOCoreFilter


def _build_dataframe() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    target = np.linspace(0.2, 0.8, num=50)
    noisy_feature = target + rng.normal(0, 0.05, size=50)
    flat_feature = np.ones_like(target) * 0.5
    weak_corr_feature = rng.normal(0, 0.01, size=50)
    df = pd.DataFrame(
        {
            "latency": noisy_feature,
            "flat": flat_feature,
            "weak": weak_corr_feature,
            "coherency": target,
        }
    )
    return df


def test_vlpo_filter_downscales_low_entropy_and_forgets_low_corr():
    df = _build_dataframe()
    filt = VLPOCoreFilter(entropy_threshold=1.0, correlation_threshold=0.2, scale_factor=0.5)
    cleaned = filt.filter(df, target_col="coherency")

    assert cleaned.shape == df.shape
    # Low entropy flat feature should not increase in magnitude
    assert abs(cleaned["flat"].iloc[0]) <= df["flat"].iloc[0] * 0.5 + 1e-9
    # Weak correlation feature should be zeroed
    assert np.allclose(cleaned["weak"].to_numpy(), 0.0)


def test_filter_preserves_target_series():
    df = _build_dataframe()
    filt = VLPOCoreFilter()
    cleaned = filt.filter(df, target_col="coherency")
    assert np.allclose(cleaned["coherency"].to_numpy(), df["coherency"].to_numpy())
