# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Deep coverage tests for execution.oms — order placement, fills, cancellation,
idempotency, error paths, state transitions, persistence and recovery."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from domain import Order, OrderStatus
from execution.connectors import ExecutionConnector, OrderError, TransientOrderError
from execution.oms import OMSConfig, OrderManagementSystem, QueuedOrder

# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class StubRiskController:
    def validate_order(self, symbol, side, qty, price):
        return None

    def register_fill(self, symbol, side, qty, price):
        return None

    def current_position(self, symbol):
        return 0.0

    def current_notional(self, symbol):
        return 0.0

    @property
    def kill_switch(self):
        return None


class DeterministicConnector(ExecutionConnector):
    def __init__(self):
        super().__init__(sandbox=True)
        self._counter = 0
        self._cancel_result = True

    def place_order(self, order, *, idempotency_key=None):
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

    def cancel_order(self, order_id):
        return self._cancel_result


class FailNTimesConnector(ExecutionConnector):
    """Fails with TransientOrderError for the first N calls, then succeeds."""

    def __init__(self, fail_count=2):
        super().__init__(sandbox=True)
        self._fail_count = fail_count
        self._calls = 0
        self._counter = 0

    def place_order(self, order, *, idempotency_key=None):
        self._calls += 1
        if self._calls <= self._fail_count:
            raise TransientOrderError(f"transient failure #{self._calls}")
        submitted = replace(order)
        if not submitted.order_id:
            submitted.mark_submitted(f"retry-{self._counter:04d}")
        self._counter += 1
        return submitted

    def cancel_order(self, order_id):
        return True


class FatalErrorConnector(ExecutionConnector):
    def place_order(self, order, *, idempotency_key=None):
        raise OrderError("permanent failure")

    def cancel_order(self, order_id):
        return False


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_oms(tmp_path):
    """Return a factory that creates OMS instances with temp state files."""

    def _make(connector=None, **config_kwargs):
        state_path = tmp_path / "oms-state.json"
        defaults = dict(
            state_path=state_path,
            auto_persist=True,
            ledger_path=None,
            pre_trade_timeout=None,
        )
        defaults.update(config_kwargs)
        config = OMSConfig(**defaults)
        conn = connector or DeterministicConnector()
        risk = StubRiskController()
        oms = OrderManagementSystem(conn, risk, config)
        return oms

    return _make


def _order(symbol="BTC/USDT", side="buy", qty=1.0, price=100.0, **kw):
    return Order(symbol=symbol, side=side, quantity=qty, price=price, **kw)


# ---------------------------------------------------------------------------
# Tests — Order placement
# ---------------------------------------------------------------------------


class TestOrderPlacement:
    def test_submit_and_process_basic(self, tmp_oms):
        oms = tmp_oms()
        order = _order()
        submitted = oms.submit(order, correlation_id="c1")
        assert submitted is order
        processed = oms.process_next()
        assert processed.order_id is not None
        assert processed.status == OrderStatus.OPEN

    def test_submit_enqueues(self, tmp_oms):
        oms = tmp_oms()
        oms.submit(_order(), correlation_id="c1")
        oms.submit(_order(), correlation_id="c2")
        assert len(oms._queue) == 2

    def test_process_all(self, tmp_oms):
        oms = tmp_oms()
        oms.submit(_order(), correlation_id="c1")
        oms.submit(_order(), correlation_id="c2")
        oms.process_all()
        assert len(oms._queue) == 0
        assert len(oms._orders) == 2

    def test_process_next_empty_queue_raises(self, tmp_oms):
        oms = tmp_oms()
        with pytest.raises(LookupError, match="No orders pending"):
            oms.process_next()


# ---------------------------------------------------------------------------
# Tests — Idempotency
# ---------------------------------------------------------------------------


class TestIdempotency:
    def test_duplicate_correlation_returns_existing_pending(self, tmp_oms):
        oms = tmp_oms()
        order = _order()
        first = oms.submit(order, correlation_id="c1")
        second = oms.submit(order, correlation_id="c1")
        assert second is first
        assert len(oms._queue) == 1

    def test_duplicate_correlation_returns_processed(self, tmp_oms):
        oms = tmp_oms()
        order = _order()
        oms.submit(order, correlation_id="c1")
        oms.process_next()
        result = oms.submit(_order(), correlation_id="c1")
        assert result.order_id is not None
        assert len(oms._queue) == 0

    def test_correlation_id_reuse_different_payload_raises(self, tmp_oms):
        oms = tmp_oms()
        oms.submit(_order(qty=1.0), correlation_id="c1")
        with pytest.raises(ValueError, match="Correlation ID reused"):
            oms.submit(_order(qty=2.0), correlation_id="c1")


