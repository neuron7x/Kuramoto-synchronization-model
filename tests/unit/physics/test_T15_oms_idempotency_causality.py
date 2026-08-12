# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T15 — OMS idempotency and lifecycle causality witnesses.

Covers two OMS invariants that have concrete surface in the production
``execution.oms.OrderManagementSystem``:

* **INV-OMS2 — idempotency**: submitting the same ``correlation_id``
  more than once must not double-book the position. The OMS's internal
  ``_processed`` map dedupes correlation IDs, so a second submit with
  the same key is a no-op after the first fill.

* **INV-OMS3 — causal order**: lifecycle events for a single order
  appear in strictly non-decreasing causal order — SUBMIT must precede
  ACK, ACK must precede any FILL, FILL events are totally ordered, and
  a CANCEL never precedes the SUBMIT it cancels.

The fixture is a minimal, deterministic clone of the pattern used by
``tests/unit/execution/test_oms_lifecycle.py``: a stub risk controller,
a deterministic in-memory connector, and an in-memory sqlite-backed
``OrderLifecycleStore``. No network, no disk persistence (auto_persist
disabled), single-threaded.
"""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from domain import Order, OrderSide, OrderType
from execution.connectors import ExecutionConnector
from execution.oms import OMSConfig, OrderManagementSystem
from execution.order_lifecycle import (
    OrderEvent,
    OrderLifecycle,
    OrderLifecycleStore,
)
from interfaces.execution import RiskController
from libs.db import DataAccessLayer

# ── Fixtures (local minimal clones of tests/unit/execution/test_oms_lifecycle.py)


class _StubRiskController(RiskController):
    """Permissive risk controller — the invariant under test is not risk."""

    def validate_order(self, symbol: str, side: str, qty: float, price: float) -> None:
        return None

    def register_fill(self, symbol: str, side: str, qty: float, price: float) -> None:
        return None

    def current_position(self, symbol: str) -> float:
        return 0.0

    def current_notional(self, symbol: str) -> float:
        return 0.0

    @property
    def kill_switch(self) -> object | None:
        return None


class _DeterministicConnector(ExecutionConnector):
    """Connector with monotonic order-id issuance for bit-reproducible tests."""

    def __init__(self) -> None:
        super().__init__(sandbox=True)
        self._counter = 0

    def place_order(self, order: Order, *, idempotency_key: str | None = None) -> Order:
        if idempotency_key is not None and idempotency_key in self._idempotency_cache:
            return self._idempotency_cache[idempotency_key]
        submitted = replace(order)
        if not submitted.order_id:
            submitted.mark_submitted(f"witness-{self._counter:04d}")
        self._counter += 1
        if idempotency_key is not None:
            self._idempotency_cache[idempotency_key] = submitted
        assert submitted.order_id is not None  # narrowing for mypy
        self._orders[submitted.order_id] = submitted
        return submitted


@pytest.fixture()
def lifecycle(tmp_path: Path) -> OrderLifecycle:
    db_path = tmp_path / "lifecycle.db"

    def factory() -> sqlite3.Connection:
        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        return connection

    store = OrderLifecycleStore(
        DataAccessLayer(factory),
        schema=None,
        dialect="sqlite",
    )
    store.ensure_schema()
    return OrderLifecycle(store, clock=lambda: datetime(2024, 1, 1, tzinfo=timezone.utc))


def _build_oms(tmp_path: Path, lifecycle_obj: OrderLifecycle) -> OrderManagementSystem:
    state_path = tmp_path / "oms-state.json"
    config = OMSConfig(state_path=state_path, auto_persist=False)
    connector = _DeterministicConnector()
    risk = _StubRiskController()
    return OrderManagementSystem(connector, risk, config, lifecycle=lifecycle_obj)


# ── INV-OMS2: idempotency under duplicate correlation_id ─────────────


def test_oms_submit_is_idempotent_under_duplicate_correlation_id(
    tmp_path: Path, lifecycle: OrderLifecycle
) -> None:
    """INV-OMS2: apply(order, order, ..., order) ≡ apply(order).

    Submits the same order with the same ``correlation_id`` five times
    and asserts that after the first submit+process_next cycle, every
    subsequent submit is a no-op: it returns the same Order instance
    (same order_id) without enqueueing new work. The lifecycle ledger
    must also record exactly one SUBMIT event across the whole group.
    """
    oms = _build_oms(tmp_path, lifecycle)
    n_replays = 5
    correlation_key = "witness-idempotent-ord-A"

    base_order = Order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        quantity=1.0,
        price=20_000.0,
        order_type=OrderType.LIMIT,
    )

    # First submit enqueues; first process_next drains the queue and
    # moves the correlation id from `_pending` to `_processed`.
    first = oms.submit(base_order, correlation_id=correlation_key)
    processed_first = oms.process_next()
    assert processed_first is not None, (
        "INV-OMS2 VIOLATED: first submit did not produce a processed order. "
        "Expected the initial submit/process_next pair to return an Order. "
        f"Observed at correlation_id={correlation_key}, seed=none. "
        "Physical reasoning: the OMS fixture is deterministic and single-"
        "threaded; the first enqueue must process immediately."
    )
    baseline_order_id = processed_first.order_id
    assert baseline_order_id is not None
    assert first.quantity == 1.0

    # Replays with the same correlation_id must return the stored Order
    # straight from `_processed`, NOT enqueue new work. The queue must
    # stay empty after every replay.
    for replay_idx in range(1, n_replays):
        replay_return = oms.submit(base_order, correlation_id=correlation_key)
        assert replay_return.order_id == baseline_order_id, (
            f"INV-OMS2 VIOLATED on replay={replay_idx}: "
            f"replay returned order_id={replay_return.order_id} ≠ "
            f"baseline={baseline_order_id}. "
            f"Expected every replay of correlation_id={correlation_key} "
            f"to return the baseline Order instance. "
            f"Observed at N={n_replays} replays, correlation_id={correlation_key}. "
            f"Physical reasoning: correlation_id is the idempotency key of "
            f"the submit API — a distinct id means duplicate booking."
        )
        # The queue must stay empty — process_next raises LookupError
        # when there is nothing to process, which is exactly the
        # observable guarantee of idempotent replay.
        with pytest.raises(LookupError):
            oms.process_next()

    # Ledger must show exactly one SUBMIT event across all replays.
    history = lifecycle.history(baseline_order_id)
    submit_events = [t for t in history if t.event == OrderEvent.SUBMIT]
    assert len(submit_events) == 1, (
        f"INV-OMS2 VIOLATED: lifecycle recorded {len(submit_events)} SUBMIT "
        f"events for a single correlation_id. "
        f"Expected exactly 1 SUBMIT per idempotent group. "
        f"Observed at N={n_replays} replays, correlation_id={correlation_key}, "
        f"seed=none. "
        f"Physical reasoning: each SUBMIT is a state transition; N replays "
        f"must collapse to 1 transition or the ledger is double-counting."
    )


# ── INV-OMS3: causal lifecycle ordering ──────────────────────────────


def test_oms_lifecycle_respects_causal_event_order(
    tmp_path: Path, lifecycle: OrderLifecycle
) -> None:
    """INV-OMS3: lifecycle events are totally ordered SUBMIT < ACK < FILL…

    Walks an order through submit → process → partial fill → final fill
    and asserts the ``lifecycle.history`` sequence respects the causal
    order: SUBMIT first, then ACK, then FILL_PARTIAL, then FILL_FINAL.
    Any out-of-order event is an INV-OMS3 violation — a non-monotone
    timeline means downstream consumers cannot reconstruct state.
    """
    oms = _build_oms(tmp_path, lifecycle)

    order = Order(
        symbol="ETHUSDT",
        side=OrderSide.SELL,
        quantity=2.0,
        price=1_800.0,
        order_type=OrderType.LIMIT,
    )

    oms.submit(order, correlation_id="witness-causal-ord-B")
    submitted = oms.process_next()
    assert submitted is not None and submitted.order_id is not None
    order_id = submitted.order_id

    oms.register_fill(order_id, 0.8, 1_795.0)
    oms.register_fill(order_id, 1.2, 1_805.0)

    history = lifecycle.history(order_id)
    event_sequence = [transition.event for transition in history]
    expected_sequence = [
        OrderEvent.SUBMIT,
        OrderEvent.ACK,
        OrderEvent.FILL_PARTIAL,
        OrderEvent.FILL_FINAL,
    ]

    assert event_sequence == expected_sequence, (
        f"INV-OMS3 VIOLATED: lifecycle event sequence {event_sequence} "
        f"≠ expected {expected_sequence}. "
        f"Expected SUBMIT → ACK → FILL_PARTIAL → FILL_FINAL in that causal "
        f"order for a two-fill round-trip. "
        f"Observed at order_id={order_id}, correlation_id=witness-causal-ord-B. "
        f"Physical reasoning: SUBMIT must precede ACK (connector ack comes "
        f"after send), ACK must precede any FILL (can't fill an unacked order), "
        f"and fills are totally ordered by their arrival sequence."
    )

    # Additional check — every pair of consecutive events must be in
    # non-decreasing time, enforcing the timestamp monotonicity clause.
    n_transitions = len(history)
    assert n_transitions >= 4, (
        f"INV-OMS3 witness incomplete: only {n_transitions} transitions "
        f"recorded. "
        f"Expected ≥ 4 (SUBMIT, ACK, FILL_PARTIAL, FILL_FINAL). "
        f"Observed at order_id={order_id}. "
        f"Physical reasoning: the two-fill flow has exactly 4 causally "
        f"ordered events; fewer means the lifecycle store swallowed one."
    )
    for prev_idx in range(n_transitions - 1):
        prev = history[prev_idx]
        curr = history[prev_idx + 1]
        assert curr.created_at >= prev.created_at, (
            f"INV-OMS3 VIOLATED: timestamp regression between "
            f"{prev.event} (t={prev.created_at}) and "
            f"{curr.event} (t={curr.created_at}). "
            f"Expected monotone non-decreasing timestamps. "
            f"Observed at order_id={order_id}, pair={prev_idx}. "
            f"Physical reasoning: the clock is monotonic and events are "
            f"logged synchronously; a regression means the store reordered "
            f"rows on readback."
        )
