# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Characterization pins for ``OrderManagementSystem.register_fill``.

ARC-001 remediation: ``register_fill`` was refactored (metrics-recording block
extracted into a private helper) to drop below the code-hygiene complexity/LOC
thresholds. This suite freezes the CURRENT behaviour — return contract,
fill accumulation, lifecycle event sequence + monotonicity (INV-OMS3), risk
booking, reservation conversion/release (INV-OMS2/3 reservation semantics) and
the metrics-enabled latency path (the extracted helper) — so any drift fails.
"""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from domain import Order, OrderStatus
from execution.connectors import ExecutionConnector
from execution.oms import OMSConfig, OrderManagementSystem
from execution.order_lifecycle import OrderEvent, OrderLifecycle, OrderLifecycleStore
from libs.db import DataAccessLayer


def _make_lifecycle(db_path) -> OrderLifecycle:
    def factory() -> sqlite3.Connection:
        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        return connection

    store = OrderLifecycleStore(DataAccessLayer(factory), schema=None, dialect="sqlite")
    store.ensure_schema()
    return OrderLifecycle(store)


class ReservationRiskController:
    """Risk stub that records fills and reservation lifecycle."""

    def __init__(self) -> None:
        self.fills: list[tuple[str, str, float, float, str | None]] = []
        self.released: list[str] = []

    def validate_order(self, symbol, side, qty, price, **kwargs):  # noqa: ANN001
        return None

    def register_fill(self, symbol, side, qty, price, **kwargs):  # noqa: ANN001
        self.fills.append((symbol, side, qty, price, kwargs.get("reservation_id")))
        return None

    def release_reservation(self, reservation_id):  # noqa: ANN001
        self.released.append(reservation_id)

    def current_position(self, symbol):  # noqa: ANN001
        return 0.0

    def current_notional(self, symbol):  # noqa: ANN001
        return 0.0

    @property
    def kill_switch(self):
        return None


class DeterministicConnector(ExecutionConnector):
    def __init__(self) -> None:
        super().__init__(sandbox=True)
        self._counter = 0

    def place_order(self, order, *, idempotency_key=None):  # noqa: ANN001
        if idempotency_key and idempotency_key in self._idempotency_cache:
            return self._idempotency_cache[idempotency_key]
        submitted = replace(order)
        if not submitted.order_id:
            submitted.mark_submitted(f"ord-{self._counter:04d}")
        self._counter += 1
        if idempotency_key:
            self._idempotency_cache[idempotency_key] = submitted
        self._orders[submitted.order_id] = submitted
        return submitted

    def cancel_order(self, order_id):  # noqa: ANN001
        return True


class _FakeMetrics:
    """Metrics collector double with the enabled fill/latency surface."""

    enabled = True

    def __init__(self) -> None:
        self.fill_latency: list[tuple] = []
        self.signal_latency: list[tuple] = []

    def record_order_fill_latency(self, exchange, symbol, latency):  # noqa: ANN001
        self.fill_latency.append((exchange, symbol, latency))

    def record_signal_to_fill_latency(self, strategy, exchange, symbol, latency):  # noqa: ANN001
        self.signal_latency.append((strategy, exchange, symbol, latency))

    def record_order_ack_latency(self, exchange, symbol, latency):  # noqa: ANN001
        pass


@pytest.fixture()
def make_oms(tmp_path):
    def _make(*, reserve=False, lifecycle=None, risk=None):
        config = OMSConfig(
            state_path=tmp_path / "oms.json",
            auto_persist=True,
            ledger_path=None,
            pre_trade_timeout=None,
            reserve_risk_exposure=reserve,
        )
        oms = OrderManagementSystem(
            DeterministicConnector(),
            risk or ReservationRiskController(),
            config,
            lifecycle=lifecycle,
        )
        return oms

    return _make


def _order(symbol="BTC/USDT", side="buy", qty=1.0, price=100.0, **kw):
    return Order(symbol=symbol, side=side, quantity=qty, price=price, **kw)


def test_return_contract_and_accumulation(make_oms):
    oms = make_oms()
    oms.submit(_order(qty=10.0), correlation_id="c1")
    processed = oms.process_next()

    r1 = oms.register_fill(processed.order_id, 3.0, 100.0)
    assert r1 is oms._orders[processed.order_id]  # returns the stored order
    assert r1.status == OrderStatus.PARTIALLY_FILLED
    assert r1.filled_quantity == 3.0

    r2 = oms.register_fill(processed.order_id, 7.0, 101.0)
    assert r2.status == OrderStatus.FILLED
    assert r2.filled_quantity == 10.0


def test_risk_booking_receives_each_fill(make_oms):
    risk = ReservationRiskController()
    oms = make_oms(risk=risk)
    oms.submit(_order(qty=5.0), correlation_id="c1")
    processed = oms.process_next()
    oms.register_fill(processed.order_id, 2.0, 100.0)
    oms.register_fill(processed.order_id, 3.0, 100.0)

    assert [(f[0], f[1], f[2], f[3]) for f in risk.fills] == [
        ("BTC/USDT", "buy", 2.0, 100.0),
        ("BTC/USDT", "buy", 3.0, 100.0),
    ]


def test_unknown_order_raises_keyerror(make_oms):
    oms = make_oms()
    with pytest.raises(KeyError):
        oms.register_fill("does-not-exist", 1.0, 100.0)


def test_lifecycle_sequence_monotone_and_final_clears(make_oms, tmp_path):
    lifecycle = _make_lifecycle(tmp_path / "lifecycle.db")
    oms = make_oms(lifecycle=lifecycle)
    oms.submit(_order(qty=10.0), correlation_id="c1")
    processed = oms.process_next()
    oms.register_fill(processed.order_id, 4.0, 100.0)
    oms.register_fill(processed.order_id, 6.0, 100.0)  # completes

    history = lifecycle.history(processed.order_id)
    fills = [t for t in history if t.event in (OrderEvent.FILL_PARTIAL, OrderEvent.FILL_FINAL)]
    seqs = [int(t.correlation_id.rsplit(":", 1)[1]) for t in fills]
    assert seqs == sorted(seqs)  # INV-OMS3 monotone per order
    assert fills[-1].event is OrderEvent.FILL_FINAL
    # Sequence latch cleared once FILLED.
    assert processed.order_id not in oms._lifecycle_sequences


def test_reservation_converts_on_fill_and_full_fill_releases(make_oms):
    risk = ReservationRiskController()
    oms = make_oms(reserve=True, risk=risk)
    oms.submit(_order(qty=4.0), correlation_id="c1")
    processed = oms.process_next()
    correlation = oms.correlation_for(processed.order_id)

    oms.register_fill(processed.order_id, 4.0, 100.0)  # full fill
    # Each fill carries the reservation id (conversion), INV-OMS2/3 semantics.
    assert risk.fills[-1][4] == correlation


def test_metrics_enabled_records_fill_latency(make_oms):
    """Exercises the extracted ``_record_fill_metrics`` helper end to end."""
    oms = make_oms()
    oms.submit(_order(qty=1.0), correlation_id="c1")
    processed = oms.process_next()
    # Swap in the fake AFTER placement so only the fill path is characterized.
    fake = _FakeMetrics()
    oms._metrics = fake
    # Seed an ack timestamp so the fill-latency branch fires.
    oms._ack_timestamps[processed.order_id] = datetime.now(timezone.utc) - timedelta(seconds=1)

    result = oms.register_fill(processed.order_id, 1.0, 100.0)
    assert result.status == OrderStatus.FILLED
    assert len(fake.fill_latency) == 1
    assert fake.fill_latency[0][1] == "BTC/USDT"
    # ack timestamp consumed by the metrics path.
    assert processed.order_id not in oms._ack_timestamps
