# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Coverage battery for :mod:`core.events.sourcing`.

Aggregate roots, event (de)serialisation, the SQLite-backed event store,
replay/rebuild helpers and snapshot utilities are all exercised through
real calls.

The store under test is Postgres-oriented (``JSONB``, ``ON CONFLICT``,
``BigInteger`` autoincrement). Following the pattern already established
by ``tests/unit/events/test_sourcing_epoch_ns.py`` we substitute the
portable SQLite equivalents (``JSON`` for ``JSONB``, ``Integer`` for the
``BigInteger`` primary key, the SQLite ``insert`` for the Postgres
dialect ``insert``) so the write/read/upsert paths run in-memory. The
real Postgres path is covered by integration tests elsewhere.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import JSON, Integer, create_engine
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

import core.events.sourcing as src
from core.events.admission import AdmissionVerdict, Barrier, RejectCode
from core.events.validation import DomainValidationError, ValidationResult
from domain.order import OrderSide, OrderStatus, OrderType
from geosync.core.compat import FrozenClock

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def es(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Patch the sourcing module for SQLite and return store helpers."""

    monkeypatch.setattr(src, "JSONB", JSON, raising=True)
    monkeypatch.setattr(src, "BigInteger", Integer, raising=True)
    monkeypatch.setattr(src, "insert", sqlite_insert, raising=True)

    def make_engine() -> Any:
        return create_engine("sqlite:///:memory:", future=True)

    def make_store(
        engine: Any = None, clock: FrozenClock | None = None
    ) -> src.PostgresEventStore:
        engine = engine if engine is not None else make_engine()
        store = src.PostgresEventStore(engine, schema=None, clock=clock)
        for table in (store._events, store._snapshots):
            for col in table.columns:
                if col.name == "metadata":
                    col.server_default = None
        store.create_schema()
        return store

    return SimpleNamespace(make_engine=make_engine, make_store=make_store)


def _new_order(**overrides: Any) -> src.OrderAggregate:
    params: dict[str, Any] = {
        "order_id": f"order-{uuid4()}",
        "symbol": "AAPL",
        "side": OrderSide.BUY,
        "quantity": 10.0,
        "price": 150.0,
        "order_type": OrderType.LIMIT,
    }
    params.update(overrides)
    return src.OrderAggregate.create(**params)


def _clock() -> FrozenClock:
    return FrozenClock(instant=datetime(2026, 6, 1, tzinfo=timezone.utc))


# ---------------------------------------------------------------------------
# Domain events + registry
# ---------------------------------------------------------------------------


class TestDomainEvent:
    def test_to_dict_and_from_dict_roundtrip(self) -> None:
        event = src.OrderCancelled(order_id="o-1", reason="user")
        payload = event.to_dict()
        assert payload["order_id"] == "o-1"
        assert "stream_version" not in payload  # excluded field
        restored = src.OrderCancelled.from_dict(payload)
        assert restored.order_id == "o-1"
        assert restored.reason == "user"

    def test_event_name_defaults_to_class_name(self) -> None:
        assert src.OrderCreated.event_name == "OrderCreated"

    def test_duplicate_event_name_raises(self) -> None:
        with pytest.raises(ValueError, match="Duplicate domain event name"):

            class _Dup(src.DomainEvent):
                event_name = "OrderCreated"


# ---------------------------------------------------------------------------
# AggregateRoot base behaviour
# ---------------------------------------------------------------------------


class TestAggregateRoot:
    def test_missing_aggregate_type_raises(self) -> None:
        with pytest.raises(ValueError, match="aggregate_type"):
            src.AggregateRoot("agg-1")

    def test_pending_events_lifecycle(self) -> None:
        order = _new_order()
        assert len(order.get_pending_events()) == 1
        order.clear_pending_events()
        assert order.get_pending_events() == []

    def test_missing_handler_raises_attribute_error(self) -> None:
        order = src.OrderAggregate("o-1")
        foreign = src.PositionOpened(
            position_id="p-1", symbol="AAPL", quantity=1.0, average_price=1.0
        )
        with pytest.raises(AttributeError, match="missing handler"):
            order.load_from_history([foreign])

    def test_load_from_history_sets_version_from_stream_version(self) -> None:
        created = src.OrderCreated(
            order_id="o-1",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=5.0,
            price=1.0,
            order_type=OrderType.LIMIT,
        )
        created.stream_version = 7
        order = src.OrderAggregate("o-1")
        order.load_from_history([created])
        assert order.version == 7


# ---------------------------------------------------------------------------
# Order aggregate
# ---------------------------------------------------------------------------


class TestOrderAggregate:
    def test_create_sets_state(self) -> None:
        order = _new_order()
        assert order.status is OrderStatus.PENDING
        assert order.symbol == "AAPL"
        assert order.version == 1

    def test_mark_submitted(self) -> None:
        order = _new_order()
        order.mark_submitted("venue-1")
        assert order.status is OrderStatus.OPEN
        assert order.venue_order_id == "venue-1"

    def test_mark_submitted_invalid_status(self) -> None:
        order = _new_order(quantity=5.0)
        order.record_fill(quantity=5.0, price=100.0)  # -> FILLED
        with pytest.raises(ValueError, match="Cannot submit order"):
            order.mark_submitted("venue-x")

    def test_record_fill_partial_then_full(self) -> None:
        order = _new_order(quantity=10.0)
        order.record_fill(quantity=4.0, price=100.0)
        assert order.status is OrderStatus.PARTIALLY_FILLED
        assert order.filled_quantity == 4.0
        order.record_fill(quantity=6.0, price=110.0)
        assert order.status is OrderStatus.FILLED
        # Weighted average price across the two fills.
        assert order.average_price == pytest.approx((100.0 * 4 + 110.0 * 6) / 10.0)

    def test_record_fill_non_positive_quantity(self) -> None:
        order = _new_order()
        with pytest.raises(ValueError, match="Fill quantity must be positive"):
            order.record_fill(quantity=0.0, price=1.0)

    def test_record_fill_exceeds_size(self) -> None:
        order = _new_order(quantity=5.0)
        with pytest.raises(ValueError, match="exceeds order size"):
            order.record_fill(quantity=6.0, price=1.0)

    def test_record_fill_non_positive_price(self) -> None:
        order = _new_order()
        with pytest.raises(ValueError, match="Fill price must be positive"):
            order.record_fill(quantity=1.0, price=0.0)

    def test_cancel_and_idempotent_after_terminal(self) -> None:
        order = _new_order(quantity=5.0)
        order.cancel(reason="bye")
        assert order.status is OrderStatus.CANCELLED
        pending_before = len(order.get_pending_events())
        order.cancel()  # already cancelled -> no-op
        assert len(order.get_pending_events()) == pending_before

    def test_reject_and_reject_filled_raises(self) -> None:
        order = _new_order(quantity=5.0)
        order.reject(reason="risk")
        assert order.status is OrderStatus.REJECTED
        assert order.rejection_reason == "risk"

        filled = _new_order(quantity=5.0)
        filled.record_fill(quantity=5.0, price=100.0)
        with pytest.raises(ValueError, match="Cannot reject a filled order"):
            filled.reject()

    def test_snapshot_roundtrip(self) -> None:
        order = _new_order(quantity=8.0)
        order.mark_submitted("venue-9")
        order.record_fill(quantity=8.0, price=155.0)
        state = order.snapshot_state()
        restored = src.OrderAggregate("o-2")
        restored.load_snapshot(state)
        assert restored.status is OrderStatus.FILLED
        assert restored.side is OrderSide.BUY
        assert restored.order_type is OrderType.LIMIT
        assert restored.filled_quantity == 8.0

    def test_snapshot_roundtrip_with_none_optionals(self) -> None:
        order = src.OrderAggregate("o-3")
        state = order.snapshot_state()
        assert state["side"] is None
        assert state["order_type"] is None
        restored = src.OrderAggregate("o-4")
        restored.load_snapshot(state)
        assert restored.side is None
        assert restored.order_type is None


# ---------------------------------------------------------------------------
# Position aggregate
# ---------------------------------------------------------------------------


class TestPositionAggregate:
    def test_open_and_close(self) -> None:
        pos = src.PositionAggregate.open(
            position_id="p-1", symbol="AAPL", quantity=10.0, average_price=100.0
        )
        assert pos.quantity == 10.0
        pos.close(closing_price=110.0)
        assert pos.is_closed is True
        assert pos.realised_pnl == pytest.approx((110.0 - 100.0) * 10.0)
        assert pos.quantity == 0.0

    def test_open_zero_quantity_raises(self) -> None:
        with pytest.raises(ValueError, match="non-zero"):
            src.PositionAggregate.open(
                position_id="p", symbol="AAPL", quantity=0.0, average_price=1.0
            )

    def test_open_non_positive_price_raises(self) -> None:
        with pytest.raises(ValueError, match="Average price must be positive"):
            src.PositionAggregate.open(
                position_id="p", symbol="AAPL", quantity=1.0, average_price=0.0
            )

    def test_adjust_increases_and_averages(self) -> None:
        pos = src.PositionAggregate.open(
            position_id="p-1", symbol="AAPL", quantity=10.0, average_price=100.0
        )
        pos.adjust(delta_quantity=10.0, execution_price=120.0)
        assert pos.quantity == 20.0
        assert pos.average_price == pytest.approx((100.0 * 10 + 120.0 * 10) / 20.0)

    def test_adjust_to_zero_closes(self) -> None:
        pos = src.PositionAggregate.open(
            position_id="p-1", symbol="AAPL", quantity=10.0, average_price=100.0
        )
        pos.adjust(delta_quantity=-10.0, execution_price=105.0)
        assert pos.quantity == 0.0
        assert pos.average_price == 0.0
        assert pos.is_closed is True

    def test_adjust_closed_raises(self) -> None:
        pos = src.PositionAggregate.open(
            position_id="p-1", symbol="AAPL", quantity=10.0, average_price=100.0
        )
        pos.close(closing_price=100.0)
        with pytest.raises(ValueError, match="Cannot adjust a closed position"):
            pos.adjust(delta_quantity=1.0, execution_price=100.0)

    def test_adjust_non_positive_price_raises(self) -> None:
        pos = src.PositionAggregate.open(
            position_id="p-1", symbol="AAPL", quantity=10.0, average_price=100.0
        )
        with pytest.raises(ValueError, match="Execution price must be positive"):
            pos.adjust(delta_quantity=1.0, execution_price=0.0)

    def test_close_idempotent(self) -> None:
        pos = src.PositionAggregate.open(
            position_id="p-1", symbol="AAPL", quantity=10.0, average_price=100.0
        )
        pos.close(closing_price=110.0)
        pending = len(pos.get_pending_events())
        pos.close(closing_price=120.0)  # already closed -> no-op
        assert len(pos.get_pending_events()) == pending

    def test_close_non_positive_price_raises(self) -> None:
        pos = src.PositionAggregate.open(
            position_id="p-1", symbol="AAPL", quantity=10.0, average_price=100.0
        )
        with pytest.raises(ValueError, match="Closing price must be positive"):
            pos.close(closing_price=0.0)

    def test_snapshot_roundtrip(self) -> None:
        pos = src.PositionAggregate.open(
            position_id="p-1", symbol="AAPL", quantity=10.0, average_price=100.0
        )
        restored = src.PositionAggregate("p-2")
        restored.load_snapshot(pos.snapshot_state())
        assert restored.quantity == 10.0
        assert restored.symbol == "AAPL"
        assert restored.is_closed is False


# ---------------------------------------------------------------------------
# Portfolio aggregate
# ---------------------------------------------------------------------------


class TestPortfolioAggregate:
    def _portfolio(self) -> src.PortfolioAggregate:
        return src.PortfolioAggregate.create(portfolio_id="pf-1", base_currency="USD")

    def test_create_and_deposit(self) -> None:
        pf = self._portfolio()
        assert pf.base_currency == "USD"
        pf.deposit_cash(1000.0)
        assert pf.cash_balance == 1000.0

    def test_deposit_non_positive_raises(self) -> None:
        with pytest.raises(ValueError, match="Deposit amount must be positive"):
            self._portfolio().deposit_cash(0.0)

    def test_withdraw_and_errors(self) -> None:
        pf = self._portfolio()
        pf.deposit_cash(500.0)
        pf.withdraw_cash(200.0)
        assert pf.cash_balance == 300.0
        with pytest.raises(ValueError, match="Withdrawal amount must be positive"):
            pf.withdraw_cash(0.0)
        with pytest.raises(ValueError, match="Insufficient cash"):
            pf.withdraw_cash(10_000.0)

    def test_link_realise_and_exposure(self) -> None:
        pf = self._portfolio()
        pf.link_position("p-1", "AAPL", 10.0)
        assert pf.positions["p-1"]["symbol"] == "AAPL"
        pf.realise_pnl("p-1", 42.0)
        assert pf.realised_pnl == 42.0
        pf.update_exposure({"AAPL": 0.5})
        assert pf.exposures["AAPL"] == 0.5

    def test_snapshot_roundtrip(self) -> None:
        pf = self._portfolio()
        pf.deposit_cash(1000.0)
        pf.link_position("p-1", "AAPL", 10.0)
        pf.realise_pnl("p-1", 15.0)
        pf.update_exposure({"AAPL": 0.25})
        restored = src.PortfolioAggregate("pf-2")
        restored.load_snapshot(pf.snapshot_state())
        assert restored.cash_balance == 1000.0
        assert restored.positions["p-1"]["quantity"] == 10.0
        assert restored.realised_pnl == 15.0
        assert restored.exposures["AAPL"] == 0.25


# ---------------------------------------------------------------------------
# PostgresEventStore
# ---------------------------------------------------------------------------


class TestPostgresEventStore:
    def test_append_and_load_stream_roundtrip(self, es: SimpleNamespace) -> None:
        store = es.make_store(clock=_clock())
        order = _new_order()
        version = store.append(
            aggregate=order,
            events=order.get_pending_events(),
            expected_version=0,
            metadata={"k": "v"},
            correlation_id="corr-1",
            causation_id="cause-1",
        )
        order.clear_pending_events()
        assert version == 1

        envelopes = store.load_stream(aggregate_id=order.id, aggregate_type="order")
        assert len(envelopes) == 1
        env = envelopes[0]
        assert env.event_type == "OrderCreated"
        assert env.metadata["k"] == "v"
        assert env.correlation_id == "corr-1"
        assert env.epoch_ns == _clock().epoch_ns()
        assert env.payload.stream_version == 1

    def test_append_expected_version_none_skips_check(self, es: SimpleNamespace) -> None:
        store = es.make_store()
        order = _new_order()
        version = store.append(
            aggregate=order,
            events=order.get_pending_events(),
            expected_version=None,
        )
        assert version == 1

    def test_append_concurrency_error(self, es: SimpleNamespace) -> None:
        store = es.make_store()
        order = _new_order()
        store.append(
            aggregate=order, events=order.get_pending_events(), expected_version=0
        )
        order.clear_pending_events()
        order.mark_submitted("venue-1")
        with pytest.raises(src.ConcurrencyError, match="Expected version 0"):
            store.append(
                aggregate=order,
                events=order.get_pending_events(),
                expected_version=0,
            )

    def test_append_epoch_ns_unavailable_writes_null(self, es: SimpleNamespace) -> None:
        store = es.make_store(clock=_clock())
        store._epoch_ns_available = False
        order = _new_order()
        store.append(
            aggregate=order, events=order.get_pending_events(), expected_version=0
        )
        envelopes = store.load_stream(aggregate_id=order.id, aggregate_type="order")
        assert envelopes[0].epoch_ns is None

    def test_inspect_epoch_ns_available_on_existing_table(
        self, es: SimpleNamespace
    ) -> None:
        engine = es.make_engine()
        es.make_store(engine)  # creates the events table with epoch_ns
        second = src.PostgresEventStore(engine, schema=None)
        assert second._epoch_ns_available is True

    def test_append_with_validator_accept(self, es: SimpleNamespace) -> None:
        class _Accept:
            def validate(
                self, event: src.DomainEvent, aggregate: src.AggregateRoot
            ) -> ValidationResult:
                return ValidationResult.ok()

        store = es.make_store()
        order = _new_order()
        store.append(
            aggregate=order,
            events=order.get_pending_events(),
            expected_version=0,
            validator=_Accept(),
        )
        order.clear_pending_events()
        # Second batch replays committed history into the validator shadow.
        order.mark_submitted("venue-1")
        store.append(
            aggregate=order,
            events=order.get_pending_events(),
            expected_version=1,
            validator=_Accept(),
        )
        stream = store.load_stream(aggregate_id=order.id, aggregate_type="order")
        assert len(stream) == 2

    def test_append_with_validator_reject(self, es: SimpleNamespace) -> None:
        class _Reject:
            def validate(
                self, event: src.DomainEvent, aggregate: src.AggregateRoot
            ) -> ValidationResult:
                return ValidationResult.rejected("blocked by rule")

        store = es.make_store()
        order = _new_order()
        with pytest.raises(DomainValidationError, match="blocked by rule"):
            store.append(
                aggregate=order,
                events=order.get_pending_events(),
                expected_version=0,
                validator=_Reject(),
            )
        # Rolled back: nothing persisted.
        assert store.load_stream(aggregate_id=order.id, aggregate_type="order") == []

    def test_append_with_admission_gate_accept(self, es: SimpleNamespace) -> None:
        class _Gate:
            def verdict(
                self, event: src.DomainEvent, aggregate: src.AggregateRoot
            ) -> AdmissionVerdict:
                return AdmissionVerdict.accept()

        store = es.make_store()
        order = _new_order()
        store.append(
            aggregate=order,
            events=order.get_pending_events(),
            expected_version=0,
            admission_gate=_Gate(),
        )
        assert len(store.load_stream(aggregate_id=order.id, aggregate_type="order")) == 1

    def test_append_with_admission_gate_reject_structured(
        self, es: SimpleNamespace
    ) -> None:
        class _Gate:
            def verdict(
                self, event: src.DomainEvent, aggregate: src.AggregateRoot
            ) -> AdmissionVerdict:
                return AdmissionVerdict.reject(
                    Barrier.STATE,
                    RejectCode.STATE_INCONSISTENT,
                    "state broken",
                    "INV-1",
                )

        store = es.make_store()
        order = _new_order()
        with pytest.raises(DomainValidationError, match="E_STATE_INCONSISTENT"):
            store.append(
                aggregate=order,
                events=order.get_pending_events(),
                expected_version=0,
                admission_gate=_Gate(),
            )

    def test_append_with_admission_gate_reject_without_code(
        self, es: SimpleNamespace
    ) -> None:
        class _Gate:
            def verdict(
                self, event: src.DomainEvent, aggregate: src.AggregateRoot
            ) -> AdmissionVerdict:
                return AdmissionVerdict(
                    accepted=False,
                    barrier=None,
                    code=None,
                    reason="opaque",
                    invariant_id="INV-2",
                )

        store = es.make_store()
        order = _new_order()
        with pytest.raises(DomainValidationError, match="REJECTED"):
            store.append(
                aggregate=order,
                events=order.get_pending_events(),
                expected_version=0,
                admission_gate=_Gate(),
            )

    def test_iterate_all_events_multiple_chunks(self, es: SimpleNamespace) -> None:
        store = es.make_store()
        order = _new_order(quantity=9.0)
        order.mark_submitted("venue-1")
        order.record_fill(quantity=9.0, price=100.0)
        store.append(
            aggregate=order, events=order.get_pending_events(), expected_version=0
        )
        batches = list(store.iterate_all_events(chunk_size=2))
        total = sum(len(batch) for batch in batches)
        assert total == 3
        assert len(batches) >= 2  # 3 events at chunk_size 2 -> at least two batches

    def test_hydrate_unknown_event_raises(self, es: SimpleNamespace) -> None:
        store = es.make_store()
        with pytest.raises(KeyError, match="Unknown event type"):
            store._hydrate_event({}, "NoSuchEvent")

    def test_snapshot_store_load_and_upsert(self, es: SimpleNamespace) -> None:
        store = es.make_store()
        order = _new_order(quantity=5.0)
        order.record_fill(quantity=5.0, price=100.0)
        snap = src.take_snapshot(order)
        store.store_snapshot(snap)
        loaded = store.load_latest_snapshot(
            aggregate_id=order.id, aggregate_type="order"
        )
        assert loaded is not None
        assert loaded.version == snap.version
        assert loaded.state["status"] == OrderStatus.FILLED.value

        # Upsert path: store a newer snapshot for the same aggregate.
        newer = src.AggregateSnapshot(
            aggregate_id=order.id,
            aggregate_type="order",
            version=snap.version + 5,
            state=dict(snap.state),
            taken_at=datetime(2026, 6, 2, tzinfo=timezone.utc),
        )
        store.store_snapshot(newer)
        reloaded = store.load_latest_snapshot(
            aggregate_id=order.id, aggregate_type="order"
        )
        assert reloaded is not None
        assert reloaded.version == snap.version + 5

    def test_load_latest_snapshot_missing_returns_none(
        self, es: SimpleNamespace
    ) -> None:
        store = es.make_store()
        assert (
            store.load_latest_snapshot(aggregate_id="nope", aggregate_type="order")
            is None
        )


# ---------------------------------------------------------------------------
# EventReplay
# ---------------------------------------------------------------------------


class TestEventReplay:
    def test_rehydrate_without_snapshot(self, es: SimpleNamespace) -> None:
        store = es.make_store()
        order = _new_order(quantity=6.0)
        order.mark_submitted("venue-1")
        order.record_fill(quantity=6.0, price=120.0)
        store.append(
            aggregate=order, events=order.get_pending_events(), expected_version=0
        )
        replay = src.EventReplay(store)
        rebuilt = replay.rehydrate(src.OrderAggregate, order.id)
        assert isinstance(rebuilt, src.OrderAggregate)
        assert rebuilt.status is OrderStatus.FILLED
        assert rebuilt.filled_quantity == 6.0

    def test_rehydrate_with_snapshot(self, es: SimpleNamespace) -> None:
        store = es.make_store()
        order = _new_order(quantity=10.0)
        store.append(
            aggregate=order, events=order.get_pending_events(), expected_version=0
        )
        order.clear_pending_events()
        # Snapshot at version 1, then a fill event at version 2.
        snap = src.AggregateSnapshot(
            aggregate_id=order.id,
            aggregate_type="order",
            version=1,
            state=dict(order.snapshot_state()),
            taken_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )
        store.store_snapshot(snap)
        order.record_fill(quantity=10.0, price=130.0)
        store.append(
            aggregate=order, events=order.get_pending_events(), expected_version=1
        )
        replay = src.EventReplay(store)
        rebuilt = replay.rehydrate(src.OrderAggregate, order.id)
        assert rebuilt.status is OrderStatus.FILLED

    def test_print_timeline(self, es: SimpleNamespace) -> None:
        store = es.make_store(clock=_clock())
        order = _new_order()
        order.mark_submitted("venue-1")
        store.append(
            aggregate=order, events=order.get_pending_events(), expected_version=0
        )
        replay = src.EventReplay(store)
        timeline = replay.print_timeline(src.OrderAggregate, order.id)
        assert len(timeline) == 2
        assert "OrderCreated" in timeline[0]
        assert "v1" in timeline[0]


# ---------------------------------------------------------------------------
# ProjectionRebuilder
# ---------------------------------------------------------------------------


class _RecordingProjection:
    def __init__(self, name: str, interested: set[str] | None) -> None:
        self.name = name
        self._interested = interested
        self.reset_called = False
        self.projected: list[str] = []

    def interested_in(self) -> set[str] | None:
        return self._interested

    def reset(self, session: Any) -> None:
        self.reset_called = True

    def project(self, envelope: src.EventEnvelope, session: Any) -> None:
        self.projected.append(envelope.event_type)


class TestProjectionRebuilder:
    def _seed(self, store: src.PostgresEventStore) -> None:
        order = _new_order(quantity=4.0)
        order.mark_submitted("venue-1")
        order.record_fill(quantity=4.0, price=100.0)
        store.append(
            aggregate=order, events=order.get_pending_events(), expected_version=0
        )

    def test_rebuild_all_events(self, es: SimpleNamespace) -> None:
        store = es.make_store()
        self._seed(store)
        projection = _RecordingProjection("all", interested=None)
        src.ProjectionRebuilder(store).rebuild(projection)
        assert projection.reset_called is True
        assert projection.projected == ["OrderCreated", "OrderSubmitted", "OrderFilled"]

    def test_rebuild_filtered_events(self, es: SimpleNamespace) -> None:
        store = es.make_store()
        self._seed(store)
        projection = _RecordingProjection("filtered", interested={"OrderFilled"})
        src.ProjectionRebuilder(store).rebuild(projection)
        assert projection.projected == ["OrderFilled"]


# ---------------------------------------------------------------------------
# MaterializedViewManager (mock engine — SQLite has no materialized views)
# ---------------------------------------------------------------------------


class TestMaterializedViewManager:
    def _mock_engine(self) -> tuple[MagicMock, MagicMock]:
        engine = MagicMock()
        conn = MagicMock()
        engine.begin.return_value.__enter__.return_value = conn
        engine.begin.return_value.__exit__.return_value = False
        return engine, conn

    def test_ensure_exists_with_data(self) -> None:
        engine, conn = self._mock_engine()
        view = src.MaterializedView(name="mv", definition_sql="SELECT 1")
        src.MaterializedViewManager(engine).ensure_exists(view)
        sql = str(conn.execute.call_args.args[0])
        assert "CREATE MATERIALIZED VIEW IF NOT EXISTS mv" in sql
        assert "WITH DATA" in sql

    def test_ensure_exists_without_data(self) -> None:
        engine, conn = self._mock_engine()
        view = src.MaterializedView(name="mv", definition_sql="SELECT 1", with_data=False)
        src.MaterializedViewManager(engine).ensure_exists(view)
        sql = str(conn.execute.call_args.args[0])
        assert "WITH NO DATA" in sql

    def test_refresh_concurrently(self) -> None:
        engine, conn = self._mock_engine()
        view = src.MaterializedView(name="mv", definition_sql="SELECT 1")
        src.MaterializedViewManager(engine).refresh(view)
        sql = str(conn.execute.call_args.args[0])
        assert "REFRESH MATERIALIZED VIEW CONCURRENTLY mv" == sql

    def test_refresh_non_concurrently(self) -> None:
        engine, conn = self._mock_engine()
        view = src.MaterializedView(
            name="mv", definition_sql="SELECT 1", refresh_concurrently=False
        )
        src.MaterializedViewManager(engine).refresh(view)
        sql = str(conn.execute.call_args.args[0])
        assert "REFRESH MATERIALIZED VIEW mv" == sql


# ---------------------------------------------------------------------------
# Snapshot utilities
# ---------------------------------------------------------------------------


class TestSnapshotUtilities:
    def test_take_snapshot(self) -> None:
        order = _new_order(quantity=5.0)
        order.record_fill(quantity=5.0, price=100.0)
        snap = src.take_snapshot(order)
        assert snap.aggregate_id == order.id
        assert snap.aggregate_type == "order"
        assert snap.state["status"] == OrderStatus.FILLED.value

    def test_restore_from_snapshot(self) -> None:
        order = _new_order(quantity=5.0)
        order.record_fill(quantity=5.0, price=100.0)
        snap = src.take_snapshot(order)
        restored = src.restore_from_snapshot(src.OrderAggregate, snap)
        assert isinstance(restored, src.OrderAggregate)
        assert restored.version == snap.version
        assert restored.status is OrderStatus.FILLED
