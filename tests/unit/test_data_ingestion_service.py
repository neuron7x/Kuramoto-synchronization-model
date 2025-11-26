from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from core.data.backfill import CacheKey, CacheRegistry
from core.data.ingestion import DataIngestor
from core.data.models import InstrumentType
from core.data.models import PriceTick as Ticker
from src.data.ingestion_service import (
    CacheEntrySnapshot,
    DataIngestionCacheService,
    DataIntegrityError,
)


def _tick(
    ts: datetime,
    price: float,
    *,
    symbol: str = "BTCUSD",
    venue: str = "BINANCE",
    instrument_type: InstrumentType = InstrumentType.SPOT,
) -> Ticker:
    return Ticker.create(
        symbol=symbol,
        venue=venue,
        price=price,
        timestamp=ts,
        volume=1.0,
        instrument_type=instrument_type,
    )


class _Clock:
    def __init__(self, *values: datetime) -> None:
        self._values = iter(values)

    def __call__(self) -> datetime:
        return next(self._values)


def test_cache_ticks_records_metadata() -> None:
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    ticks = [_tick(base.replace(minute=i), 100.0 + i) for i in range(3)]
    clock = _Clock(
        datetime(2024, 1, 2, tzinfo=timezone.utc),
    )
    service = DataIngestionCacheService(clock=clock)

    cached = service.cache_ticks(
        ticks, layer="raw", symbol="BTCUSD", venue="BINANCE", timeframe="1min"
    )

    assert isinstance(cached, pd.DataFrame)
    assert list(cached.columns) == ["price", "volume"]
    metadata = service.metadata_for(
        layer="raw", symbol="BTCUSD", venue="BINANCE", timeframe="1min"
    )
    assert isinstance(metadata, CacheEntrySnapshot)
    assert metadata.rows == 3
    assert metadata.start == ticks[0].timestamp
    assert metadata.end == ticks[-1].timestamp
    assert metadata.last_updated == datetime(2024, 1, 2, tzinfo=timezone.utc)
    assert metadata.key.symbol == "BTC/USD"


def test_cache_ticks_validates_symbol_and_venue() -> None:
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    ticks = [_tick(base, 100.0), _tick(base.replace(minute=1), 101.0, venue="OTHER")]
    service = DataIngestionCacheService()

    with pytest.raises(ValueError):
        service.cache_ticks(
            ticks, layer="raw", symbol="BTCUSD", venue="BINANCE", timeframe="1min"
        )


def test_cache_ticks_rejects_mixed_instrument_types() -> None:
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    ticks = [
        _tick(base, 100.0, instrument_type=InstrumentType.SPOT),
        _tick(
            base.replace(minute=1),
            101.0,
            instrument_type=InstrumentType.FUTURES,
        ),
    ]
    service = DataIngestionCacheService()

    with pytest.raises(ValueError, match="instrument type"):
        service.cache_ticks(
            ticks,
            layer="raw",
            symbol="BTCUSD",
            venue="BINANCE",
            timeframe="1min",
        )


def test_cache_frame_rejects_nan_values() -> None:
    index = pd.DatetimeIndex(
        [
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 1, 1, minute=1, tzinfo=timezone.utc),
        ]
    )
    frame = pd.DataFrame(
        {"price": [100.0, float("nan")], "volume": [1.0, 2.0]}, index=index
    )
    service = DataIngestionCacheService()

    with pytest.raises(DataIntegrityError, match="NaN"):
        service.cache_frame(
            frame,
            layer="raw",
            symbol="BTCUSD",
            venue="BINANCE",
            timeframe="1min",
        )


def test_cache_frame_rejects_duplicate_timestamps() -> None:
    ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    index = pd.DatetimeIndex([ts, ts])
    frame = pd.DataFrame({"price": [100.0, 101.0], "volume": [1.0, 2.0]}, index=index)
    service = DataIngestionCacheService()

    with pytest.raises(DataIntegrityError, match="duplicate"):
        service.cache_frame(
            frame,
            layer="raw",
            symbol="BTCUSD",
            venue="BINANCE",
            timeframe="1min",
        )


def test_cache_frame_rejects_frequency_mismatch() -> None:
    index = pd.DatetimeIndex(
        [
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 1, 1, minute=2, tzinfo=timezone.utc),
        ]
    )
    frame = pd.DataFrame({"price": [100.0, 101.0], "volume": [1.0, 2.0]}, index=index)
    service = DataIngestionCacheService()

    with pytest.raises(DataIntegrityError, match="frequency"):
        service.cache_frame(
            frame,
            layer="features",
            symbol="BTCUSD",
            venue="BINANCE",
            timeframe="1min",
        )


