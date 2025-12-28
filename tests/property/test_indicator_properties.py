# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

try:
    from hypothesis import HealthCheck, Phase, assume, given, settings
    from hypothesis import strategies as st
except ImportError:  # pragma: no cover - optional dependency
    pytest.skip("hypothesis not installed", allow_module_level=True)

from core.indicators.hurst import hurst_exponent
from core.indicators.kuramoto import kuramoto_order, multi_asset_kuramoto
from core.indicators.ricci import build_price_graph, mean_ricci
from core.indicators.temporal_ricci import TemporalRicciAnalyzer

finite_floats = st.floats(
    allow_nan=True,
    allow_infinity=True,
    width=64,
)


@given(st.lists(finite_floats, min_size=3, max_size=50))
def test_kuramoto_order_handles_non_finite(phases: list[float]) -> None:
    arr = np.asarray(phases, dtype=float)
    result = kuramoto_order(arr)
    assert np.isfinite(result)
    assert 0.0 <= result
    assert result <= 1.0 or np.isclose(result, 1.0, rtol=1e-9, atol=1e-12)


@given(
    st.integers(min_value=2, max_value=6),
    st.integers(min_value=8, max_value=64),
    st.data(),
)
def test_multi_asset_kuramoto_supports_variable_windows(
    asset_count: int,
    window: int,
    data: st.DataObject,
) -> None:
    series_list = []
    for _ in range(asset_count):
        samples = data.draw(
            st.lists(finite_floats, min_size=window, max_size=window),
            label="series",
        )
        series_list.append(np.asarray(samples, dtype=float))
    result = multi_asset_kuramoto(series_list)
    assert np.isfinite(result)
    assert 0.0 <= result
    assert result <= 1.0 or np.isclose(result, 1.0, rtol=1e-9, atol=1e-12)


@given(st.lists(finite_floats, min_size=3, max_size=40))
def test_mean_ricci_accepts_non_finite_inputs(prices: list[float]) -> None:
    arr = np.asarray(prices, dtype=float)
    graph = build_price_graph(arr)
    curvature = mean_ricci(graph)
    assert np.isfinite(curvature)


@settings(deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    st.integers(min_value=32, max_value=128),
    st.lists(finite_floats, min_size=128, max_size=384),
)
def test_temporal_ricci_resilient_to_non_finite(
    window: int, raw_prices: list[float]
) -> None:
    length = len(raw_prices)
    index = pd.date_range("2023-01-01", periods=length, freq="T")
    prices = np.asarray(raw_prices, dtype=float)
    volumes = np.linspace(1.0, 2.0, length)
    df = pd.DataFrame({"close": prices, "volume": volumes}, index=index)
    window = min(window, length)
    analyzer = TemporalRicciAnalyzer(
        window_size=window, n_snapshots=4, retain_history=False
    )
    result = analyzer.analyze(df)
    assert np.isfinite(result.temporal_curvature)
    assert np.isfinite(result.structural_stability)


def _float_extended_dtype() -> np.dtype:
    """Return the highest precision floating dtype available on this platform."""

    for candidate in (
        getattr(np, "float128", None),
        getattr(np, "longdouble", None),
        np.float64,
    ):
        if candidate is not None:
            return np.dtype(candidate)
    return np.dtype(np.float64)


def _kuramoto_reference(phases: np.ndarray) -> float | np.ndarray:
    """High-precision Kuramoto order parameter used as a verification oracle."""

    dtype = _float_extended_dtype()
    arr = np.asarray(phases, dtype=dtype)
    mask = np.isfinite(arr)

    if arr.ndim == 1:
        valid = arr[mask]
        if valid.size == 0:
            return 0.0
        cos_sum = np.sum(np.cos(valid), dtype=dtype)
        sin_sum = np.sum(np.sin(valid), dtype=dtype)
        magnitude = np.hypot(cos_sum, sin_sum)
        result = magnitude / dtype.type(valid.size)
        return float(np.clip(result, 0.0, 1.0))

    if arr.ndim != 2:
        raise ValueError("_kuramoto_reference expects 1D or 2D arrays")

    if not mask.any():
        return np.zeros(arr.shape[1], dtype=float)

    valid_counts = mask.sum(axis=0)
    safe = np.where(mask, arr, dtype.type(0.0))
    cos_vals = np.cos(safe) * mask.astype(dtype)
    sin_vals = np.sin(safe) * mask.astype(dtype)
    cos_sum = np.sum(cos_vals, axis=0, dtype=dtype)
    sin_sum = np.sum(sin_vals, axis=0, dtype=dtype)
    magnitude = np.hypot(cos_sum, sin_sum)
    values = np.divide(
        magnitude,
        valid_counts.astype(dtype),
        out=np.zeros_like(magnitude, dtype=dtype),
        where=valid_counts > 0,
    )
    clipped = np.clip(values, 0.0, 1.0)
    clipped = np.where(clipped < dtype.type(1e-12), dtype.type(0.0), clipped)
    return clipped.astype(float)