# ---------------------------------------------------------------------------
# Tests — Fill handling
# ---------------------------------------------------------------------------


class TestFillHandling:
    def test_partial_fill(self, tmp_oms):
        oms = tmp_oms()
        oms.submit(_order(qty=10.0), correlation_id="c1")
        processed = oms.process_next()
        filled = oms.register_fill(processed.order_id, 3.0, 100.0)
        assert filled.status == OrderStatus.PARTIALLY_FILLED
        assert filled.filled_quantity == 3.0

    def test_full_fill(self, tmp_oms):
        oms = tmp_oms()
        oms.submit(_order(qty=5.0), correlation_id="c1")
        processed = oms.process_next()
        filled = oms.register_fill(processed.order_id, 5.0, 100.0)
        assert filled.status == OrderStatus.FILLED

    def test_multi_step_fill(self, tmp_oms):
        oms = tmp_oms()
        oms.submit(_order(qty=10.0), correlation_id="c1")
        processed = oms.process_next()
        oms.register_fill(processed.order_id, 3.0, 100.0)
        oms.register_fill(processed.order_id, 3.0, 101.0)
        filled = oms.register_fill(processed.order_id, 4.0, 102.0)
        assert filled.status == OrderStatus.FILLED
        assert filled.filled_quantity == 10.0

    def test_fill_updates_risk(self, tmp_oms):
        risk = StubRiskController()
        risk.register_fill = MagicMock()
        conn = DeterministicConnector()
        oms = tmp_oms(connector=conn)
        oms.risk = risk
        oms.submit(_order(qty=5.0), correlation_id="c1")
        processed = oms.process_next()
        oms.register_fill(processed.order_id, 5.0, 100.0)
        risk.register_fill.assert_called_once_with("BTC/USDT", "buy", 5.0, 100.0)

    def test_fill_unknown_order_raises(self, tmp_oms):
        oms = tmp_oms()
        with pytest.raises(KeyError):
            oms.register_fill("nonexistent", 1.0, 100.0)


# ---------------------------------------------------------------------------
# Tests — Cancellation
# ---------------------------------------------------------------------------


class TestCancellation:
    def test_cancel_existing_order(self, tmp_oms):
        oms = tmp_oms()
        oms.submit(_order(), correlation_id="c1")
        processed = oms.process_next()
        result = oms.cancel(processed.order_id)
        assert result is True
        assert oms._orders[processed.order_id].status == OrderStatus.CANCELLED

    def test_cancel_unknown_order_returns_false(self, tmp_oms):
        oms = tmp_oms()
        assert oms.cancel("nonexistent") is False

    def test_cancel_refused_by_connector(self, tmp_oms):
        conn = DeterministicConnector()
        conn._cancel_result = False
        oms = tmp_oms(connector=conn)
        oms.submit(_order(), correlation_id="c1")
        processed = oms.process_next()
        result = oms.cancel(processed.order_id)
        assert result is False
        assert oms._orders[processed.order_id].status == OrderStatus.OPEN


# ---------------------------------------------------------------------------
# Tests — Retry and error paths
# ---------------------------------------------------------------------------


class TestRetryAndErrors:
    def test_transient_error_retries_then_succeeds(self, tmp_oms):
        conn = FailNTimesConnector(fail_count=2)
        oms = tmp_oms(connector=conn, max_retries=5, backoff_seconds=0.0)
        oms.submit(_order(), correlation_id="c1")
        processed = oms.process_next()
        assert processed.order_id is not None
        assert processed.status == OrderStatus.OPEN

    def test_transient_error_exhausts_retries(self, tmp_oms):
        conn = FailNTimesConnector(fail_count=10)
        oms = tmp_oms(connector=conn, max_retries=3, backoff_seconds=0.0)
        oms.submit(_order(), correlation_id="c1")
        processed = oms.process_next()
        assert processed.status == OrderStatus.REJECTED

    def test_fatal_order_error_rejects_immediately(self, tmp_oms):
        conn = FatalErrorConnector()
        oms = tmp_oms(connector=conn)
        oms.submit(_order(), correlation_id="c1")
        processed = oms.process_next()
        assert processed.status == OrderStatus.REJECTED
        assert "permanent failure" in (processed.rejection_reason or "")

    def test_connector_returns_no_id_raises(self, tmp_oms):
        conn = DeterministicConnector()
        original_place = conn.place_order

        def bad_place(order, *, idempotency_key=None):
            result = original_place(order, idempotency_key=idempotency_key)
            object.__setattr__(result, "order_id", None)
            object.__setattr__(result, "status", OrderStatus.PENDING)
            return result

        conn.place_order = bad_place
        oms = tmp_oms(connector=conn)
        oms.submit(_order(), correlation_id="c1")
        with pytest.raises(RuntimeError, match="Connector returned order without ID"):
            oms.process_next()