def test_get_cached_frame_supports_ranges() -> None:
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    ticks = [_tick(base.replace(minute=i), 100.0 + i) for i in range(5)]
    service = DataIngestionCacheService()
    service.cache_ticks(
        ticks, layer="raw", symbol="BTCUSD", venue="BINANCE", timeframe="1min"
    )

    subset = service.get_cached_frame(
        layer="raw",
        symbol="BTCUSD",
        venue="BINANCE",
        timeframe="1min",
        start=ticks[2].timestamp,
        end=ticks[4].timestamp,
    )

    assert subset.shape[0] == 3
    assert subset.index[0] == ticks[2].timestamp
    assert subset.index[-1] == ticks[4].timestamp


def test_cache_ticks_rejects_blank_timeframe() -> None:
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    ticks = [_tick(base.replace(minute=i), 100.0 + i) for i in range(2)]
    service = DataIngestionCacheService()

    with pytest.raises(ValueError, match="timeframe must be a non-empty string"):
        service.cache_ticks(
            ticks, layer="raw", symbol="BTCUSD", venue="BINANCE", timeframe="   "
        )


def test_cache_ticks_rejects_empty_sequence() -> None:
    service = DataIngestionCacheService()

    with pytest.raises(ValueError, match="ticks must not be empty"):
        service.cache_ticks(
            [],
            layer="raw",
            symbol="BTCUSD",
            venue="BINANCE",
            timeframe="1min",
        )


def test_cache_frame_normalises_timezone_naive_index() -> None:
    index = pd.DatetimeIndex(
        [
            datetime(2024, 1, 1, 0, 0),
            datetime(2024, 1, 1, 0, 1),
            datetime(2024, 1, 1, 0, 2),
        ]
    )
    frame = pd.DataFrame(
        {"price": [100.0, 101.0, 102.0], "volume": [1.0, 1.0, 1.0]}, index=index
    )
    service = DataIngestionCacheService()

    cached = service.cache_frame(
        frame,
        layer="raw",
        symbol="ETHUSD",
        venue="BINANCE",
        timeframe="1min",
    )

    assert cached.index.tz is not None
    assert cached.index.tz.tzname(None) == "UTC"
    assert cached.index.is_monotonic_increasing
    metadata = service.metadata_for(
        layer="raw", symbol="ETHUSD", venue="BINANCE", timeframe="1min"
    )
    assert metadata is not None and metadata.rows == 3


def test_cache_frame_requires_datetime_index() -> None:
    frame = pd.DataFrame(
        {"price": [100.0, 101.0], "volume": [1.0, 2.0]},
        index=pd.Index([0, 1], name="timestamp"),
    )
    service = DataIngestionCacheService()

    with pytest.raises(TypeError, match="DatetimeIndex"):
        service.cache_frame(
            frame,
            layer="raw",
            symbol="BTCUSD",
            venue="BINANCE",
            timeframe="1min",
        )


def test_cache_frame_rejects_non_numeric_values() -> None:
    index = pd.DatetimeIndex(
        [
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 1, 1, minute=1, tzinfo=timezone.utc),
        ]
    )
    frame = pd.DataFrame(
        {"price": ["100.0", "invalid"], "volume": [1.0, 2.0]}, index=index
    )
    service = DataIngestionCacheService()

    with pytest.raises(DataIntegrityError, match="non-numeric"):
        service.cache_frame(
            frame,
            layer="raw",
            symbol="BTCUSD",
            venue="BINANCE",
            timeframe="1min",
        )


def test_cache_frame_rejects_non_finite_values() -> None:
    index = pd.DatetimeIndex(
        [
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 1, 1, minute=1, tzinfo=timezone.utc),
        ]
    )
    frame = pd.DataFrame({"price": [100.0, np.inf], "volume": [1.0, 2.0]}, index=index)
    service = DataIngestionCacheService()

    with pytest.raises(DataIntegrityError, match="non-finite"):
        service.cache_frame(
            frame,
            layer="raw",
            symbol="BTCUSD",
            venue="BINANCE",
            timeframe="1min",
        )


