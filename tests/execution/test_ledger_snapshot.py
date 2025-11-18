# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Tests for OrderLedger and OMSState snapshot/restore functionality."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from domain import Order, OrderSide, OrderType
from execution.order_ledger import OrderLedger
from execution.order_lifecycle import OMSState, make_idempotency_key


@pytest.fixture
def sample_order() -> Order:
    """Create a sample order for testing."""
    return Order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        quantity=0.1,
        price=20000.0,
        order_type=OrderType.LIMIT,
    )


def test_order_ledger_append_and_iter(tmp_path: Path) -> None:
    """Test that OrderLedger can append events and iterate from a given offset."""
    ledger = OrderLedger(tmp_path / "test_ledger.jsonl")

    # Append first event
    event1 = ledger.append(
        "submit",
        order={"order_id": "A", "symbol": "BTCUSDT"},
        correlation_id="corr-1",
    )
    off1 = event1.sequence

    # Append second event
    event2 = ledger.append(
        "ack",
        order={"order_id": "A", "symbol": "BTCUSDT"},
        correlation_id="corr-1",
    )
    off2 = event2.sequence

    assert off2 == off1 + 1

    # Iterate from first offset - should only see second event
    events = list(ledger.replay_from(off1 + 1))
    assert len(events) == 1
    assert events[0].event == "ack"
    assert events[0].order_id == "A"


def test_order_ledger_replay_integrity(tmp_path: Path) -> None:
    """Test that ledger replay validates digest chain integrity."""
    ledger = OrderLedger(tmp_path / "test_ledger_integrity.jsonl")

    # Append multiple events
    for i in range(5):
        ledger.append(
            f"event_{i}",
            order={"order_id": f"order_{i}"},
            metadata={"index": i},
        )

    # Replay with verification should succeed
    events = list(ledger.replay(verify=True))
    assert len(events) == 5

    # Verify sequence is monotonically increasing
    for i, event in enumerate(events):
        assert event.sequence == i + 1


def test_oms_state_apply_and_outstanding(sample_order: Order) -> None:
    """Test that OMSState can apply events and track outstanding orders."""
    oms = OMSState()

    # Create order with ID
    order_with_id = Order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        quantity=0.1,
        price=20000.0,
        order_type=OrderType.LIMIT,
    )
    order_with_id.mark_submitted("test-order-1")

    # Apply submit event
    evt_submit = {
        "type": "submit",
        "venue": "binance",
        "order": {"order_id": "test-order-1", "_obj": order_with_id},
        "ts": 123.0,
    }
    oms.apply(evt_submit)

    # Check outstanding orders
    outstanding = oms.outstanding("binance")
    assert len(outstanding) == 1
    assert outstanding[0].order_id == "test-order-1"

    # Apply ack event
    evt_ack = {
        "type": "ack",
        "venue": "binance",
        "order": {"order_id": "test-order-1", "_obj": order_with_id},
        "ts": 124.0,
    }
    oms.apply(evt_ack)

    # Still outstanding with status updated
    outstanding = oms.outstanding("binance")
    assert len(outstanding) == 1

    # Apply fill event
    evt_fill = {
        "type": "fill",
        "venue": "binance",
        "order": {"order_id": "test-order-1", "_obj": order_with_id},
        "ts": 125.0,
    }
    oms.apply(evt_fill)

    # Should no longer be outstanding
    outstanding = oms.outstanding("binance")
    assert len(outstanding) == 0


def test_oms_state_adopt_stray_orders() -> None:
    """Test that OMSState can adopt stray venue-open orders."""
    oms = OMSState()

    # Create stray orders
    stray1 = Order(
        symbol="ETHUSDT",
        side=OrderSide.SELL,
        quantity=1.0,
        price=1500.0,
        order_type=OrderType.LIMIT,
    )
    stray1.mark_submitted("stray-1")

    stray2 = Order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        quantity=0.05,
        price=21000.0,
        order_type=OrderType.LIMIT,
    )
    stray2.mark_submitted("stray-2")

    # Adopt strays
    oms.adopt("binance", [stray1, stray2])

    # Check they're now tracked
    outstanding = oms.outstanding("binance")
    assert len(outstanding) == 2
    order_ids = {o.order_id for o in outstanding}
    assert "stray-1" in order_ids
    assert "stray-2" in order_ids


