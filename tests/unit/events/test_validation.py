# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for Sprint 2 — semantic event validation gate.

Covers:
    V-1 validate() is pure (no aggregate mutation).
    V-2 ValidationResult.ok / rejected construction.
    V-3 CompositeValidator short-circuits on first rejection.
    V-4 PostgresEventStore.append(..., validator=) rejects bad events
        with DomainValidationError before any row is written.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import JSON, Integer, create_engine

from core.events.sourcing import (
    ExposureUpdated,
    OrderAggregate,
    OrderCreated,
    OrderFilled,
    PortfolioAggregate,
    PostgresEventStore,
)
from core.events.validation import (
    CompositeValidator,
    DomainValidationError,
    EventValidator,
    OrderEventValidator,
    PortfolioEventValidator,
    ValidationResult,
)
from domain.order import OrderSide, OrderStatus, OrderType
from geosync.core.compat import FrozenClock


# ── Fixtures ─────────────────────────────────────────────────────────────
@pytest.fixture
def sqlite_engine(monkeypatch):
    monkeypatch.setattr("core.events.sourcing.JSONB", JSON, raising=True)
    monkeypatch.setattr("core.events.sourcing.BigInteger", Integer, raising=True)
    return create_engine("sqlite:///:memory:", future=True)


def _store(engine, clock=None):
    clock = clock or FrozenClock(instant=datetime(2026, 1, 1, tzinfo=timezone.utc))
    store = PostgresEventStore(engine, schema=None, clock=clock)
    for table in (store._events, store._snapshots):
        for col in table.columns:
            if col.name == "metadata":
                col.server_default = None
    store.create_schema()
    return store


# ── ValidationResult basics ──────────────────────────────────────────────


