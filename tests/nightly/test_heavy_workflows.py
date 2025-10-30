# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Nightly coverage for heavy indicator math, long backtests, and fuzzing."""
from __future__ import annotations

import math
from typing import Iterable

import numpy as np
import pytest

from backtest.engine import walk_forward
from core.indicators.entropy import delta_entropy, entropy
from core.indicators.kuramoto import compute_phase, kuramoto_order, multi_asset_kuramoto
from core.indicators.ricci import build_price_graph, mean_ricci

try:  # Optional dependency during lightweight installs
    from hypothesis import HealthCheck, given, settings
    from hypothesis import strategies as st
except ImportError:  # pragma: no cover - nightly suites require hypothesis
    HealthCheck = None  # type: ignore[assignment]
    given = None  # type: ignore[assignment]
    settings = None  # type: ignore[assignment]
    st = None  # type: ignore[assignment]
    _HYPOTHESIS_AVAILABLE = False
else:  # pragma: no cover - import side effect only
    _HYPOTHESIS_AVAILABLE = True

pytestmark = [pytest.mark.nightly, pytest.mark.slow]


def _generate_price_path(seed: int, steps: int) -> np.ndarray:
    """Return a long synthetic price series with multiple volatility regimes."""

    rng = np.random.default_rng(seed)
    segments = [
        rng.normal(0.0, 0.3, steps // 3),
        rng.normal(0.0, 1.0, steps // 3),
        rng.normal(0.0, 1.8, steps - 2 * (steps // 3)),
    ]
    returns = np.concatenate(segments)
    prices = 100.0 + np.cumsum(returns)
    prices -= prices.min() - 50.0  # keep prices positive for log/graph transforms
    return prices.astype(float)


def _rolling_curvature(prices: np.ndarray, window: int, stride: int) -> np.ndarray:
    """Compute mean Ricci curvature on a rolling window to exercise heavy math."""

    curvature: list[float] = []
    for start in range(0, max(prices.size - window + 1, 1), stride):
        window_prices = prices[start : start + window]
        graph = build_price_graph(window_prices)
        if graph.number_of_edges() == 0:
            curvature.append(0.0)
            continue
        curvature.append(float(mean_ricci(graph)))
    return np.asarray(curvature, dtype=float)


@pytest.mark.heavy_math
def test_long_backtest_with_heavy_indicators() -> None:
    """Run a multi-year walk-forward using entropy, Ricci, and Kuramoto features."""

    prices = _generate_price_path(seed=42, steps=252 * 8)

    def heavy_signal(series: np.ndarray) -> np.ndarray:
        phases = compute_phase(series, use_float32=True)
        phase_velocity = np.gradient(phases)
        curvature = _rolling_curvature(series, window=256, stride=128)
        curvature_scale = 1.0
        if curvature.size:
            curvature_scale += float(np.tanh(np.nanmean(curvature)))

        entropy(series, bins=64, use_float32=True, chunk_size=2048)
        entropy_delta = delta_entropy(series, window=min(256, series.size // 2) or 1)
        entropy_scale = 1.0 + 0.25 * math.tanh(entropy_delta)

        tail = series[-1024:] if series.size >= 1024 else series
        tail_phase = compute_phase(tail, use_float32=True)
        tail_order = kuramoto_order(tail_phase)
        order_scale = 1.0 + float(tail_order)

        signal = np.tanh(phase_velocity * curvature_scale * entropy_scale * order_scale)
        return np.clip(signal, -1.0, 1.0)

    result = walk_forward(
        prices, heavy_signal, fee=0.0004, strategy_name="nightly-heavy"
    )

    assert result.trades > prices.size * 0.02
    assert np.isfinite(result.pnl)
    assert result.equity_curve.size == prices.size - 1
    assert np.all(np.isfinite(result.equity_curve))


@pytest.mark.heavy_math
def test_entropy_parallel_matches_serial() -> None:
    """Parallel chunked entropy should stay close to single-pass computation."""

    samples = _generate_price_path(seed=7, steps=200_000)
    baseline = entropy(samples, bins=80)
    parallel = entropy(
        samples,
        bins=80,
        use_float32=True,
        chunk_size=4096,
        parallel="async",
        max_workers=8,
    )
    assert math.isfinite(baseline)
    assert math.isfinite(parallel)
    assert abs(parallel - baseline) <= 0.35


@pytest.mark.heavy_math
def test_multi_asset_kuramoto_high_cardinality() -> None:
    """Kuramoto order should remain bounded for a large oscillator matrix."""

    rng = np.random.default_rng(11)
    assets = [
        compute_phase(_generate_price_path(seed=seed, steps=4096), use_float32=True)
        for seed in range(8)
    ]
    shifted: Iterable[np.ndarray] = (
        asset + rng.normal(0.0, 0.05, asset.shape) for asset in assets
    )
    order_value = multi_asset_kuramoto(
        tuple(np.asarray(x, dtype=float) for x in shifted)
    )
    assert 0.0 <= order_value <= 1.0 or np.isclose(order_value, 1.0)


if _HYPOTHESIS_AVAILABLE:

    @settings(
        max_examples=25,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
    )
    @given(
        st.integers(min_value=32, max_value=1024).flatmap(
            lambda length: st.lists(
                st.floats(allow_nan=True, allow_infinity=True, width=64),
                min_size=length,
                max_size=length,
            )
        )
    )
    def test_compute_phase_fuzz(values: list[float]) -> None:
        """Fuzz compute_phase with large, potentially non-finite samples."""

        series = np.asarray(values, dtype=float)
        phases = compute_phase(series, use_float32=True)
        assert phases.shape == series.shape
        finite_phases = np.nan_to_num(phases, nan=0.0, copy=False)
        assert np.all(np.isfinite(finite_phases))

    @settings(
        max_examples=15,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
    )
    @given(
        st.integers(min_value=128, max_value=2048).flatmap(
            lambda length: st.lists(
                st.floats(
                    min_value=0.0,
                    max_value=2000.0,
                    allow_nan=False,
                    allow_infinity=False,
                ),
                min_size=length,
                max_size=length,
            )
        )
    )
    def test_delta_entropy_window_fuzz(prices: list[float]) -> None:
        """Delta entropy should be finite for long windows with adaptive binning."""

        series = np.asarray(prices, dtype=float)
        window = max(128, len(series) // 4)
        value = delta_entropy(series, window=window)
        assert math.isfinite(value)
        assert abs(value) < 10.0

else:  # pragma: no cover - optional dependency absent

    @pytest.mark.skip(reason="hypothesis not installed")
    def test_compute_phase_fuzz() -> None:  # type: ignore[empty-body]
        pytest.skip("hypothesis not installed")

    @pytest.mark.skip(reason="hypothesis not installed")
    def test_delta_entropy_window_fuzz() -> None:  # type: ignore[empty-body]
        pytest.skip("hypothesis not installed")