def test_oms_state_snapshot_restore_roundtrip(tmp_path: Path) -> None:
    """Test that OMSState snapshot/restore preserves state correctly."""
    oms = OMSState()
    oms.set_ledger_offset(42)

    # Create and apply some orders
    order1 = Order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        quantity=0.2,
        price=20000.0,
        order_type=OrderType.LIMIT,
    )
    order1.mark_submitted("X1")

    evt = {
        "type": "submit",
        "venue": "binance",
        "order": {"order_id": "X1", "_obj": order1},
        "ts": 123.0,
    }
    oms.apply(evt)

    # Take snapshot
    snap = oms.snapshot()
    assert snap["ledger_offset"] == 42
    assert "checksum" in snap
    assert "venues" in snap
    assert "binance" in snap["venues"]

    # Persist and restore
    path = tmp_path / "oms_snap.json"
    path.write_text(json.dumps(snap), encoding="utf-8")

    restored = OMSState.restore(json.loads(path.read_text(encoding="utf-8")))

    # Verify restored state
    assert restored.last_ledger_offset() == 42
    outstanding = restored.outstanding("binance")
    assert len(outstanding) == 1
    # Handle both Order objects and dict fallbacks
    restored_order = outstanding[0]
    if hasattr(restored_order, "symbol"):
        assert restored_order.symbol == "BTCUSDT"
    elif isinstance(restored_order, dict):
        assert restored_order["symbol"] == "BTCUSDT"
    else:
        pytest.fail(f"Unexpected order type: {type(restored_order)}")


def test_oms_state_snapshot_checksum_integrity(tmp_path: Path) -> None:
    """Test that snapshot includes checksum for integrity verification."""
    oms = OMSState()
    oms.set_ledger_offset(100)

    order = Order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        quantity=0.1,
        price=20000.0,
        order_type=OrderType.LIMIT,
    )
    order.mark_submitted("check-1")

    evt = {
        "type": "submit",
        "venue": "binance",
        "order": {"order_id": "check-1", "_obj": order},
        "ts": 200.0,
    }
    oms.apply(evt)

    snap = oms.snapshot()

    # Verify checksum format
    assert "checksum" in snap
    assert snap["checksum"].startswith("sha256:")

    # Verify checksum is deterministic
    snap2 = oms.snapshot()
    assert snap["checksum"] == snap2["checksum"]


def test_make_idempotency_key_with_correlation_id() -> None:
    """Test that make_idempotency_key uses correlation_id when provided."""
    order = Order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        quantity=0.1,
        price=20000.0,
        order_type=OrderType.LIMIT,
    )

    key = make_idempotency_key(order, correlation_id="my-correlation-123")
    assert key == "corr:my-correlation-123"


def test_make_idempotency_key_deterministic() -> None:
    """Test that make_idempotency_key is deterministic for same order."""
    order1 = Order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        quantity=0.1,
        price=20000.0,
        order_type=OrderType.LIMIT,
    )

    order2 = Order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        quantity=0.1,
        price=20000.0,
        order_type=OrderType.LIMIT,
    )

    # Within the same minute bucket, keys should match
    key1 = make_idempotency_key(order1)
    key2 = make_idempotency_key(order2)
    assert key1 == key2

    # Different order should have different key
    order3 = Order(
        symbol="ETHUSDT",  # Different symbol
        side=OrderSide.BUY,
        quantity=0.1,
        price=20000.0,
        order_type=OrderType.LIMIT,
    )
    key3 = make_idempotency_key(order3)
    assert key3 != key1


def test_ledger_last_offset(tmp_path: Path) -> None:
    """Test that ledger tracks the last sequence correctly."""
    ledger = OrderLedger(tmp_path / "offset_test.jsonl")

    # Initially should have no events
    latest = ledger.latest_event(verify=False)
    assert latest is None

    event1 = ledger.append("event1", metadata={"test": True})
    assert event1.sequence >= 1

    event2 = ledger.append("event2", metadata={"test": True})
    assert event2.sequence > event1.sequence

    # Latest event should be event2
    latest = ledger.latest_event(verify=False)
    assert latest is not None
    assert latest.sequence == event2.sequence