class TestValidationResult:
    def test_ok_is_valid(self) -> None:
        r = ValidationResult.ok()
        assert r.valid is True
        assert r.reason is None

    def test_rejected_requires_reason(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            ValidationResult.rejected("")

    def test_rejected_carries_reason(self) -> None:
        r = ValidationResult.rejected("because")
        assert r.valid is False
        assert r.reason == "because"

    def test_frozen(self) -> None:
        r = ValidationResult.ok()
        with pytest.raises(AttributeError):
            r.valid = False  # type: ignore[misc]


# ── OrderEventValidator ──────────────────────────────────────────────────


class TestOrderValidator:
    def test_accepts_healthy_create(self) -> None:
        agg = OrderAggregate.create(
            order_id="o-1",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=10.0,
            price=150.0,
            order_type=OrderType.LIMIT,
        )
        validator = OrderEventValidator()
        evt = agg.get_pending_events()[0]
        assert validator.validate(evt, agg).valid is True

    def test_rejects_zero_quantity(self) -> None:
        # Build the event directly (bypass aggregate constructor, which
        # would have its own guard post-Sprint-2).
        evt = OrderCreated(
            order_id="o-1",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=0.0,
            price=150.0,
            order_type=OrderType.LIMIT,
        )
        agg = OrderAggregate("o-1")
        result = OrderEventValidator().validate(evt, agg)
        assert not result.valid
        assert "quantity" in (result.reason or "")

    def test_rejects_limit_order_without_price(self) -> None:
        evt = OrderCreated(
            order_id="o-1",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=10.0,
            price=None,
            order_type=OrderType.LIMIT,
        )
        result = OrderEventValidator().validate(evt, OrderAggregate("o-1"))
        assert not result.valid
        assert "LIMIT" in (result.reason or "")

    def test_rejects_overfill(self) -> None:
        agg = OrderAggregate.create(
            order_id="o-1",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=10.0,
            price=150.0,
            order_type=OrderType.LIMIT,
        )
        agg.clear_pending_events()
        # Aggregate state: quantity=10, filled=0, remaining=10.
        bad = OrderFilled(
            order_id="o-1",
            fill_quantity=12.0,
            fill_price=150.0,
            cumulative_quantity=12.0,
            average_price=150.0,
            status=OrderStatus.FILLED,
        )
        result = OrderEventValidator().validate(bad, agg)
        assert not result.valid
        assert "exceeds remaining" in (result.reason or "")

    def test_pure_does_not_mutate_aggregate(self) -> None:
        agg = OrderAggregate.create(
            order_id="o-1",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=10.0,
            price=150.0,
            order_type=OrderType.LIMIT,
        )
        before_status = agg.status
        before_pending = list(agg.get_pending_events())
        validator = OrderEventValidator()
        for evt in before_pending:
            validator.validate(evt, agg)
        assert agg.status == before_status
        assert agg.get_pending_events() == before_pending


# ── PortfolioEventValidator ──────────────────────────────────────────────


class TestPortfolioValidator:
    def test_rejects_negative_exposure(self) -> None:
        agg = PortfolioAggregate.create(portfolio_id="p-1", base_currency="USD")
        agg.clear_pending_events()
        evt = ExposureUpdated(portfolio_id="p-1", exposures={"AAPL": -5.0})
        result = PortfolioEventValidator().validate(evt, agg)
        assert not result.valid
        assert "negative exposure" in (result.reason or "")

    def test_allows_zero_exposure(self) -> None:
        agg = PortfolioAggregate.create(portfolio_id="p-1", base_currency="USD")
        agg.clear_pending_events()
        evt = ExposureUpdated(portfolio_id="p-1", exposures={"AAPL": 0.0})
        assert PortfolioEventValidator().validate(evt, agg).valid is True


# ── CompositeValidator ───────────────────────────────────────────────────


class TestCompositeValidator:
    def test_short_circuits_on_first_rejection(self) -> None:
        calls: list[str] = []

        class _Rejecter:
            def validate(self, event, aggregate):
                calls.append("reject")
                return ValidationResult.rejected("nope")

        class _Accepter:
            def validate(self, event, aggregate):
                calls.append("accept")
                return ValidationResult.ok()

        agg = OrderAggregate("o-1")
        evt = OrderCreated(
            order_id="o-1",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=1.0,
            price=1.0,
            order_type=OrderType.LIMIT,
        )
        result = CompositeValidator([_Rejecter(), _Accepter()]).validate(evt, agg)
        assert not result.valid
        # Only the first delegate was called.
        assert calls == ["reject"]

    def test_ok_when_all_delegates_accept(self) -> None:
        class _Accept:
            def validate(self, event, aggregate):
                return ValidationResult.ok()

        assert (
            CompositeValidator([_Accept(), _Accept()])
            .validate(
                OrderCreated(
                    order_id="o-1",
                    symbol="AAPL",
                    side=OrderSide.BUY,
                    quantity=1.0,
                    price=1.0,
                    order_type=OrderType.LIMIT,
                ),
                OrderAggregate("o-1"),
            )
            .valid
        )


# ── Store integration ────────────────────────────────────────────────────


class TestStoreAppendValidator:
    def test_append_raises_domain_validation_error_on_reject(self, sqlite_engine) -> None:
        store = _store(sqlite_engine)
        agg = OrderAggregate.create(
            order_id=f"o-{uuid4()}",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=10.0,
            price=150.0,
            order_type=OrderType.LIMIT,
        )
        bad_events = [
            OrderFilled(
                order_id=agg.id,
                fill_quantity=100.0,
                fill_price=150.0,
                cumulative_quantity=100.0,
                average_price=150.0,
                status=OrderStatus.FILLED,
            )
        ]
        agg.clear_pending_events()
        with pytest.raises(DomainValidationError, match="exceeds remaining"):
            store.append(
                aggregate=agg,
                events=bad_events,
                expected_version=0,
                validator=OrderEventValidator(),
            )
        # Nothing persisted on rejection.
        assert store.load_stream(aggregate_id=agg.id, aggregate_type=agg.aggregate_type) == []

    def test_valid_events_still_pass(self, sqlite_engine) -> None:
        store = _store(sqlite_engine)
        agg = OrderAggregate.create(
            order_id=f"o-{uuid4()}",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=10.0,
            price=150.0,
            order_type=OrderType.LIMIT,
        )
        store.append(
            aggregate=agg,
            events=agg.get_pending_events(),
            expected_version=0,
            validator=OrderEventValidator(),
        )
        agg.clear_pending_events()
        envelopes = store.load_stream(aggregate_id=agg.id, aggregate_type=agg.aggregate_type)
        assert len(envelopes) == 1

    def test_validator_protocol_is_runtime_checkable(self) -> None:
        assert isinstance(OrderEventValidator(), EventValidator)
        assert isinstance(PortfolioEventValidator(), EventValidator)
        assert isinstance(CompositeValidator([OrderEventValidator()]), EventValidator)
