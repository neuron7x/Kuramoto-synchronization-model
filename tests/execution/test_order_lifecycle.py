# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for execution.order_lifecycle module."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from execution.order_lifecycle import (
    TERMINAL_STATUSES,
    OrderEvent,
    OrderLifecycle,
    OrderLifecycleStore,
    _parse_timestamp,
    _quote_identifier,
    make_idempotency_key,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _SQLiteDAL:
    """Minimal DAL for testing with SQLite."""

    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row

    def execute(self, sql, params=()):
        self.conn.execute(sql, params)
        self.conn.commit()

    def fetch_one(self, sql, params=()):
        cur = self.conn.execute(sql, params)
        return cur.fetchone()

    def fetch_all(self, sql, params=()):
        cur = self.conn.execute(sql, params)
        return cur.fetchall()

    class _TxCtx:
        def __init__(self, conn):
            self._conn = conn

        def __enter__(self):
            return self._conn

        def __exit__(self, *a):
            self._conn.commit()

    def transaction(self):
        return self._TxCtx(self.conn)


def _make_store():
    dal = _SQLiteDAL()
    store = OrderLifecycleStore(dal, schema=None, table="order_journal", dialect="sqlite")
    store.ensure_schema()
    return store, dal


# ---------------------------------------------------------------------------
# _parse_timestamp
# ---------------------------------------------------------------------------


class TestParseTimestamp:
    def test_datetime_with_tz(self):
        dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
        assert _parse_timestamp(dt) == dt

    def test_datetime_naive(self):
        dt = datetime(2024, 1, 1)
        result = _parse_timestamp(dt)
        assert result.tzinfo == timezone.utc

    def test_unix_float(self):
        ts = 1704067200.0
        result = _parse_timestamp(ts)
        assert isinstance(result, datetime)
        assert result.tzinfo is not None

    def test_unix_int(self):
        result = _parse_timestamp(1704067200)
        assert isinstance(result, datetime)

    def test_iso_string(self):
        result = _parse_timestamp("2024-01-01T00:00:00Z")
        assert result.year == 2024

    def test_iso_string_no_tz(self):
        result = _parse_timestamp("2024-01-01T00:00:00")
        assert result.tzinfo is not None

    def test_bytes(self):
        result = _parse_timestamp(b"2024-01-01T00:00:00Z")
        assert result.year == 2024

    def test_invalid_type(self):
        with pytest.raises(TypeError):
            _parse_timestamp([1, 2, 3])


# ---------------------------------------------------------------------------
# _quote_identifier
# ---------------------------------------------------------------------------


class TestQuoteIdentifier:
    def test_valid(self):
        assert _quote_identifier("orders") == '"orders"'

    def test_with_underscore(self):
        assert _quote_identifier("order_journal") == '"order_journal"'

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            _quote_identifier("bad;sql")


# ---------------------------------------------------------------------------
# OrderEvent
# ---------------------------------------------------------------------------


class TestOrderEvent:
    def test_values(self):
        assert OrderEvent.SUBMIT.value == "submit"
        assert OrderEvent.ACK.value == "ack"
        assert OrderEvent.FILL_PARTIAL.value == "fill_partial"
        assert OrderEvent.FILL_FINAL.value == "fill_final"
        assert OrderEvent.CANCEL.value == "cancel"
        assert OrderEvent.REJECT.value == "reject"


# ---------------------------------------------------------------------------
# make_idempotency_key
# ---------------------------------------------------------------------------


class TestMakeIdempotencyKey:
    def test_with_correlation_id(self):
        order = MagicMock()
        key = make_idempotency_key(order, "my-corr-id")
        assert key == "corr:my-corr-id"

    def test_without_correlation_id(self):
        order = MagicMock(symbol="BTCUSD", side="buy", quantity=1.0, price=50000.0)
        key = make_idempotency_key(order)
        assert len(key) == 32
        assert isinstance(key, str)

    def test_deterministic_within_minute(self):
        order = MagicMock(symbol="BTCUSD", side="buy", quantity=1.0, price=50000.0)
        k1 = make_idempotency_key(order)
        k2 = make_idempotency_key(order)
        assert k1 == k2

    def test_different_orders_differ(self):
        o1 = MagicMock(symbol="BTCUSD", side="buy", quantity=1.0, price=50000.0)
        o2 = MagicMock(symbol="ETHUSD", side="sell", quantity=2.0, price=3000.0)
        assert make_idempotency_key(o1) != make_idempotency_key(o2)