# ---------------------------------------------------------------------------
# Tests — State transitions
# ---------------------------------------------------------------------------


class TestStateTransitions:
    def test_outstanding_returns_active_orders(self, tmp_oms):
        oms = tmp_oms()
        oms.submit(_order(), correlation_id="c1")
        oms.process_next()
        active = list(oms.outstanding())
        assert len(active) == 1
        assert active[0].status == OrderStatus.OPEN

    def test_filled_order_removed_from_active(self, tmp_oms):
        oms = tmp_oms()
        oms.submit(_order(qty=5.0), correlation_id="c1")
        processed = oms.process_next()
        assert len(list(oms.outstanding())) == 1
        oms.register_fill(processed.order_id, 5.0, 100.0)
        assert len(list(oms.outstanding())) == 0

    def test_cancelled_order_removed_from_active(self, tmp_oms):
        oms = tmp_oms()
        oms.submit(_order(), correlation_id="c1")
        processed = oms.process_next()
        oms.cancel(processed.order_id)
        assert len(list(oms.outstanding())) == 0


# ---------------------------------------------------------------------------
# Tests — Persistence and reload
# ---------------------------------------------------------------------------


class TestPersistence:
    def test_state_persisted_to_disk(self, tmp_oms, tmp_path):
        oms = tmp_oms()
        oms.submit(_order(), correlation_id="c1")
        oms.process_next()
        state_path = tmp_path / "oms-state.json"
        assert state_path.exists()
        data = json.loads(state_path.read_text())
        assert "orders" in data
        assert len(data["orders"]) == 1

    def test_reload_recovers_state(self, tmp_oms, tmp_path):
        oms = tmp_oms()
        oms.submit(_order(), correlation_id="c1")
        oms.process_next()
        # Create new OMS from same state path — should recover
        oms2 = tmp_oms()
        assert len(oms2._orders) == 1

    def test_auto_persist_false_skips_write(self, tmp_path):
        state_path = tmp_path / "no-persist.json"
        config = OMSConfig(
            state_path=state_path, auto_persist=False, ledger_path=None, pre_trade_timeout=None
        )
        conn = DeterministicConnector()
        risk = StubRiskController()
        oms = OrderManagementSystem(conn, risk, config)
        oms.submit(_order(), correlation_id="c1")
        assert not state_path.exists()


# ---------------------------------------------------------------------------
# Tests — sync_remote_state
# ---------------------------------------------------------------------------


class TestSyncRemoteState:
    def test_sync_cancelled(self, tmp_oms):
        oms = tmp_oms()
        oms.submit(_order(), correlation_id="c1")
        processed = oms.process_next()
        remote = replace(processed, status=OrderStatus.CANCELLED)
        synced = oms.sync_remote_state(remote)
        assert synced.status == OrderStatus.CANCELLED

    def test_sync_rejected(self, tmp_oms):
        oms = tmp_oms()
        oms.submit(_order(), correlation_id="c1")
        processed = oms.process_next()
        remote = replace(processed, status=OrderStatus.REJECTED, rejection_reason="venue_reject")
        synced = oms.sync_remote_state(remote)
        assert synced.status == OrderStatus.REJECTED
        assert synced.rejection_reason == "venue_reject"

    def test_sync_fill_update(self, tmp_oms):
        oms = tmp_oms()
        oms.submit(_order(qty=10.0), correlation_id="c1")
        processed = oms.process_next()
        remote = replace(
            processed, status=OrderStatus.FILLED, filled_quantity=10.0, average_price=100.0
        )
        synced = oms.sync_remote_state(remote)
        assert synced.status == OrderStatus.FILLED
        assert synced.filled_quantity == 10.0

    def test_sync_no_order_id_raises(self, tmp_oms):
        oms = tmp_oms()
        order = _order()
        with pytest.raises(ValueError, match="order must include an order_id"):
            oms.sync_remote_state(order)

    def test_sync_unknown_order_raises(self, tmp_oms):
        oms = tmp_oms()
        order = _order(order_id="unknown-123")
        with pytest.raises(LookupError, match="Unknown order_id"):
            oms.sync_remote_state(order)


