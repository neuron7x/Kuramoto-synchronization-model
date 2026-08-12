# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given, settings  # noqa: E402 - after importorskip
from hypothesis import strategies as st  # noqa: E402

import src.data.kafka_ingestion as kafka_ingestion  # noqa: E402
from core.data.models import InstrumentType, PriceTick  # noqa: E402
from src.data.kafka_ingestion import HotSymbolCache  # noqa: E402

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
    assert [tick.price for tick in snapshot.ticks] == [
        ticks[1].price,
        ticks[2].price,
        ticks[3].price,
    ]


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


def test_hot_symbol_cache_expires_stale_entries(
    deterministic_clock: _DeterministicClock,
) -> None:
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
    stale_snapshot = next(
        snapshot for snapshot in flushed if snapshot.symbol == "BTC/USDT"
    )
    assert [tick.price for tick in stale_snapshot.ticks] == [first_tick.price]
    expected_last_seen = datetime.fromtimestamp(first_seen, tz=UTC)
    assert stale_snapshot.last_seen == expected_last_seen

    # After eviction, the entry is completely removed from the cache
    btc_snapshot = cache.snapshot("BTC/USDT", "BINANCE")
    assert btc_snapshot is None


def test_hot_symbol_cache_retains_new_symbol_after_expiring_stale_entry(
    deterministic_clock: _DeterministicClock,
) -> None:
    cache = HotSymbolCache(
        max_entries=1,
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
    second_seen = deterministic_clock.monotonic()
    second_tick = _make_tick(symbol="ETH/USDT", minutes=1)
    flushed = cache.update(second_tick)

    assert len(flushed) == 1
    stale_snapshot = flushed[0]
    assert stale_snapshot.symbol == "BTC/USDT"
    expected_first_seen = datetime.fromtimestamp(first_seen, tz=UTC)
    assert stale_snapshot.last_seen == expected_first_seen

    assert cache.snapshot("BTC/USDT", "BINANCE") is None
    eth_snapshot = cache.snapshot("ETH/USDT", "BINANCE")
    assert eth_snapshot is not None
    assert eth_snapshot.ticks == (second_tick,)
    expected_second_seen = datetime.fromtimestamp(second_seen, tz=UTC)
    assert eth_snapshot.last_seen == expected_second_seen


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
    assert [tick.price for tick in snapshot_by_symbol["BTC/USDT"].ticks] == [
        first_tick.price
    ]
    assert [tick.price for tick in snapshot_by_symbol["ETH/USDT"].ticks] == [
        second_tick.price
    ]

    assert cache.snapshot("BTC/USDT", "BINANCE") is None
    assert cache.snapshot("ETH/USDT", "BINANCE") is None


class _PredictableClock:
    """Deterministic monotonic clock returning evenly spaced timestamps."""

    def __init__(self, *, step: float = 0.03125) -> None:
        self._value = 0.0
        self._step = step

    def __call__(self) -> float:
        self._value += self._step
        return self._value


def _summarise_snapshot(snapshot: kafka_ingestion.HotSymbolSnapshot) -> tuple:
    return (
        snapshot.symbol,
        snapshot.venue,
        snapshot.instrument_type,
        tuple(
            (
                tick.timestamp,
                tick.price,
                tick.volume,
                tick.instrument_type,
            )
            for tick in snapshot.ticks
        ),
        snapshot.last_seen,
    )


@st.composite
def _tick_strategy(draw) -> PriceTick:
    symbol = draw(
        st.sampled_from(
            (
                "BTC/USDT",
                "ETH/USDT",
                "SOL/USDT",
                "ADA/USDT",
            )
        )
    )
    venue = draw(st.sampled_from(("BINANCE", "COINBASE", "KRAKEN")))
    instrument_type = draw(st.sampled_from(tuple(InstrumentType)))
    price = draw(
        st.decimals(
            min_value=Decimal("0.01"),
            max_value=Decimal("100000"),
            places=5,
            allow_nan=False,
            allow_infinity=False,
        )
    )
    volume = draw(
        st.decimals(
            min_value=Decimal("0"),
            max_value=Decimal("1000"),
            places=4,
            allow_nan=False,
            allow_infinity=False,
        )
    )
    timestamp = BASE_TS + timedelta(
        seconds=draw(st.integers(min_value=0, max_value=86_400))
    )
    return PriceTick.create(
        symbol=symbol,
        venue=venue,
        price=price,
        timestamp=timestamp,
        volume=volume,
        instrument_type=instrument_type,
    )


def _run_cache_sequence(
    ticks: list[PriceTick],
) -> tuple[tuple[tuple, ...], tuple[tuple, ...]]:
    clock = _PredictableClock()
    cache = HotSymbolCache(
        max_entries=5,
        ttl_seconds=3600,
        max_ticks=7,
        flush_size=4,
        clock=clock,
    )

    flushes: list[tuple[tuple, ...]] = []
    seen_keys: set[tuple[str, str, InstrumentType]] = set()
    for tick in ticks:
        seen_keys.add((tick.symbol, tick.venue, tick.instrument_type))
        snapshots = cache.update(tick)
        for snapshot in snapshots:
            assert snapshot.ticks, "flushed snapshots must contain ticks"
            assert len(snapshot.ticks) <= 7
            assert all(t.symbol == snapshot.symbol for t in snapshot.ticks)
            assert all(t.venue == snapshot.venue for t in snapshot.ticks)
            assert all(
                t.instrument_type == snapshot.instrument_type for t in snapshot.ticks
            )
        flushes.append(tuple(_summarise_snapshot(snapshot) for snapshot in snapshots))
        for symbol, venue, instrument_type in seen_keys:
            snapshot = cache.snapshot(symbol, venue, instrument_type)
            if snapshot is None:
                continue
            assert len(snapshot.ticks) <= 7
            assert all(t.symbol == symbol for t in snapshot.ticks)
            assert all(t.venue == venue for t in snapshot.ticks)
            assert all(t.instrument_type == instrument_type for t in snapshot.ticks)

    drained_snapshots = []
    for snapshot in cache.drain():
        assert snapshot.ticks, "drained snapshots must contain ticks"
        assert len(snapshot.ticks) <= 7
        drained_snapshots.append(_summarise_snapshot(snapshot))
    return tuple(flushes), tuple(drained_snapshots)


@given(st.lists(_tick_strategy(), min_size=1, max_size=25))
@settings(max_examples=200, deadline=None)
def test_hot_symbol_cache_property_invariants_and_determinism(
    ticks: list[PriceTick],
) -> None:
    first = _run_cache_sequence(ticks)
    second = _run_cache_sequence(ticks)
    assert first == second
