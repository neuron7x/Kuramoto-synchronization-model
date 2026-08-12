# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Clock DI + ``epoch_ns`` column round-trip on ``PostgresEventStore``.

These tests exercise the schema extension added in Sprint 1 of the
remediation plan against an in-memory SQLite engine. SQLite lacks JSONB
but accepts our ``BigInteger`` / ``String`` / ``DateTime`` columns and
is sufficient to verify the write path.

Contract summary
----------------
C-ES-CLK-1  ``PostgresEventStore`` accepts a ``clock`` in the constructor
            and uses it instead of ``default_clock()``.
C-ES-CLK-2  Every event written after Sprint 1 carries a non-null
            ``epoch_ns`` matching ``clock.epoch_ns()``.
C-ES-CLK-3  ``EventEnvelope.epoch_ns`` is hydrated on read.
C-ES-CLK-4  Two FrozenClock-driven stores writing the same aggregate
            produce byte-identical ``epoch_ns`` sequences.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import JSON, Integer, create_engine

from geosync.core.compat import FrozenClock


@pytest.fixture
def sqlite_engine_factory(monkeypatch):
    """Factory for engines that can stand in for Postgres in sourcing tests.

    The ``sourcing`` module uses ``sqlalchemy.dialects.postgresql.JSONB``
    plus a ``'{}'::jsonb`` cast in the ``metadata`` server default. Both
    are Postgres-specific. We substitute ``JSON`` for ``JSONB`` (portable
    at the column-type level) and drop server defaults on SQLite before
    ``create_schema`` so the tests run in-memory. Integration tests
    exercise the real JSONB path against Postgres elsewhere.
    """

    monkeypatch.setattr("core.events.sourcing.JSONB", JSON, raising=True)
    # SQLite demands literal ``INTEGER PRIMARY KEY`` (not BIGINT) to wire
    # autoincrement; swap the PK column type for the duration of the test.
    monkeypatch.setattr("core.events.sourcing.BigInteger", Integer, raising=True)

    def _make():
        return create_engine("sqlite:///:memory:", future=True)

    return _make


def _store_against_sqlite(engine, clock):
    """Construct a ``PostgresEventStore`` that can run on SQLite for tests."""
    from core.events.sourcing import PostgresEventStore

    store = PostgresEventStore(engine, schema=None, clock=clock)
    # Drop the Postgres-specific ``'{}'::jsonb`` cast used for the
    # ``metadata`` column default; keep portable ``func.now()`` defaults.
    for table in (store._events, store._snapshots):
        for col in table.columns:
            if col.name == "metadata":
                col.server_default = None
    store.create_schema()
    return store


def _clock_at(instant: datetime) -> FrozenClock:
    return FrozenClock(instant=instant)


@pytest.fixture
def sample_aggregate():
    from core.events.sourcing import OrderAggregate
    from domain.order import OrderSide, OrderType

    def _make() -> OrderAggregate:
        return OrderAggregate.create(
            order_id=f"order-{uuid4()}",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=10.0,
            price=150.0,
            order_type=OrderType.LIMIT,
        )

    return _make


class TestClockInjection:
    def test_store_accepts_clock_constructor_argument(self, sqlite_engine_factory) -> None:
        from core.events.sourcing import PostgresEventStore

        clock = _clock_at(datetime(2026, 6, 1, tzinfo=timezone.utc))
        store = PostgresEventStore(sqlite_engine_factory(), clock=clock)
        assert store._clock is clock

    def test_store_falls_back_to_default_clock(self, sqlite_engine_factory) -> None:
        from core.events.sourcing import PostgresEventStore
        from geosync.core.compat import default_clock

        store = PostgresEventStore(sqlite_engine_factory())
        assert store._clock is default_clock()


class TestEpochNsRoundTrip:
    def test_append_writes_clock_epoch_ns(self, sqlite_engine_factory, sample_aggregate) -> None:
        clock = _clock_at(datetime(2026, 6, 1, tzinfo=timezone.utc))
        store = _store_against_sqlite(sqlite_engine_factory(), clock)

        aggregate = sample_aggregate()
        store.append(
            aggregate=aggregate,
            events=aggregate.get_pending_events(),
            expected_version=0,
        )
        aggregate.clear_pending_events()

        envelopes = store.load_stream(
            aggregate_id=aggregate.id,
            aggregate_type=aggregate.aggregate_type,
        )
        assert len(envelopes) == 1
        assert envelopes[0].epoch_ns == clock.epoch_ns()

    def test_repeated_appends_reflect_clock_progression(
        self, sqlite_engine_factory, sample_aggregate
    ) -> None:
        clock = _clock_at(datetime(2026, 6, 1, tzinfo=timezone.utc))
        store = _store_against_sqlite(sqlite_engine_factory(), clock)

        aggregate = sample_aggregate()
        store.append(
            aggregate=aggregate,
            events=aggregate.get_pending_events(),
            expected_version=0,
        )
        aggregate.clear_pending_events()

        clock.advance(seconds=5.0)
        aggregate.mark_submitted(venue_order_id="V-1")
        store.append(
            aggregate=aggregate,
            events=aggregate.get_pending_events(),
            expected_version=1,
        )
        aggregate.clear_pending_events()

        envelopes = store.load_stream(
            aggregate_id=aggregate.id,
            aggregate_type=aggregate.aggregate_type,
        )
        assert len(envelopes) == 2
        assert envelopes[0].epoch_ns is not None
        assert envelopes[1].epoch_ns is not None
        assert envelopes[1].epoch_ns - envelopes[0].epoch_ns == 5_000_000_000


class TestDeterministicReplayAcrossStores:
    def test_two_stores_same_clock_produce_equal_epoch_ns(
        self, sqlite_engine_factory, sample_aggregate
    ) -> None:
        """Pinning two independent stores to the same FrozenClock must
        yield identical ``epoch_ns`` sequences. Foundation for replay."""
        instant = datetime(2026, 6, 1, tzinfo=timezone.utc)
        store_a = _store_against_sqlite(sqlite_engine_factory(), _clock_at(instant))
        store_b = _store_against_sqlite(sqlite_engine_factory(), _clock_at(instant))

        agg_a = sample_aggregate()
        store_a.append(
            aggregate=agg_a,
            events=agg_a.get_pending_events(),
            expected_version=0,
        )
        agg_b = sample_aggregate()
        store_b.append(
            aggregate=agg_b,
            events=agg_b.get_pending_events(),
            expected_version=0,
        )

        envs_a = store_a.load_stream(aggregate_id=agg_a.id, aggregate_type=agg_a.aggregate_type)
        envs_b = store_b.load_stream(aggregate_id=agg_b.id, aggregate_type=agg_b.aggregate_type)
        assert envs_a[0].epoch_ns == envs_b[0].epoch_ns