# ---------------------------------------------------------------------------
# Tests — Recovery helpers
# ---------------------------------------------------------------------------


class TestRecoveryHelpers:
    def test_correlation_for(self, tmp_oms):
        oms = tmp_oms()
        oms.submit(_order(), correlation_id="c1")
        processed = oms.process_next()
        assert oms.correlation_for(processed.order_id) == "c1"

    def test_correlation_for_unknown(self, tmp_oms):
        oms = tmp_oms()
        assert oms.correlation_for("nope") is None

    def test_order_for_broker(self, tmp_oms):
        oms = tmp_oms()
        oms.submit(_order(), correlation_id="c1")
        processed = oms.process_next()
        broker_id = processed.broker_order_id
        assert oms.order_for_broker(broker_id) is processed

    def test_order_for_broker_unknown(self, tmp_oms):
        oms = tmp_oms()
        assert oms.order_for_broker("nope") is None

    def test_adopt_open_order(self, tmp_oms):
        oms = tmp_oms()
        order = _order(order_id="ext-001")
        oms.adopt_open_order(order, correlation_id="adopted-1")
        assert "ext-001" in oms._orders
        assert oms.correlation_for("ext-001") == "adopted-1"

    def test_adopt_without_id_raises(self, tmp_oms):
        oms = tmp_oms()
        order = _order()
        with pytest.raises(ValueError, match="order must have an order_id"):
            oms.adopt_open_order(order)

    def test_requeue_order(self, tmp_oms):
        oms = tmp_oms()
        oms.submit(_order(), correlation_id="c1")
        processed = oms.process_next()
        oid = processed.order_id
        corr = oms.requeue_order(oid)
        assert corr is not None
        assert len(oms._queue) == 1
        assert oid not in oms._orders

    def test_requeue_unknown_raises(self, tmp_oms):
        oms = tmp_oms()
        with pytest.raises(LookupError, match="Unknown order_id"):
            oms.requeue_order("nope")

    def test_reload(self, tmp_oms):
        oms = tmp_oms()
        oms.submit(_order(), correlation_id="c1")
        oms.process_next()
        oms.reload()
        assert len(oms._orders) == 1


# ---------------------------------------------------------------------------
# Tests — OMSConfig validation
# ---------------------------------------------------------------------------


class TestOMSConfig:
    def test_max_retries_floor(self, tmp_path):
        config = OMSConfig(state_path=tmp_path / "s.json", max_retries=0, ledger_path=None)
        assert config.max_retries == 1

    def test_negative_backoff_clamped(self, tmp_path):
        config = OMSConfig(state_path=tmp_path / "s.json", backoff_seconds=-5.0, ledger_path=None)
        assert config.backoff_seconds == 0.0

    def test_invalid_request_timeout_cleared(self, tmp_path):
        config = OMSConfig(state_path=tmp_path / "s.json", request_timeout=-1, ledger_path=None)
        assert config.request_timeout is None

    def test_invalid_pre_trade_timeout_cleared(self, tmp_path):
        config = OMSConfig(state_path=tmp_path / "s.json", pre_trade_timeout=0, ledger_path=None)
        assert config.pre_trade_timeout is None

    def test_state_path_coerced_to_path(self, tmp_path):
        config = OMSConfig(state_path=str(tmp_path / "s.json"), ledger_path=None)
        assert isinstance(config.state_path, Path)


# ---------------------------------------------------------------------------
# Tests — QueuedOrder dataclass
# ---------------------------------------------------------------------------


class TestQueuedOrder:
    def test_defaults(self):
        o = _order()
        qo = QueuedOrder(correlation_id="c1", order=o)
        assert qo.attempts == 0
        assert qo.last_error is None


# ---------------------------------------------------------------------------
# Tests — Ledger helpers
# ---------------------------------------------------------------------------


class TestLedgerHelpers:
    def test_latest_ledger_sequence_no_ledger(self, tmp_oms):
        oms = tmp_oms()
        assert oms.latest_ledger_sequence() is None

    def test_replay_ledger_from_no_ledger(self, tmp_oms):
        oms = tmp_oms()
        assert list(oms.replay_ledger_from(0)) == []
