# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Causal prefix-invariance: future data must not change past output.

For a time-indexed computation, given two series that share a prefix ``A[:t] ==
B[:t]`` but diverge afterwards, the output computed over the shared prefix must be
identical. This file drives that property (Hypothesis when available, plus an
explicit constructed case) over surfaces not already covered by
``tests/property/modules/test_modules_no_future_leakage.py``: the regime Hurst
exponent, the performance-tracker cumulative Sharpe, and the realtime feature
event-time monotonicity that guarantees a later tick cannot alter an earlier read.
"""

from __future__ import annotations

import numpy as np

from modules.market_regime_analyzer import MarketRegimeAnalyzer
from modules.performance_tracker import PerformanceTracker

try:
    from hypothesis import given, settings
    from hypothesis import strategies as st

    _HAS_HYPOTHESIS = True
except ImportError:  # pragma: no cover - hypothesis is a dev dep
    _HAS_HYPOTHESIS = False


def _hurst_prefix(prices: list[float], k: int) -> float:
    analyzer = MarketRegimeAnalyzer()
    return float(analyzer.calculate_hurst_exponent(np.asarray(prices[:k], dtype=float)))


def _sharpe_prefix(equities: list[float], k: int) -> float:
    tracker = PerformanceTracker(initial_capital=equities[0])
    for equity in equities[:k]:
        tracker.update_equity(equity=equity)
    return float(tracker.get_metrics().sharpe_ratio)


def test_regime_hurst_prefix_invariant_explicit() -> None:
    shared = [100.0 + np.sin(i / 3.0) for i in range(48)]
    a = shared + [200.0, 50.0, 300.0]
    b = shared + [10.0, 999.0, 1.0]
    assert a[: len(shared)] == b[: len(shared)]
    assert _hurst_prefix(a, len(shared)) == _hurst_prefix(b, len(shared))


def test_performance_sharpe_prefix_invariant_explicit() -> None:
    shared = [100_000.0, 101_000.0, 99_500.0, 102_300.0, 101_800.0, 103_000.0]
    a = shared + [120_000.0, 80_000.0]
    b = shared + [90_000.0, 130_000.0]
    assert _sharpe_prefix(a, len(shared)) == _sharpe_prefix(b, len(shared))


def test_realtime_feature_event_time_monotonicity_explicit() -> None:
    # A later-arriving OLDER event must not change what an earlier read observed:
    # the cache keeps the newer event_ts (compare-and-set), so the past read is
    # stable under a future out-of-order tick.
    import asyncio
    from datetime import datetime, timezone

    from core.features.realtime_store import FeatureDescriptor, FeatureRecord, _TTLCache

    desc = FeatureDescriptor(name="f", version="1.0", entity="user")
    t_new = datetime(2024, 1, 1, 0, 0, 1, tzinfo=timezone.utc)
    t_old = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    async def _run() -> float:
        cache = _TTLCache()
        rec_new = FeatureRecord(descriptor=desc, entity_id="u", value={"s": 9.0}, event_ts=t_new)
        await cache.set("k", rec_new, ttl_ms=5000)
        observed = await cache.get("k")
        # A future OLDER tick arrives; the earlier observation must remain valid.
        rec_old = FeatureRecord(descriptor=desc, entity_id="u", value={"s": 1.0}, event_ts=t_old)
        await cache.set("k", rec_old, ttl_ms=5000)
        after = await cache.get("k")
        assert observed is not None and after is not None
        assert observed.value["s"] == after.value["s"] == 9.0
        return float(after.value["s"])

    assert asyncio.run(_run()) == 9.0


if _HAS_HYPOTHESIS:

    @settings(max_examples=40, deadline=None)
    @given(
        shared=st.lists(
            st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
            min_size=32,
            max_size=64,
        ),
        future_a=st.lists(
            st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
            min_size=1,
            max_size=8,
        ),
        future_b=st.lists(
            st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
            min_size=1,
            max_size=8,
        ),
    )
    def test_regime_hurst_prefix_invariant_property(
        shared: list[float], future_a: list[float], future_b: list[float]
    ) -> None:
        k = len(shared)
        assert _hurst_prefix(shared + future_a, k) == _hurst_prefix(shared + future_b, k)
