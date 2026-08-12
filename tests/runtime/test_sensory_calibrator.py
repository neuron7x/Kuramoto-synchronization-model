# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import numpy as np
import pandas as pd

from runtime.filters.vlpo_core_filter.data.sensory_calibrator import (
    SensoryCalibrationConfig,
    SensoryCalibrator,
)


def test_normalization_scales_hold_after_volatility_shift() -> None:
    rng = np.random.default_rng(2024)
    config = SensoryCalibrationConfig(mode="ema_minmax", calibration_window=50)
    calibrator = SensoryCalibrator(["latency", "coherency"], config=config)

    low_vol = pd.DataFrame(
        {
            "latency": rng.normal(0.5, 0.01, size=50),
            "coherency": rng.normal(0.8, 0.01, size=50),
        }
    )
    calibrator.normalize(low_vol)
    assert calibrator.steady_state is True

    scales_before = calibrator.scales()

    high_vol = pd.DataFrame(
        {
            "latency": rng.normal(0.5, 0.2, size=50),
            "coherency": rng.normal(0.8, 0.2, size=50),
        }
    )
    normalized = calibrator.normalize(high_vol)
    scales_after = calibrator.scales()

    assert scales_after == scales_before
    assert normalized["latency"].between(0.0, 1.0).all()
    assert normalized["coherency"].between(0.0, 1.0).all()


def test_mode_selector_picks_full_extremes_not_the_quantile_band() -> None:
    """`if self._config.mode == "ema_minmax"` chooses full min/max over the 5-95 quantile band.

    Both branches produce values in [0, 1], so the existing test cannot tell them apart and a
    mutation probe left `Eq -> NotEq` alive — under it an ema_minmax config silently runs the
    quantile fallback. The two normalisations disagree sharply in the presence of an outlier:
    with min/max the bulk of the data is compressed toward zero, whereas the quantile band
    clips the tails and pushes the same points to 1.0. One heavy outlier makes the branch
    identity observable.
    """
    bulk_plus_outlier = np.concatenate([np.arange(100, dtype=float), np.array([1000.0])])
    frame = pd.DataFrame({"latency": bulk_plus_outlier})

    ema = SensoryCalibrator(
        ["latency"], config=SensoryCalibrationConfig(mode="ema_minmax", calibration_window=200)
    )
    ema_out = ema.normalize(frame)

    quantile = SensoryCalibrator(
        ["latency"], config=SensoryCalibrationConfig(mode="quantile", calibration_window=200)
    )
    quantile_out = quantile.normalize(frame)

    # The value 99 sits at the top of the bulk but far below the outlier.
    # ema_minmax scales it by the full range [0, 1000] -> ~0.099.
    # The quantile band [~5, ~95] pushes it past 1.0, clipped to 1.0.
    ema_99 = float(ema_out["latency"].iloc[99])
    quantile_99 = float(quantile_out["latency"].iloc[99])

    assert ema_99 < 0.2, f"ema_minmax must scale by full min/max, got {ema_99}"
    assert quantile_99 == 1.0, f"quantile band must clip the bulk top to 1.0, got {quantile_99}"
    assert quantile_99 - ema_99 > 0.5, "the two modes must be observably different"