def _hurst_reference(ts: np.ndarray, min_lag: int, max_lag: int) -> float:
    """Compute a high-precision R/S estimator for validation purposes."""

    dtype = _float_extended_dtype()
    series = np.asarray(ts, dtype=dtype)
    if series.size < max_lag * 2:
        return 0.5

    lags = np.arange(min_lag, max_lag + 1)
    tau = np.empty(lags.size, dtype=dtype)

    for idx, lag in enumerate(lags):
        diff = series[lag:] - series[:-lag]
        segment = diff.astype(dtype)
        count = dtype.type(segment.size)
        if count == 0:
            tau[idx] = dtype.type(0.0)
            continue
        sum_vals = np.sum(segment, dtype=dtype)
        sum_sq = np.dot(segment, segment)
        mean = sum_vals / count
        var = sum_sq / count - mean * mean
        tau[idx] = np.sqrt(var) if var > 0 else dtype.type(0.0)

    if np.any(tau <= 0.0):
        return 0.5

    y = np.log(tau.astype(dtype))
    X = np.vstack([np.ones_like(lags, dtype=dtype), np.log(lags.astype(dtype))]).T
    try:
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    except TypeError:
        beta, *_ = np.linalg.lstsq(
            X.astype(np.float64), y.astype(np.float64), rcond=None
        )
    hurst = beta[1]
    return float(np.clip(hurst, 0.0, 1.0))


@settings(
    max_examples=200,
    deadline=None,
    phases=[Phase.generate],
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    st.lists(
        st.floats(
            min_value=-100,
            max_value=100,
            allow_nan=False,
            allow_infinity=False,
            width=64,
        ),
        min_size=3,
        max_size=64,
    ),
    st.floats(
        min_value=-100, max_value=100, allow_nan=False, allow_infinity=False, width=64
    ),
)
def test_kuramoto_order_translation_invariant(
    phases: list[float], shift: float
) -> None:
    arr = np.asarray(phases, dtype=float)
    assume(np.isfinite(arr).all())
    base = kuramoto_order(arr)
    shifted = kuramoto_order(arr + shift)
    assert math.isfinite(base)
    assert math.isfinite(shifted)
    # Use 1e-5 tolerance to account for floating-point precision loss
    # in trigonometric operations with large phase values
    assert shifted == pytest.approx(base, rel=1e-5, abs=1e-5)


@settings(
    max_examples=150,
    deadline=None,
    phases=[Phase.generate],
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    st.lists(
        st.floats(
            min_value=-100,
            max_value=100,
            allow_nan=False,
            allow_infinity=False,
            width=64,
        ),
        min_size=4,
        max_size=60,
    )
)
def test_kuramoto_order_matches_reference(phases: list[float]) -> None:
    arr = np.asarray(phases, dtype=float)
    assume(np.isfinite(arr).all())
    reference = _kuramoto_reference(arr)
    result = kuramoto_order(arr)
    assert math.isfinite(result)
    assert math.isfinite(reference)
    # Use 1e-5 tolerance to account for numerical differences between
    # implementations when dealing with trigonometric operations
    assert result == pytest.approx(reference, rel=1e-5, abs=1e-5)


@settings(
    max_examples=75,
    deadline=None,
    phases=[Phase.generate],
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    st.data(),
)
def test_kuramoto_order_matrix_matches_reference(data: st.DataObject) -> None:
    rows = data.draw(st.integers(min_value=1, max_value=8), label="rows")
    cols = data.draw(st.integers(min_value=2, max_value=12), label="cols")
    elements = st.floats(
        min_value=-2e4, max_value=2e4, allow_nan=False, allow_infinity=False, width=64
    )
    matrix = data.draw(
        st.lists(
            st.lists(elements, min_size=cols, max_size=cols),
            min_size=rows,
            max_size=rows,
        ),
        label="matrix",
    )
    arr = np.asarray(matrix, dtype=float)
    assume(np.isfinite(arr).all(axis=None))
    reference = _kuramoto_reference(arr)
    result = kuramoto_order(arr)
    assert np.all(np.isfinite(reference))
    assert np.all(np.isfinite(result))
    np.testing.assert_allclose(result, reference, rtol=1e-3, atol=1e-3)


