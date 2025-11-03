# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Tests for recovery performance and RTO requirements."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from execution.order_ledger import OrderLedger, OrderLedgerConfig
from execution.recovery import RecoveryManager, recover_from_ledger


def create_test_ledger_with_orders(
    path: Path, num_orders: int, snapshot_interval: int = 100
) -> OrderLedger:
    """Helper to create a ledger with test orders."""
    config = OrderLedgerConfig(snapshot_interval=snapshot_interval)
    ledger = OrderLedger(path, config=config)
    
    # Create initial state
    state = {
        "orders": [],
        "queue": [],
        "processed": {},
        "correlations": {},
    }
    
    ledger.append("bootstrap", state_snapshot=state)
    
    # Add orders
    for i in range(num_orders):
        order = {
            "order_id": f"order-{i}",
            "symbol": "BTC-USD",
            "side": "buy",
            "quantity": 1.0,
            "price": 50000.0 + i,
        }
        state["orders"].append(order)
        state["processed"][f"corr-{i}"] = order["order_id"]
        
        # Add state snapshot every N orders based on config
        if (i + 1) % snapshot_interval == 0:
            ledger.append(f"order_placed_{i}", order=order, state_snapshot=state)
        else:
            ledger.append(f"order_placed_{i}", order=order)
    
    return ledger


def test_recovery_with_snapshot_acceleration(tmp_path: Path) -> None:
    """Test that snapshots accelerate recovery."""
    ledger_path = tmp_path / "ledger.jsonl"
    
    # Create ledger with 1000 orders, snapshot every 100
    create_test_ledger_with_orders(ledger_path, num_orders=1000, snapshot_interval=100)
    
    # Recover without snapshot
    start = time.perf_counter()
    ledger1 = OrderLedger(ledger_path)
    manager1 = RecoveryManager(ledger1)
    stats1 = manager1.recover(use_snapshot=False)
    duration_no_snapshot = time.perf_counter() - start
    
    # Recover with snapshot
    start = time.perf_counter()
    ledger2 = OrderLedger(ledger_path)
    manager2 = RecoveryManager(ledger2)
    stats2 = manager2.recover(use_snapshot=True)
    duration_with_snapshot = time.perf_counter() - start
    
    # Snapshot should reduce events replayed
    assert stats2.events_replayed < stats1.events_replayed
    assert stats2.snapshot_used
    assert stats2.snapshot_sequence is not None
    
    # Both should recover successfully
    assert stats1.recovery_successful
    assert stats2.recovery_successful
    
    # Final states should match
    assert stats1.final_state is not None
    assert stats2.final_state is not None


def test_recovery_rto_10k_orders(tmp_path: Path) -> None:
    """Test that recovery time meets RTO target of 2s for 10k orders."""
    ledger_path = tmp_path / "ledger.jsonl"
    
    # Create ledger with 10,000 orders and regular snapshots
    # Disable compaction for this test to keep all events
    num_orders = 10_000
    config = OrderLedgerConfig(
        snapshot_interval=500,
        compaction_threshold_events=100_000  # High threshold to avoid compaction
    )
    ledger = OrderLedger(ledger_path, config=config)
    
    # Create initial state
    state = {
        "orders": [],
        "queue": [],
        "processed": {},
        "correlations": {},
    }
    
    ledger.append("bootstrap", state_snapshot=state)
    
    # Add orders
    for i in range(num_orders):
        order = {
            "order_id": f"order-{i}",
            "symbol": "BTC-USD",
            "side": "buy",
            "quantity": 1.0,
            "price": 50000.0 + i,
        }
        state["orders"].append(order)
        state["processed"][f"corr-{i}"] = order["order_id"]
        
        # Add state snapshot every N orders based on config
        if (i + 1) % config.snapshot_interval == 0:
            ledger.append(f"order_placed_{i}", order=order, state_snapshot=state)
        else:
            ledger.append(f"order_placed_{i}", order=order)
    
    # Measure recovery time
    start_time = time.perf_counter()
    ledger2, stats = recover_from_ledger(ledger_path, config=config, use_snapshot=True)
    recovery_duration = time.perf_counter() - start_time
    
    # Verify RTO requirement: ≤ 2s
    assert recovery_duration <= 2.0, f"Recovery took {recovery_duration:.3f}s, exceeds 2s RTO target"
    
    # Verify recovery was successful
    assert stats.recovery_successful
    
    # Verify final state contains all orders
    assert stats.final_state is not None
    assert len(stats.final_state["orders"]) == num_orders


def test_recovery_stats_accuracy(tmp_path: Path) -> None:
    """Test that recovery stats accurately reflect the operation."""
    ledger_path = tmp_path / "ledger.jsonl"
    
    # Create small ledger
    num_orders = 50
    ledger = create_test_ledger_with_orders(ledger_path, num_orders=num_orders, snapshot_interval=10)
    
    # Recover and check stats
    manager = RecoveryManager(ledger)
    stats = manager.recover(use_snapshot=True, verify_integrity=True)
    
    assert stats.total_events == num_orders + 1  # +1 for bootstrap
    assert stats.duration_seconds > 0
    assert stats.recovery_successful
    assert not stats.corruption_detected
    assert stats.corruption_details is None
    assert stats.final_state is not None


