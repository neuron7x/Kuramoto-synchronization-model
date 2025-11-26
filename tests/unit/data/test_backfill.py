from __future__ import annotations

from datetime import UTC

import pandas as pd
import pytest

from core.data.backfill import (
    CacheKey,
    CacheRegistry,
    Gap,
    GapFillPlanner,
    LayerCache,
    detect_gaps,
    normalise_index,
)


def _sample_frame(
    start: str = "2024-01-01 00:00:00", *, periods: int = 4
) -> pd.DataFrame:
    index = pd.date_range(start=start, periods=periods, freq="1min", tz=UTC)
    return pd.DataFrame({"value": range(periods)}, index=index)


def test_layer_cache_roundtrip() -> None:
    cache = LayerCache()
    key = CacheKey(layer="raw", symbol="BTC", venue="XNYS", timeframe="1min")
    frame = _sample_frame()

    cache.put(key, frame)
    retrieved = cache.get(key)
    assert retrieved.equals(frame)
    coverage = cache.coverage(key)
    assert coverage is not None
    assert coverage.left == frame.index.min()
    assert coverage.right == frame.index.max()


def test_layer_cache_validates_index_type() -> None:
    cache = LayerCache()
    key = CacheKey(layer="raw", symbol="BTC", venue="XNYS", timeframe="1min")
    frame = pd.DataFrame({"value": [1, 2]}, index=[0, 1])

    with pytest.raises(TypeError):
        cache.put(key, frame)


def test_layer_cache_ignores_empty_payload() -> None:
    cache = LayerCache()
    key = CacheKey(layer="raw", symbol="BTC", venue="XNYS", timeframe="1min")
    empty = _sample_frame(periods=0)

    cache.put(key, empty)
    assert cache.get(key).empty


def test_layer_cache_delete_removes_entries() -> None:
    cache = LayerCache()
    key = CacheKey(layer="raw", symbol="BTC", venue="XNYS", timeframe="1min")
    frame = _sample_frame()

    cache.put(key, frame)
    assert cache.delete(key) is True
    assert cache.get(key).empty
    assert cache.coverage(key) is None
    assert cache.delete(key) is False


def test_gap_validation_and_detection() -> None:
    start = pd.Timestamp("2024-01-01 00:00:00", tz=UTC)
    with pytest.raises(ValueError):
        Gap(start=start, end=start)

    expected = pd.date_range(start=start, periods=5, freq="1min", tz=UTC)
    existing = expected.delete([1, 2])

    gaps = detect_gaps(expected, existing)
    assert len(gaps) == 1
    assert gaps[0].start == expected[1]
    assert gaps[0].end == expected[2] + pd.Timedelta(minutes=1)


def test_detect_gaps_requires_frequency_override_for_irregular_index() -> None:
    """Irregular indices must supply an explicit cadence for gap detection."""

    expected = pd.DatetimeIndex(
        [
            pd.Timestamp("2024-01-01 00:00:00", tz=UTC),
            pd.Timestamp("2024-01-01 00:01:00", tz=UTC),
            pd.Timestamp("2024-01-01 00:03:00", tz=UTC),
        ]
    )
    existing = expected.delete(1)

    with pytest.raises(
        ValueError, match="Unable to determine expected_index frequency"
    ):
        detect_gaps(expected, existing)

    gaps = detect_gaps(expected, existing, frequency="1min")
    assert len(gaps) == 1
    assert gaps[0].start == pd.Timestamp("2024-01-01 00:01:00", tz=UTC)
    assert gaps[0].end == pd.Timestamp("2024-01-01 00:02:00", tz=UTC)


def test_gap_fill_planner_full_refresh_and_apply() -> None:
    cache = LayerCache()
    planner = GapFillPlanner(cache)
    key = CacheKey(layer="raw", symbol="ETH", venue="XNAS", timeframe="1min")
    expected = pd.date_range("2024-01-01", periods=3, freq="1min", tz=UTC)

    plan = planner.plan(key, expected_index=expected)
    assert plan.is_full_refresh is True
    assert plan.gaps[0].start == expected[0]

    new_data = _sample_frame(periods=3)
    planner.apply(key, new_data)
    cached = cache.get(key)
    assert cached.shape[0] == 3

    # Subsequent planning should reuse existing coverage and detect no gaps.
    follow_up = planner.plan(key, expected_index=expected)
    assert not follow_up.gaps
    assert isinstance(follow_up.covered, pd.Interval)


def test_gap_fill_planner_merges_newer_data() -> None:
    cache = LayerCache()
    planner = GapFillPlanner(cache)
    key = CacheKey(layer="features", symbol="ETH", venue="XNAS", timeframe="1min")

    baseline = _sample_frame()
    planner.apply(key, baseline.iloc[:2])
    planner.apply(key, baseline.iloc[2:])

    combined = cache.get(key)
    assert combined.equals(baseline)


def test_cache_registry_routing() -> None:
    registry = CacheRegistry()
    assert isinstance(registry.cache_for("raw"), LayerCache)
    assert isinstance(registry.cache_for("ohlcv"), LayerCache)
    assert isinstance(registry.cache_for("features"), LayerCache)

    with pytest.raises(ValueError):
        registry.cache_for("unknown")


def test_normalise_index_validates_and_normalises() -> None:
    frame = _sample_frame().tz_localize(None)

    normalized = normalise_index(frame)
    assert normalized.index.tz == UTC
    assert normalized.index.is_monotonic_increasing

    with pytest.raises(TypeError):
        normalise_index(pd.DataFrame({"value": [1]}, index=["not-a-date"]))

    empty = pd.DataFrame(columns=["value"])
    result = normalise_index(empty)
    assert result.empty