# ---------------------------------------------------------------------------
# TERMINAL_STATUSES
# ---------------------------------------------------------------------------


def test_terminal_statuses():
    from domain import OrderStatus

    assert OrderStatus.FILLED in TERMINAL_STATUSES
    assert OrderStatus.CANCELLED in TERMINAL_STATUSES
    assert OrderStatus.REJECTED in TERMINAL_STATUSES
    assert OrderStatus.PENDING not in TERMINAL_STATUSES
    assert OrderStatus.OPEN not in TERMINAL_STATUSES


# ---------------------------------------------------------------------------
# OrderLifecycleStore (SQLite)
# ---------------------------------------------------------------------------


class TestOrderLifecycleStore:
    def test_create_sqlite_store(self):
        store, _ = _make_store()
        assert store is not None

    def test_invalid_dialect(self):
        dal = _SQLiteDAL()
        with pytest.raises(ValueError, match="dialect"):
            OrderLifecycleStore(dal, schema=None, table="t", dialect="mysql")

    def test_append_and_get(self):
        from domain import OrderStatus

        store, _ = _make_store()
        t = store.append(
            "order-1",
            "corr-1",
            OrderEvent.SUBMIT,
            from_status=OrderStatus.PENDING,
            to_status=OrderStatus.PENDING,
        )
        assert t.order_id == "order-1"
        assert t.event == OrderEvent.SUBMIT

        got = store.get("order-1", "corr-1")
        assert got is not None
        assert got.order_id == "order-1"

    def test_idempotent_append(self):
        from domain import OrderStatus

        store, _ = _make_store()
        t1 = store.append(
            "order-1",
            "corr-1",
            OrderEvent.SUBMIT,
            from_status=OrderStatus.PENDING,
            to_status=OrderStatus.PENDING,
        )
        t2 = store.append(
            "order-1",
            "corr-1",
            OrderEvent.SUBMIT,
            from_status=OrderStatus.PENDING,
            to_status=OrderStatus.PENDING,
        )
        assert t1.sequence == t2.sequence

    def test_history(self):
        from domain import OrderStatus

        store, _ = _make_store()
        store.append(
            "order-1",
            "corr-1",
            OrderEvent.SUBMIT,
            from_status=OrderStatus.PENDING,
            to_status=OrderStatus.PENDING,
        )
        store.append(
            "order-1",
            "corr-2",
            OrderEvent.ACK,
            from_status=OrderStatus.PENDING,
            to_status=OrderStatus.OPEN,
        )
        h = store.history("order-1")
        assert len(h) == 2

    def test_last_transition(self):
        from domain import OrderStatus

        store, _ = _make_store()
        store.append(
            "order-1",
            "corr-1",
            OrderEvent.SUBMIT,
            from_status=OrderStatus.PENDING,
            to_status=OrderStatus.PENDING,
        )
        store.append(
            "order-1",
            "corr-2",
            OrderEvent.ACK,
            from_status=OrderStatus.PENDING,
            to_status=OrderStatus.OPEN,
        )
        last = store.last_transition("order-1")
        assert last.event == OrderEvent.ACK

    def test_active_orders(self):
        from domain import OrderStatus

        store, _ = _make_store()
        store.append(
            "order-1",
            "corr-1",
            OrderEvent.SUBMIT,
            from_status=OrderStatus.PENDING,
            to_status=OrderStatus.PENDING,
        )
        store.append(
            "order-2",
            "corr-2",
            OrderEvent.SUBMIT,
            from_status=OrderStatus.PENDING,
            to_status=OrderStatus.PENDING,
        )
        store.append(
            "order-2",
            "corr-3",
            OrderEvent.REJECT,
            from_status=OrderStatus.PENDING,
            to_status=OrderStatus.REJECTED,
        )
        active = store.active_orders()
        assert "order-1" in active
        assert "order-2" not in active

    def test_get_nonexistent(self):
        store, _ = _make_store()
        assert store.get("no-such-order", "no-corr") is None

    def test_last_transition_nonexistent(self):
        store, _ = _make_store()
        assert store.last_transition("no-such-order") is None


# ---------------------------------------------------------------------------
# OrderLifecycle state machine
# ---------------------------------------------------------------------------