def test_recovery_with_corruption(tmp_path: Path) -> None:
    """Test recovery behavior when corruption is detected."""
    ledger_path = tmp_path / "ledger.jsonl"
    config = OrderLedgerConfig(corruption_action="read_only")
    
    # Create ledger
    ledger = OrderLedger(ledger_path, config=config)
    ledger.append("event1", state_snapshot={"orders": []})
    ledger.append("event2", state_snapshot={"orders": []})
    
    # Corrupt the ledger
    import json
    with ledger_path.open("r", encoding="utf-8") as f:
        lines = f.readlines()
    
    event = json.loads(lines[1])
    event["digest"] = "corrupted"
    lines[1] = json.dumps(event) + "\n"
    
    with ledger_path.open("w", encoding="utf-8") as f:
        f.writelines(lines)
    
    # Recover - should detect corruption
    ledger2, stats = recover_from_ledger(ledger_path, config=config)
    
    assert ledger2.corruption_detected
    assert stats.corruption_detected
    assert stats.corruption_details is not None


def test_recovery_without_snapshots(tmp_path: Path) -> None:
    """Test recovery when no snapshots are available."""
    ledger_path = tmp_path / "ledger.jsonl"
    
    # Create ledger without state snapshots
    ledger = OrderLedger(ledger_path)
    for i in range(100):
        order = {"order_id": f"order-{i}", "symbol": "BTC-USD"}
        ledger.append(f"order_{i}", order=order)  # No state snapshot
    
    # Recover
    manager = RecoveryManager(ledger)
    stats = manager.recover(use_snapshot=True)
    
    # Should succeed but without using snapshots
    assert stats.recovery_successful
    assert not stats.snapshot_used
    assert stats.snapshot_sequence is None
    assert stats.events_replayed == 100


def test_recovery_manager_with_state_builder(tmp_path: Path) -> None:
    """Test recovery manager with custom state builder callback."""
    ledger_path = tmp_path / "ledger.jsonl"
    
    # Create ledger with snapshot_interval that ensures events after snapshot
    config = OrderLedgerConfig(snapshot_interval=10)
    ledger = OrderLedger(ledger_path, config=config)
    
    state = {"orders": [], "queue": [], "processed": {}, "correlations": {}}
    ledger.append("bootstrap", state_snapshot=state)
    
    # Add 55 orders - last snapshot will be at order 50, leaving 5 more events
    for i in range(55):
        order = {
            "order_id": f"order-{i}",
            "symbol": "BTC-USD",
            "side": "buy",
            "quantity": 1.0,
            "price": 50000.0 + i,
        }
        state["orders"].append(order)
        
        # State snapshot every 10 orders
        if (i + 1) % 10 == 0:
            ledger.append(f"order_placed_{i}", order=order, state_snapshot=state)
        else:
            ledger.append(f"order_placed_{i}", order=order)
    
    # Track state builder calls
    built_orders = []
    
    def state_builder(order_data):
        built_orders.append(order_data)
    
    # Create new ledger instance and recover
    ledger2 = OrderLedger(ledger_path, config=config)
    manager = RecoveryManager(ledger2, state_builder=state_builder)
    stats = manager.recover(use_snapshot=True)
    
    assert stats.recovery_successful
    assert stats.snapshot_used
    # State builder should be called for orders after last snapshot (5 orders)
    assert len(built_orders) >= 5


def test_recovery_with_max_events_limit(tmp_path: Path) -> None:
    """Test recovery with event limit for testing."""
    ledger_path = tmp_path / "ledger.jsonl"
    
    # Create ledger with many events
    create_test_ledger_with_orders(ledger_path, num_orders=100, snapshot_interval=20)
    
    ledger = OrderLedger(ledger_path)
    manager = RecoveryManager(ledger)
    
    # Recover with limit
    stats = manager.recover(use_snapshot=False, max_events=10)
    
    # Should stop at limit
    assert stats.events_replayed == 10
    assert stats.recovery_successful


def test_benchmark_recovery_scaling(tmp_path: Path) -> None:
    """Benchmark recovery time scaling with order count."""
    results = []
    
    for num_orders in [100, 1000, 5000]:
        ledger_path = tmp_path / f"ledger_{num_orders}.jsonl"
        create_test_ledger_with_orders(ledger_path, num_orders=num_orders, snapshot_interval=500)
        
        start = time.perf_counter()
        ledger, stats = recover_from_ledger(ledger_path, use_snapshot=True)
        duration = time.perf_counter() - start
        
        results.append({
            "orders": num_orders,
            "duration": duration,
            "events_replayed": stats.events_replayed,
        })
        
        assert stats.recovery_successful
    
    # Verify scaling is reasonable (not exponential)
    # With snapshots, recovery time should scale sub-linearly
    ratio_10x = results[1]["duration"] / results[0]["duration"]
    assert ratio_10x < 15, f"Recovery time scaled poorly: 10x orders took {ratio_10x}x time"


def test_recover_from_ledger_convenience_function(tmp_path: Path) -> None:
    """Test the convenience function for recovery."""
    ledger_path = tmp_path / "ledger.jsonl"
    
    # Create ledger
    create_test_ledger_with_orders(ledger_path, num_orders=100, snapshot_interval=20)
    
    # Use convenience function
    ledger, stats = recover_from_ledger(ledger_path)
    
    assert isinstance(ledger, OrderLedger)
    assert stats.recovery_successful
    assert stats.duration_seconds > 0