def test_cache_frame_accepts_unparseable_feature_frequency() -> None:
    index = pd.date_range(
        start=datetime(2024, 1, 1, tzinfo=timezone.utc),
        periods=4,
        freq="5min",
    )
    frame = pd.DataFrame({"price": [100.0, 101.0, 102.0, 103.0]}, index=index)
    service = DataIngestionCacheService()

    cached = service.cache_frame(
        frame,
        layer="features",
        symbol="ETHUSD",
        venue="BINANCE",
        timeframe="not-a-timedelta",
    )

    assert cached.index.equals(index)


def test_get_cached_frame_coerces_boundary_timezones() -> None:
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    ticks = [_tick(base.replace(minute=i), 100.0 + i) for i in range(5)]
    service = DataIngestionCacheService()
    service.cache_ticks(
        ticks, layer="raw", symbol="BTCUSD", venue="BINANCE", timeframe="1min"
    )

    start = datetime(2024, 1, 1, 0, 1)
    end = datetime(2024, 1, 1, 2, 3, tzinfo=timezone(timedelta(hours=2)))

    subset = service.get_cached_frame(
        layer="raw",
        symbol="BTCUSD",
        venue="BINANCE",
        timeframe="1min",
        start=start,
        end=end,
    )

    assert list(subset.index) == [
        ticks[1].timestamp,
        ticks[2].timestamp,
        ticks[3].timestamp,
    ]


def test_cache_frame_records_empty_frame_metadata() -> None:
    frame = pd.DataFrame(
        columns=["price", "volume"],
        index=pd.DatetimeIndex([], tz="UTC"),
    )
    service = DataIngestionCacheService()

    cached = service.cache_frame(
        frame,
        layer="raw",
        symbol="BTCUSD",
        venue="BINANCE",
        timeframe="1min",
    )

    assert cached.empty
    metadata = service.metadata_for(
        layer="raw", symbol="BTCUSD", venue="BINANCE", timeframe="1min"
    )
    assert metadata is not None
    assert metadata.rows == 0
    assert metadata.start is None and metadata.end is None


def test_ingest_csv_populates_cache(tmp_path: Path) -> None:
    csv_path = tmp_path / "prices.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["ts", "price", "volume"])
        writer.writeheader()
        writer.writerow({"ts": 1.0, "price": "100.0", "volume": "2"})
        writer.writerow({"ts": 2.0, "price": "101.5", "volume": "3"})

    service = DataIngestionCacheService(
        data_ingestor=DataIngestor(allowed_roots=[tmp_path]),
        clock=_Clock(datetime(2024, 1, 3, tzinfo=timezone.utc)),
    )

    frame = service.ingest_csv(
        str(csv_path),
        symbol="BTCUSD",
        venue="CSV",
        timeframe="1min",
        layer="raw",
    )

    assert frame.shape[0] == 2
    metadata = service.metadata_for(
        layer="raw", symbol="BTCUSD", venue="CSV", timeframe="1min"
    )
    assert metadata is not None
    assert metadata.rows == 2
    assert metadata.start == frame.index.min().to_pydatetime()


def test_cache_snapshot_returns_sorted_entries() -> None:
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    ticks = [_tick(base.replace(minute=i), 100.0 + i) for i in range(2)]
    clock = _Clock(
        datetime(2024, 1, 5, tzinfo=timezone.utc),
        datetime(2024, 1, 6, tzinfo=timezone.utc),
    )
    service = DataIngestionCacheService(clock=clock)
    service.cache_ticks(
        ticks, layer="raw", symbol="BTCUSD", venue="BINANCE", timeframe="1min"
    )
    feature_ticks = [_tick(base.replace(minute=i * 5), 100.0 + i) for i in range(2)]
    service.cache_ticks(
        feature_ticks,
        layer="features",
        symbol="BTCUSD",
        venue="BINANCE",
        timeframe="5min",
    )

    snapshot = service.cache_snapshot()

    assert [entry.key.layer for entry in snapshot] == ["features", "raw"]
    times_by_layer = {entry.key.layer: entry.last_updated for entry in snapshot}
    assert times_by_layer["raw"] < times_by_layer["features"]


def test_delete_cached_frame_evicts_dataset_and_metadata() -> None:
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    ticks = [_tick(base.replace(minute=i), 100.0 + i) for i in range(3)]
    service = DataIngestionCacheService()
    service.cache_ticks(
        ticks, layer="raw", symbol="BTCUSD", venue="BINANCE", timeframe="1min"
    )

    removed = service.delete_cached_frame(
        layer="raw", symbol="BTCUSD", venue="BINANCE", timeframe="1min"
    )

    assert removed is True
    assert (
        service.metadata_for(
            layer="raw", symbol="BTCUSD", venue="BINANCE", timeframe="1min"
        )
        is None
    )
    assert service.get_cached_frame(
        layer="raw", symbol="BTCUSD", venue="BINANCE", timeframe="1min"
    ).empty