@settings(
    max_examples=120,
    deadline=None,
    phases=[Phase.generate],
    suppress_health_check=[HealthCheck.too_slow],
)
@given(st.data())
def test_hurst_exponent_affine_invariance(data: st.DataObject) -> None:
    length = data.draw(st.integers(min_value=128, max_value=256), label="length")
    base_series = data.draw(
        st.lists(
            st.floats(
                min_value=-5000.0,
                max_value=5000.0,
                allow_nan=False,
                allow_infinity=False,
                width=64,
            ),
            min_size=length,
            max_size=length,
        ),
        label="base_series",
    )
    series = np.asarray(base_series, dtype=float)
    assume(np.isfinite(series).all())
    assume(np.std(series) > 1e-9)
    max_lag_cap = min(32, series.size // 2 - 1)
    assume(max_lag_cap >= 6)
    min_lag = data.draw(st.integers(min_value=2, max_value=5), label="min_lag")
    max_lag = data.draw(
        st.integers(min_value=min_lag + 1, max_value=max_lag_cap), label="max_lag"
    )
    shift = data.draw(
        st.floats(min_value=-1e4, max_value=1e4, allow_nan=False, allow_infinity=False),
        label="shift",
    )
    scale = data.draw(
        st.floats(min_value=-5.0, max_value=5.0, allow_nan=False, allow_infinity=False),
        label="scale",
    )
    assume(abs(scale) > 1e-3)
    base_value = hurst_exponent(series, min_lag=min_lag, max_lag=max_lag)
    transformed_value = hurst_exponent(
        series * scale + shift, min_lag=min_lag, max_lag=max_lag
    )
    assume(np.isfinite(base_value) and np.isfinite(transformed_value))
    assert transformed_value == pytest.approx(base_value, rel=5e-5, abs=5e-5)


@settings(
    max_examples=120,
    deadline=None,
    phases=[Phase.generate],
    suppress_health_check=[HealthCheck.too_slow],
)
@given(st.data())
def test_hurst_matches_high_precision_reference(data: st.DataObject) -> None:
    length = data.draw(st.integers(min_value=140, max_value=260), label="length")
    raw = data.draw(
        st.lists(
            st.floats(
                min_value=-2000.0,
                max_value=2000.0,
                allow_nan=False,
                allow_infinity=False,
                width=64,
            ),
            min_size=length,
            max_size=length,
        ),
        label="raw_series",
    )
    series = np.asarray(raw, dtype=float)
    assume(np.isfinite(series).all())
    assume(np.std(series) > 1e-9)
    max_lag_cap = min(48, series.size // 2 - 2)
    assume(max_lag_cap > 6)
    min_lag = data.draw(st.integers(min_value=2, max_value=5), label="min_lag")
    max_lag = data.draw(
        st.integers(min_value=min_lag + 2, max_value=max_lag_cap), label="max_lag"
    )
    indicator = hurst_exponent(series, min_lag=min_lag, max_lag=max_lag)
    reference = _hurst_reference(series, min_lag, max_lag)
    assume(np.isfinite(indicator) and np.isfinite(reference))
    assert indicator == pytest.approx(reference, rel=5e-4, abs=5e-4)


@settings(
    max_examples=120,
    deadline=None,
    phases=[Phase.generate],
    suppress_health_check=[HealthCheck.too_slow],
)
@given(st.data())
def test_hurst_float32_matches_float64(data: st.DataObject) -> None:
    length = data.draw(st.integers(min_value=140, max_value=220), label="length")
    raw = data.draw(
        st.lists(
            st.floats(
                min_value=-1000.0,
                max_value=1000.0,
                allow_nan=False,
                allow_infinity=False,
                width=64,
            ),
            min_size=length,
            max_size=length,
        ),
        label="series",
    )
    series = np.asarray(raw, dtype=float)
    assume(np.isfinite(series).all())
    assume(np.std(series) > 1e-9)
    max_lag_cap = min(32, series.size // 2 - 2)
    assume(max_lag_cap > 6)
    min_lag = data.draw(st.integers(min_value=2, max_value=5), label="min_lag")
    max_lag = data.draw(
        st.integers(min_value=min_lag + 2, max_value=max_lag_cap), label="max_lag"
    )
    value64 = hurst_exponent(
        series, min_lag=min_lag, max_lag=max_lag, use_float32=False
    )
    value32 = hurst_exponent(series, min_lag=min_lag, max_lag=max_lag, use_float32=True)
    assume(np.isfinite(value64) and np.isfinite(value32))
    assert value32 == pytest.approx(value64, rel=5e-3, abs=5e-3)
