import numpy as np
import pandas as pd

from runtime.filters.vlpo_core_filter.data.sensory_calibrator import (
    SensoryCalibrator,
    SensoryCalibrationConfig,
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
