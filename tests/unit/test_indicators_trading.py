"""Tests for lightweight trading indicators."""

from __future__ import annotations

import numpy as np
import pytest

from core.indicators.kuramoto import compute_phase, kuramoto_order
from core.indicators.trading import (
    HurstIndicator,
    KuramotoIndicator,
    VPINIndicator,
    _as_float_array,
    _fill_missing,
    _rolling_sum,
)


def test_kuramoto_indicator_matches_order_parameter() -> None:
    """KuramotoIndicator should match direct Kuramoto order evaluations."""

    rng = np.random.default_rng(1234)
    prices = np.cumsum(rng.normal(scale=0.5, size=64)) + 100.0
    indicator = KuramotoIndicator(window=16, coupling=1.0)

    result = indicator.compute(prices)

    phases = compute_phase(np.asarray(prices, dtype=float))
    expected = np.zeros_like(phases, dtype=float)
    min_samples = min(indicator.window, indicator.min_samples)
    for idx in range(phases.size):
        start = max(0, idx - indicator.window + 1)
        count = idx - start + 1
        if count < min_samples:
            continue
        expected[idx] = float(kuramoto_order(phases[start : idx + 1]))

    assert np.allclose(result, expected, rtol=1e-6, atol=1e-6)
    assert np.all((result >= 0.0) & (result <= 1.0))


def test_kuramoto_indicator_clips_with_coupling() -> None:
    """KuramotoIndicator should clamp amplified synchrony into [0, 1]."""

    indicator = KuramotoIndicator(window=8, coupling=5.0)
    prices = np.linspace(100.0, 102.0, num=32)

    result = indicator.compute(prices)

    assert np.all((result >= 0.0) & (result <= 1.0))
    assert np.any(result > 0.0)


def test_kuramoto_indicator_requires_volumes_for_weighting() -> None:
    """Volume-aware configuration should request explicit weights."""

    indicator = KuramotoIndicator(volume_weighting="sqrt")
    with pytest.raises(ValueError, match="volumes must be provided"):
        indicator.compute([100.0, 101.0, 102.0])


def test_kuramoto_indicator_weighted_matches_manual() -> None:
    """Weighted synchrony should align with direct Kuramoto order."""

    rng = np.random.default_rng(2025)
    prices = np.cumsum(rng.normal(scale=0.2, size=96)) + 50.0
    volumes = rng.uniform(50.0, 150.0, size=prices.size)
    indicator = KuramotoIndicator(
        window=24,
        coupling=1.0,
        min_samples=8,
        volume_weighting="linear",
        smoothing=0.0,
    )

    result = indicator.compute(prices, volumes=volumes)
    phases = compute_phase(prices)
    expected = np.zeros_like(result)
    min_samples = min(indicator.window, indicator.min_samples)
    for idx in range(result.size):
        start = max(0, idx - indicator.window + 1)
        count = idx - start + 1
        if count < min_samples:
            continue
        slice_phases = phases[start : idx + 1]
        slice_weights = volumes[start : idx + 1]
        expected[idx] = float(kuramoto_order(slice_phases, weights=slice_weights))

    assert np.allclose(result, expected, rtol=1e-6, atol=1e-6)


def test_kuramoto_indicator_validates_smoothing() -> None:
    """Invalid smoothing factors should raise a descriptive error."""

    with pytest.raises(ValueError, match=r"smoothing must be within \[0, 1\)"):
        KuramotoIndicator(smoothing=1.0)


def test_as_float_array_validates_shape() -> None:
    """Helper should coerce sequences to 1-D float arrays and reject higher dims."""

    values = _as_float_array([1, 2, 3])

    assert values.dtype == float
    assert values.ndim == 1
    assert np.all(values == np.array([1.0, 2.0, 3.0]))

    with pytest.raises(ValueError, match="one-dimensional"):
        _as_float_array([[1, 2], [3, 4]])


def test_fill_missing_interpolates_and_handles_all_nan() -> None:
    """Missing values should be interpolated while all-NaN arrays become zeros."""

    series = np.array([np.nan, 1.0, np.nan, 3.0, np.nan])
    filled = _fill_missing(series)
    expected = np.array([1.0, 1.0, 2.0, 3.0, 3.0])

    assert np.allclose(filled, expected)

    all_nan = np.array([np.nan, np.nan])
    zeros = _fill_missing(all_nan)

    assert np.all(zeros == np.zeros_like(all_nan))


