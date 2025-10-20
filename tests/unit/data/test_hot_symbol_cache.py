from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.data.models import InstrumentType, PriceTick
import src.data.kafka_ingestion as kafka_ingestion
from src.data.kafka_ingestion import HotSymbolCache


BASE_TS = datetime(2024, 1, 1, tzinfo=UTC)


class _DeterministicClock:
    """Deterministic monotonic clock used to control time-dependent logic."""

    def __init__(self) -> None:
        self._value = 0.0

    def advance(self, seconds: float) -> float:
        self._value += seconds
        return self._value

    def monotonic(self) -> float:
        return self._value


@pytest.fixture()
def deterministic_clock(monkeypatch: pytest.MonkeyPatch) -> _DeterministicClock:
    clock = _DeterministicClock()
    monkeypatch.setattr(kafka_ingestion.time, "monotonic", clock.monotonic)
    return clock


def _make_tick(
    *,
    symbol: str = "BTC/USDT",
    venue: str = "BINANCE",
    minutes: int = 0,
    instrument_type: InstrumentType = InstrumentType.SPOT,
) -> PriceTick:
    return PriceTick.create(
        symbol=symbol,
        venue=venue,
        price=30_000 + minutes,
        volume=1,
        timestamp=BASE_TS + timedelta(minutes=minutes),
        instrument_type=instrument_type,
    )


def test_hot_symbol_cache_flushes_overflow_when_exceeding_max_ticks(
    deterministic_clock: _DeterministicClock,
) -> None:
    cache = HotSymbolCache(
        max_entries=4,
        ttl_seconds=60,
        max_ticks=3,
        flush_size=10,
        clock=deterministic_clock.monotonic,
    )

    ticks = [_make_tick(minutes=i) for i in range(4)]
    for tick in ticks[:3]:
        deterministic_clock.advance(1.0)
        flushed = cache.update(tick)
        assert flushed == []

    deterministic_clock.advance(1.0)
    flushed = cache.update(ticks[3])

    assert len(flushed) == 1
    overflow_snapshot = flushed[0]
    assert overflow_snapshot.symbol == "BTC/USDT"
    assert [tick.price for tick in overflow_snapshot.ticks] == [ticks[0].price]
    expected_last_seen = datetime.fromtimestamp(deterministic_clock.monotonic(), tz=UTC)
    assert overflow_snapshot.last_seen == expected_last_seen

    snapshot = cache.snapshot("BTC/USDT", "BINANCE")
    assert snapshot is not None
    assert [tick.price for tick in snapshot.ticks] == [ticks[1].price, ticks[2].price, ticks[3].price]


def test_hot_symbol_cache_flushes_when_reaching_flush_size(
    deterministic_clock: _DeterministicClock,
) -> None:
    cache = HotSymbolCache(
        max_entries=4,
        ttl_seconds=60,
        max_ticks=10,
        flush_size=3,
        clock=deterministic_clock.monotonic,
    )

    ticks = [_make_tick(minutes=i) for i in range(3)]
    flushed: list[kafka_ingestion.HotSymbolSnapshot] = []
    for tick in ticks:
        deterministic_clock.advance(0.5)
        flushed = cache.update(tick)

    assert len(flushed) == 1
    batch_snapshot = flushed[0]
    assert [tick.price for tick in batch_snapshot.ticks] == [t.price for t in ticks]
    expected_last_seen = datetime.fromtimestamp(deterministic_clock.monotonic(), tz=UTC)
    assert batch_snapshot.last_seen == expected_last_seen

    snapshot = cache.snapshot("BTC/USDT", "BINANCE")
    assert snapshot is not None
    assert snapshot.ticks == ()


def test_hot_symbol_cache_expires_stale_entries(deterministic_clock: _DeterministicClock) -> None:
    cache = HotSymbolCache(
        max_entries=4,
        ttl_seconds=5,
        max_ticks=10,
        flush_size=10,
        clock=deterministic_clock.monotonic,
    )

    deterministic_clock.advance(0.1)
    first_seen = deterministic_clock.monotonic()
    first_tick = _make_tick(symbol="BTC/USDT", minutes=0)
    cache.update(first_tick)

    deterministic_clock.advance(6.0)
    second_tick = _make_tick(symbol="ETH/USDT", minutes=1)
    flushed = cache.update(second_tick)

    assert any(snapshot.symbol == "BTC/USDT" for snapshot in flushed)
    stale_snapshot = next(snapshot for snapshot in flushed if snapshot.symbol == "BTC/USDT")
    assert [tick.price for tick in stale_snapshot.ticks] == [first_tick.price]
    expected_last_seen = datetime.fromtimestamp(first_seen, tz=UTC)
    assert stale_snapshot.last_seen == expected_last_seen

    assert cache.snapshot("BTC/USDT", "BINANCE") is None


def test_hot_symbol_cache_evicts_least_recent_entries(
    deterministic_clock: _DeterministicClock,
) -> None:
    cache = HotSymbolCache(
        max_entries=1,
        ttl_seconds=60,
        max_ticks=10,
        flush_size=10,
        clock=deterministic_clock.monotonic,
    )

    first_tick = _make_tick(symbol="BTC/USDT", minutes=0)
    deterministic_clock.advance(0.2)
    assert cache.update(first_tick) == []

    deterministic_clock.advance(0.2)
    second_tick = _make_tick(symbol="ETH/USDT", minutes=1)
    flushed = cache.update(second_tick)

    assert len(flushed) == 1
    evicted_snapshot = flushed[0]
    assert evicted_snapshot.symbol == "BTC/USDT"
    assert [tick.price for tick in evicted_snapshot.ticks] == [first_tick.price]

    assert cache.snapshot("BTC/USDT", "BINANCE") is None
    eth_snapshot = cache.snapshot("ETH/USDT", "BINANCE")
    assert eth_snapshot is not None
    assert [tick.price for tick in eth_snapshot.ticks] == [second_tick.price]


def test_hot_symbol_cache_drain_flushes_all_entries(
    deterministic_clock: _DeterministicClock,
) -> None:
    cache = HotSymbolCache(
        max_entries=4,
        ttl_seconds=60,
        max_ticks=10,
        flush_size=10,
        clock=deterministic_clock.monotonic,
    )

    first_tick = _make_tick(symbol="BTC/USDT", minutes=0)
    second_tick = _make_tick(symbol="ETH/USDT", minutes=1)
    deterministic_clock.advance(0.1)
    cache.update(first_tick)
    deterministic_clock.advance(0.1)
    cache.update(second_tick)

    drained = cache.drain()
    snapshot_by_symbol = {snapshot.symbol: snapshot for snapshot in drained}
    assert set(snapshot_by_symbol) == {"BTC/USDT", "ETH/USDT"}
    assert [tick.price for tick in snapshot_by_symbol["BTC/USDT"].ticks] == [first_tick.price]
    assert [tick.price for tick in snapshot_by_symbol["ETH/USDT"].ticks] == [second_tick.price]

    assert cache.snapshot("BTC/USDT", "BINANCE") is None
    assert cache.snapshot("ETH/USDT", "BINANCE") is None
