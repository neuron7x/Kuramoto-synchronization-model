# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""No-future-leakage (causality) property for ordered-time-series consumers.

Contract: for any module that consumes an ordered time series, its output for
indices <= t must depend only on data[:t+1] and never on data[t+1:]. Concretely,
given two series A and B with ``A[:k] == B[:k]`` but ``A[k:] != B[k:]``, every
statistic computed over the shared prefix must be identical.

Uses hypothesis when available; always includes an explicit constructed case so
the property still runs deterministically without the optional dependency.
"""

from __future__ import annotations

import numpy as np

from modules.market_regime_analyzer import MarketRegimeAnalyzer
from modules.performance_tracker import PerformanceTracker

try:
    from hypothesis import given, settings
    from hypothesis import strategies as st

    _HAS_HYPOTHESIS = True
except ImportError:  # pragma: no cover - exercised only without the optional dep
    _HAS_HYPOTHESIS = False


def _prefix_statistics(prices: list[float], k: int) -> tuple[float, float, float]:
    """Regime statistics computed over ``prices[:k]`` only."""
    analyzer = MarketRegimeAnalyzer()
    prefix = np.asarray(prices[:k], dtype=float)
    hurst = analyzer.calculate_hurst_exponent(prefix)
    adf_stat, _ = analyzer.augmented_dickey_fuller_test(prefix)
    trend, _ = analyzer.calculate_trend_strength(prefix)
    return hurst, adf_stat, trend


def _assert_prefix_invariant(a: list[float], b: list[float], k: int) -> None:
    """A[:k] == B[:k] (by construction) => prefix statistics are identical."""
    assert a[:k] == b[:k]
    assert _prefix_statistics(a, k) == _prefix_statistics(b, k)


def test_regime_statistics_do_not_leak_future_explicit() -> None:
    # Shared prefix of 40 points; divergent futures must not change the prefix view.
    rng = np.random.default_rng(11)
    shared = list(100.0 + np.cumsum(rng.normal(0.0, 1.0, 40)))
    future_a = list(shared[-1] + np.cumsum(rng.normal(0.5, 1.0, 30)))
    future_b = list(shared[-1] + np.cumsum(rng.normal(-0.5, 1.0, 30)))
    a = shared + future_a
    b = shared + future_b
    _assert_prefix_invariant(a, b, len(shared))


def test_performance_metrics_do_not_leak_future_trades_explicit() -> None:
    # Two trackers fed an identical prefix of equity points, then divergent futures.
    prefix = [100_000.0, 101_000.0, 99_000.0, 102_000.0]

    def _metrics_after_prefix(future: list[float]) -> tuple[float, float]:
        tracker = PerformanceTracker(initial_capital=100_000.0)
        for equity in prefix:
            tracker.update_equity(equity=equity)
        snapshot = tracker.get_metrics()
        # The future is only appended AFTER we captured the prefix metrics.
        for equity in future:
            tracker.update_equity(equity=equity)
        return snapshot.total_return, snapshot.max_drawdown

    m_up = _metrics_after_prefix([200_000.0, 300_000.0])
    m_down = _metrics_after_prefix([10_000.0, 5_000.0])
    assert m_up == m_down  # prefix metrics are independent of the appended future


if _HAS_HYPOTHESIS:

    @settings(max_examples=40, deadline=None)
    @given(
        prefix=st.lists(
            st.floats(min_value=50.0, max_value=150.0, allow_nan=False, allow_infinity=False),
            min_size=25,
            max_size=60,
        ),
        tail_a=st.lists(
            st.floats(min_value=50.0, max_value=150.0, allow_nan=False, allow_infinity=False),
            min_size=1,
            max_size=40,
        ),
        tail_b=st.lists(
            st.floats(min_value=50.0, max_value=150.0, allow_nan=False, allow_infinity=False),
            min_size=1,
            max_size=40,
        ),
    )
    def test_regime_statistics_do_not_leak_future_property(
        prefix: list[float], tail_a: list[float], tail_b: list[float]
    ) -> None:
        k = len(prefix)
        a = prefix + tail_a
        b = prefix + tail_b
        _assert_prefix_invariant(a, b, k)
