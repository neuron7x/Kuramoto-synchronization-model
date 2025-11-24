import numpy as np

from utils.change_point import cusum_score, vol_shock


def test_cusum_score_detects_shift_within_threshold():
    series = np.array([0.0, 0.0, 10.0, 10.0, 10.0])

    alarms = cusum_score(series, threshold=2.0)

    assert alarms == 2.0


def test_cusum_score_handles_empty_series():
    assert cusum_score([]) == 0.0


def test_vol_shock_requires_minimum_window():
    assert vol_shock([0.1, -0.2], window=5) == 0.0


def test_vol_shock_detects_recent_volatility_increase():
    baseline = np.linspace(0.0, 0.59, 60)
    recent = np.linspace(0.0, 5.9, 60)
    returns = np.concatenate([baseline, recent])

    shock = vol_shock(returns, window=60)

    assert shock > 0.0
