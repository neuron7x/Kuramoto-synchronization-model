# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import pandas as pd

from core.compat import UTC
from core.data.backfill import CacheKey, CacheRegistry, GapFillPlanner, normalise_index


def _make_frame(start: str, periods: int) -> pd.DataFrame:
    index = pd.date_range(start=start, periods=periods, freq="1min", tz=UTC)
    return pd.DataFrame({"value": range(periods)}, index=index)


def test_gap_detection_and_recovery_with_registry():
    registry = CacheRegistry()
    key = CacheKey(layer="raw", symbol="BTC", venue="TEST", timeframe="1min")
    planner = GapFillPlanner(registry.cache_for("raw"))

    baseline = _make_frame("2024-01-01 00:00", periods=10)
    initial_payload = baseline.drop(baseline.index[3:6])
    registry.raw.put(key, normalise_index(initial_payload.tz_localize(None)))

    expected_index = baseline.index
    plan = planner.plan(key, expected_index=expected_index)
    assert len(plan.gaps) == 1
    gap = plan.gaps[0]
    assert gap.start == expected_index[3]
    assert gap.end == expected_index[5] + expected_index.freq
    assert plan.covered is not None

    recovery = baseline.loc[gap.start : gap.end - expected_index.freq]
    planner.apply(key, recovery)

    cached = registry.raw.get(key)
    assert cached.index.equals(expected_index)
    assert cached.equals(baseline)

    follow_up = planner.plan(key, expected_index=expected_index)
    assert not follow_up.gaps
    assert follow_up.covered is not None
    assert follow_up.covered.left == expected_index[0]
    assert follow_up.covered.right == expected_index[-1]
