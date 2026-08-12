# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import UTC

import pandas as pd

from core.data.backfill import (
    BackfillPayload,
    BackfillPlanner,
    CacheKey,
    LayerCache,
)


def _frame(start: str, *, periods: int, freq: str = "1min") -> pd.DataFrame:
    index = pd.date_range(start=start, periods=periods, freq=freq, tz=UTC)
    return pd.DataFrame({"value": range(periods)}, index=index)


def _checksum(frame: pd.DataFrame) -> str:
    hashed = pd.util.hash_pandas_object(frame, index=True).values
    return hashlib.sha256(hashed.tobytes()).hexdigest()


def test_backfill_planner_recovers_all_gaps_with_retries() -> None:
    cache = LayerCache()
    planner = BackfillPlanner(cache, max_workers=2, segment_size=5, max_retries=2)
    key = CacheKey(layer="raw", symbol="BTC", venue="XNAS", timeframe="1min")

    dataset = _frame("2024-01-01", periods=30)
    expected_index = dataset.index

    failures: defaultdict[pd.Timestamp, int] = defaultdict(int)

    def loader(_: CacheKey, start: pd.Timestamp, end: pd.Timestamp) -> BackfillPayload:
        segment_index = expected_index[
            (expected_index >= start) & (expected_index < end)
        ]
        frame = dataset.loc[segment_index]
        failures[start] += 1
        if start == expected_index[10] and failures[start] < 2:
            raise RuntimeError("transient network error")
        return BackfillPayload(frame=frame, checksum=_checksum(frame))

    result = planner.backfill(key, expected_index=expected_index, loader=loader)

    assert result.success
    assert result.progress.completion_ratio == 1.0
    assert result.progress.bytes_transferred > 0
    assert not result.failed_segments
    assert len(result.completed_segments) == len(result.plan.segments)

    cached = cache.get(key)
    assert cached.equals(dataset)


def test_backfill_planner_records_checksum_failures() -> None:
    cache = LayerCache()
    planner = BackfillPlanner(cache, max_workers=1, segment_size=10, max_retries=0)
    key = CacheKey(layer="raw", symbol="ETH", venue="XNAS", timeframe="1min")

    dataset = _frame("2024-01-01", periods=12)
    expected_index = dataset.index

    def loader(_: CacheKey, start: pd.Timestamp, end: pd.Timestamp) -> BackfillPayload:
        segment_index = expected_index[
            (expected_index >= start) & (expected_index < end)
        ]
        frame = dataset.loc[segment_index]
        return BackfillPayload(frame=frame, checksum="invalid")

    result = planner.backfill(key, expected_index=expected_index, loader=loader)

    assert not result.success
    assert result.failed_segments
    assert result.errors
    assert "Checksum mismatch" in result.errors[0].message
    assert result.progress.failed_segments == result.progress.total_segments


def test_backfill_planner_validates_loader_payload() -> None:
    cache = LayerCache()
    planner = BackfillPlanner(cache, max_workers=1, segment_size=5, max_retries=1)
    key = CacheKey(layer="raw", symbol="SOL", venue="XNAS", timeframe="1min")

    dataset = _frame("2024-01-01", periods=10)
    expected_index = dataset.index

    def loader(_: CacheKey, start: pd.Timestamp, end: pd.Timestamp) -> BackfillPayload:
        segment_index = expected_index[
            (expected_index >= start) & (expected_index < end)
        ]
        frame = dataset.loc[segment_index]
        # Drop a row to trigger validation
        frame = frame.iloc[:-1]
        return BackfillPayload(frame=frame, checksum=_checksum(frame))

    result = planner.backfill(key, expected_index=expected_index, loader=loader)

    assert not result.success
    assert result.failed_segments
    assert any("missing timestamps" in error.message for error in result.errors)