def test_delete_cached_frame_handles_missing_entries() -> None:
    service = DataIngestionCacheService()

    removed = service.delete_cached_frame(
        layer="raw", symbol="MISSING", venue="BINANCE", timeframe="1min"
    )

    assert removed is False


def test_delete_cached_frame_removes_metadata_only_entry() -> None:
    frame = pd.DataFrame(
        columns=["price", "volume"], index=pd.DatetimeIndex([], tz="UTC")
    )
    service = DataIngestionCacheService()
    service.cache_frame(
        frame,
        layer="raw",
        symbol="BTCUSD",
        venue="BINANCE",
        timeframe="1min",
    )

    removed = service.delete_cached_frame(
        layer="raw", symbol="BTCUSD", venue="BINANCE", timeframe="1min"
    )

    assert removed is True
    assert (
        service.metadata_for(
            layer="raw", symbol="BTCUSD", venue="BINANCE", timeframe="1min"
        )
        is None
    )


def test_metadata_for_unknown_key_returns_none() -> None:
    service = DataIngestionCacheService()
    assert (
        service.metadata_for(layer="raw", symbol="AAA", venue="BBB", timeframe="1min")
        is None
    )


def test_clear_resets_registry_and_metadata() -> None:
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    ticks = [_tick(base.replace(minute=i), 100.0 + i) for i in range(3)]
    service = DataIngestionCacheService()
    original_registry = service.cache_registry

    service.cache_ticks(
        ticks, layer="raw", symbol="BTCUSD", venue="BINANCE", timeframe="1min"
    )

    assert service.cache_snapshot()

    service.clear()

    assert not service.cache_snapshot()
    assert service.cache_registry is not original_registry
    assert (
        service.metadata_for(
            layer="raw", symbol="BTCUSD", venue="BINANCE", timeframe="1min"
        )
        is None
    )


def test_rebuild_metadata_hydrates_registry_state() -> None:
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    frame = pd.DataFrame(
        {"price": [100.0, 101.0], "volume": [1.0, 2.0]},
        index=pd.DatetimeIndex([base, base + timedelta(minutes=1)], tz="UTC"),
    )
    registry = CacheRegistry()
    key = CacheKey(layer="raw", symbol="BTC/USD", venue="BINANCE", timeframe="1min")
    registry.cache_for("raw").put(key, frame)

    clock = _Clock(datetime(2024, 1, 2, tzinfo=timezone.utc))
    service = DataIngestionCacheService(cache_registry=registry, clock=clock)

    snapshots = service.rebuild_metadata()

    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot.key == key
    assert snapshot.rows == 2
    assert snapshot.start == base
    assert snapshot.end == base + timedelta(minutes=1)
    assert snapshot.last_updated == datetime(2024, 1, 2, tzinfo=timezone.utc)
    assert (
        service.metadata_for(
            layer="raw", symbol="BTC/USD", venue="BINANCE", timeframe="1min"
        )
        == snapshot
    )


def test_rebuild_metadata_overwrites_stale_entries() -> None:
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    ticks = [_tick(base + timedelta(minutes=i), 100.0 + i) for i in range(2)]
    clock = _Clock(
        datetime(2024, 1, 2, tzinfo=timezone.utc),
        datetime(2024, 1, 3, tzinfo=timezone.utc),
    )
    service = DataIngestionCacheService(clock=clock)
    service.cache_ticks(
        ticks,
        layer="raw",
        symbol="BTCUSD",
        venue="BINANCE",
        timeframe="1min",
    )

    registry = service.cache_registry
    registry.cache_for("raw").delete(
        CacheKey(layer="raw", symbol="BTC/USD", venue="BINANCE", timeframe="1min")
    )
    new_key = CacheKey(layer="raw", symbol="ETH/USD", venue="BINANCE", timeframe="5min")
    new_frame = pd.DataFrame(
        {"price": [200.0], "volume": [3.0]},
        index=pd.DatetimeIndex([base + timedelta(hours=1)], tz="UTC"),
    )
    registry.cache_for("raw").put(new_key, new_frame)

    snapshots = service.rebuild_metadata()

    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot.key == new_key
    assert snapshot.rows == 1
    assert snapshot.last_updated == datetime(2024, 1, 3, tzinfo=timezone.utc)
