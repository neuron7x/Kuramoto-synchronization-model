# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from core.data.backfill import CacheRegistry, GapFillPlanner
from core.data.ingestion import DataIngestor
from core.data.models import InstrumentType
from core.data.models import PriceTick as Ticker
from src.data.ingestion_service import DataIngestionCacheService


class _Clock:
    def __init__(self, *values: datetime) -> None:
        self._values = iter(values)

    def __call__(self) -> datetime:
        return next(self._values)


def _tick(
    base: datetime,
    *,
    offset: int,
    price: float,
    symbol: str = "BTCUSD",
    venue: str = "BINANCE",
    step: timedelta = timedelta(minutes=1),
) -> Ticker:
    return Ticker.create(
        symbol=symbol,
        venue=venue,
        price=price,
        timestamp=base + offset * step,
        volume=1.0,
        instrument_type=InstrumentType.SPOT,
    )


def test_gap_fill_planner_detects_and_fills_missing_ranges() -> None:
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    ticks = [_tick(base, offset=i, price=100.0 + i) for i in range(5)]
    partial = ticks[:3]
    clock = _Clock(
        datetime(2024, 1, 2, tzinfo=timezone.utc),
        datetime(2024, 1, 3, tzinfo=timezone.utc),
    )
    registry = CacheRegistry()
    service = DataIngestionCacheService(cache_registry=registry, clock=clock)

    cached = service.cache_ticks(
        partial,
        layer="raw",
        symbol="BTCUSD",
        venue="BINANCE",
        timeframe="1min",
    )
    assert cached.shape[0] == len(partial)

    metadata = service.metadata_for(
        layer="raw",
        symbol="BTCUSD",
        venue="BINANCE",
        timeframe="1min",
    )
    assert metadata is not None
    key = metadata.key

    expected_index = pd.date_range(
        start=ticks[0].timestamp,
        periods=len(ticks),
        freq="1min",
        tz="UTC",
    )

    planner = GapFillPlanner(registry.cache_for("raw"))
    plan = planner.plan(key, expected_index=expected_index)

    assert plan.covered is not None
    assert plan.covered.left.to_pydatetime() == partial[0].timestamp
    assert plan.covered.right.to_pydatetime() == partial[-1].timestamp
    assert len(plan.gaps) == 1
    assert plan.gaps[0].start.to_pydatetime() == ticks[len(partial)].timestamp

    # Cache the complete dataset and ensure the planner observes full coverage.
    service.cache_ticks(
        ticks,
        layer="raw",
        symbol="BTCUSD",
        venue="BINANCE",
        timeframe="1min",
    )

    refreshed = service.metadata_for(
        layer="raw",
        symbol="BTCUSD",
        venue="BINANCE",
        timeframe="1min",
    )
    assert refreshed is not None
    assert refreshed.rows == len(ticks)

    plan_after_fill = planner.plan(key, expected_index=expected_index)

    assert plan_after_fill.covered is not None
    assert plan_after_fill.covered.left.to_pydatetime() == ticks[0].timestamp
    assert plan_after_fill.covered.right.to_pydatetime() == ticks[-1].timestamp
    assert plan_after_fill.gaps == []


def test_ingest_csv_caches_frame_and_supports_range_queries() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    csv_path = repo_root / "data" / "sample.csv"
    snapshot_time = datetime(2024, 1, 4, tzinfo=timezone.utc)

    service = DataIngestionCacheService(
        data_ingestor=DataIngestor(allowed_roots=[csv_path.parent]),
        clock=lambda: snapshot_time,
    )

    frame = service.ingest_csv(
        str(csv_path),
        symbol="BTCUSD",
        venue="CSV",
        timeframe="1s",
        layer="raw",
    )

    assert not frame.empty
    assert frame.index.tz is not None

    metadata = service.metadata_for(
        layer="raw",
        symbol="BTCUSD",
        venue="CSV",
        timeframe="1s",
    )

    assert metadata is not None
    assert metadata.rows == frame.shape[0]
    assert metadata.start == frame.index.min().to_pydatetime()
    assert metadata.end == frame.index.max().to_pydatetime()
    assert metadata.last_updated == snapshot_time
    assert metadata.key.symbol == "BTC/USD"
    assert metadata.key.venue == "CSV"

    start = frame.index[5].to_pydatetime()
    end = frame.index[8].to_pydatetime()
    sliced = service.get_cached_frame(
        layer="raw",
        symbol="BTCUSD",
        venue="CSV",
        timeframe="1s",
        start=start,
        end=end,
    )

    expected_slice = frame.loc[frame.index[(frame.index >= start) & (frame.index <= end)]]
    pd.testing.assert_frame_equal(sliced, expected_slice)

    snapshot = service.cache_snapshot()
    assert snapshot == [metadata]