class TestOrderLifecycle:
    def _make_lifecycle(self):
        store, _ = _make_store()
        return OrderLifecycle(store)

    def test_submit_ack_fill(self):
        from domain import OrderStatus

        lc = self._make_lifecycle()
        t1 = lc.apply("o1", OrderEvent.SUBMIT, correlation_id="c1")
        assert t1.to_status == OrderStatus.PENDING

        t2 = lc.apply("o1", OrderEvent.ACK, correlation_id="c2")
        assert t2.to_status == OrderStatus.OPEN

        t3 = lc.apply("o1", OrderEvent.FILL_FINAL, correlation_id="c3")
        assert t3.to_status == OrderStatus.FILLED

    def test_submit_reject(self):
        from domain import OrderStatus

        lc = self._make_lifecycle()
        lc.apply("o1", OrderEvent.SUBMIT, correlation_id="c1")
        t = lc.apply("o1", OrderEvent.REJECT, correlation_id="c2")
        assert t.to_status == OrderStatus.REJECTED

    def test_partial_fill_flow(self):
        from domain import OrderStatus

        lc = self._make_lifecycle()
        lc.apply("o1", OrderEvent.SUBMIT, correlation_id="c1")
        lc.apply("o1", OrderEvent.ACK, correlation_id="c2")
        t = lc.apply("o1", OrderEvent.FILL_PARTIAL, correlation_id="c3")
        assert t.to_status == OrderStatus.PARTIALLY_FILLED
        t2 = lc.apply("o1", OrderEvent.FILL_FINAL, correlation_id="c4")
        assert t2.to_status == OrderStatus.FILLED

    def test_invalid_transition_raises(self):
        lc = self._make_lifecycle()
        lc.apply("o1", OrderEvent.SUBMIT, correlation_id="c1")
        with pytest.raises(ValueError, match="not permitted"):
            lc.apply("o1", OrderEvent.FILL_FINAL, correlation_id="c2")

    def test_empty_order_id_raises(self):
        lc = self._make_lifecycle()
        with pytest.raises(ValueError, match="order_id"):
            lc.apply("", OrderEvent.SUBMIT, correlation_id="c1")

    def test_empty_correlation_id_raises(self):
        lc = self._make_lifecycle()
        with pytest.raises(ValueError, match="correlation_id"):
            lc.apply("o1", OrderEvent.SUBMIT, correlation_id="")

    def test_get_state_initial(self):
        from domain import OrderStatus

        lc = self._make_lifecycle()
        assert lc.get_state("nonexistent") == OrderStatus.PENDING

    def test_get_state_after_transitions(self):
        from domain import OrderStatus

        lc = self._make_lifecycle()
        lc.apply("o1", OrderEvent.SUBMIT, correlation_id="c1")
        lc.apply("o1", OrderEvent.ACK, correlation_id="c2")
        assert lc.get_state("o1") == OrderStatus.OPEN

    def test_history(self):
        lc = self._make_lifecycle()
        lc.apply("o1", OrderEvent.SUBMIT, correlation_id="c1")
        lc.apply("o1", OrderEvent.ACK, correlation_id="c2")
        h = lc.history("o1")
        assert len(h) == 2

    def test_recover_active_orders(self):
        lc = self._make_lifecycle()
        lc.apply("o1", OrderEvent.SUBMIT, correlation_id="c1")
        lc.apply("o2", OrderEvent.SUBMIT, correlation_id="c2")
        lc.apply("o2", OrderEvent.REJECT, correlation_id="c3")
        active = lc.recover_active_orders()
        assert "o1" in active
        assert "o2" not in active

    def test_idempotent_apply(self):
        lc = self._make_lifecycle()
        t1 = lc.apply("o1", OrderEvent.SUBMIT, correlation_id="c1")
        t2 = lc.apply("o1", OrderEvent.SUBMIT, correlation_id="c1")
        assert t1.sequence == t2.sequence

    def test_cancel_from_open(self):
        from domain import OrderStatus

        lc = self._make_lifecycle()
        lc.apply("o1", OrderEvent.SUBMIT, correlation_id="c1")
        lc.apply("o1", OrderEvent.ACK, correlation_id="c2")
        t = lc.apply("o1", OrderEvent.CANCEL, correlation_id="c3")
        assert t.to_status == OrderStatus.CANCELLED