@pytest.mark.parametrize("window", [1, 2, 4])
def test_rolling_sum_matches_manual(window: int) -> None:
    """Rolling sum should agree with explicit summation for basic cases."""

    values = np.array([1.0, 2.0, 3.0, 4.0])
    result = _rolling_sum(values, window, backend="cpu")

    manual = []
    for idx in range(values.size):
        start = max(0, idx - window + 1)
        manual.append(values[start : idx + 1].sum())

    assert np.allclose(result, np.array(manual, dtype=float))


def test_rolling_sum_validates_parameters() -> None:
    """Invalid inputs should trigger descriptive errors."""

    values = np.array([1.0, 2.0])
    with pytest.raises(ValueError, match="positive"):
        _rolling_sum(values, 0)

    with pytest.raises(ValueError, match="one-dimensional"):
        _rolling_sum(np.array([[1.0, 2.0], [3.0, 4.0]]), 2)


def test_hurst_indicator_validation() -> None:
    """Constructor should enforce positive parameters and supported backends."""

    with pytest.raises(ValueError, match="window must be positive"):
        HurstIndicator(window=0)
    with pytest.raises(ValueError, match="min_lag must be positive"):
        HurstIndicator(min_lag=0)
    with pytest.raises(ValueError, match="max_lag must exceed"):
        HurstIndicator(min_lag=3, max_lag=3)
    with pytest.raises(ValueError, match="Unsupported backend"):
        HurstIndicator(backend="invalid")


def test_hurst_indicator_compute_range_and_length() -> None:
    """HurstIndicator should return bounded finite values with correct length."""

    x = np.linspace(0.0, 4.0 * np.pi, num=64)
    prices = 100.0 + np.sin(x) + 0.05 * x
    indicator = HurstIndicator(window=6, min_lag=2, backend="cpu")

    result = indicator.compute(prices)

    assert result.shape == prices.shape
    assert np.all(np.isfinite(result))
    assert np.all((0.0 <= result) & (result <= 1.0))
    # The first few samples should remain at the neutral 0.5 while warming up
    assert np.allclose(result[: indicator.min_lag * 2], 0.5)


def test_hurst_indicator_handles_empty_series() -> None:
    """An empty input should return an empty array without errors."""

    indicator = HurstIndicator()
    result = indicator.compute([])

    assert result.size == 0


def test_vpin_indicator_validation() -> None:
    """VPINIndicator should guard against invalid configuration values."""

    with pytest.raises(ValueError, match="bucket_size must be positive"):
        VPINIndicator(bucket_size=0)
    with pytest.raises(ValueError, match="threshold must be positive"):
        VPINIndicator(threshold=0.0)
    with pytest.raises(ValueError, match="Unsupported backend"):
        VPINIndicator(backend="tpucpu")


def test_vpin_indicator_computation_matches_manual_sum() -> None:
    """VPINIndicator compute should agree with manual imbalance ratios."""

    data = np.array(
        [
            [100.0, 60.0, 40.0],
            [80.0, 50.0, 30.0],
            [120.0, 90.0, 30.0],
            [90.0, 20.0, 70.0],
        ]
    )
    indicator = VPINIndicator(bucket_size=2, threshold=0.8, backend="cpu")

    result = indicator.compute(data)

    total = np.array([100.0, 180.0, 200.0, 210.0])
    imbalance = np.array([20.0, 40.0, 80.0, 110.0])
    expected = np.zeros_like(total)
    mask = total > 0
    expected[mask] = imbalance[mask] / total[mask]

    assert np.allclose(result, expected)


def test_vpin_indicator_handles_zero_volume() -> None:
    """Zero total volume should yield zero VPIN without division warnings."""

    data = np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]])
    indicator = VPINIndicator(bucket_size=1)

    result = indicator.compute(data)

    assert np.all(result == 0.0)


def test_vpin_indicator_signed_mode_preserves_direction() -> None:
    """Signed imbalance mode should retain directionality within bounds."""

    data = np.array(
        [
            [50.0, 40.0, 10.0],
            [60.0, 20.0, 40.0],
            [55.0, 45.0, 10.0],
            [70.0, 15.0, 55.0],
        ]
    )
    indicator = VPINIndicator(bucket_size=2, use_signed_imbalance=True, smoothing=0.0)

    result = indicator.compute(data)

    total = data[:, 0]
    signed = data[:, 1] - data[:, 2]
    total_sums = _rolling_sum(total, indicator.bucket_size, backend=indicator.backend)
    signed_sums = _rolling_sum(signed, indicator.bucket_size, backend=indicator.backend)
    expected = np.zeros_like(total_sums)
    mask = total_sums > indicator.min_volume
    expected[mask] = np.clip(signed_sums[mask] / total_sums[mask], -1.0, 1.0)

    assert np.allclose(result, expected)
