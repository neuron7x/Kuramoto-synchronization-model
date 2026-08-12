# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Every OMS terminal path must discharge the risk reservation — no leak.

The reservation flag is only safe to enable if EVERY way an order can leave the
live set releases its hold. Prior tests covered fill / placement-reject / cancel.
These add the remaining audited paths: venue-reported cancel and reject via
sync_remote_state, and requeue. After each, open_reservation_count() must be zero
— a leak would falsely block future admissions.
"""

from __future__ import annotations

import importlib
import threading
import time
from dataclasses import replace

import pytest

from domain import Order, OrderSide, OrderStatus, OrderType

# ``execution.*`` is behind the forbidden_import_patterns gate → importlib.
_oms = importlib.import_module("execution.oms")
_risk = importlib.import_module("execution.risk")
_connectors = importlib.import_module("execution.connectors")

OMSConfig = _oms.OMSConfig
OrderManagementSystem = _oms.OrderManagementSystem
RiskManager = _risk.RiskManager
RiskLimits = _risk.RiskLimits
ExecutionConnector = _connectors.ExecutionConnector


class _SeqConnector(ExecutionConnector):
    def __init__(self) -> None:
        super().__init__(sandbox=True)
        self._counter = 0

    def place_order(self, order: Order, *, idempotency_key: str | None = None) -> Order:
        submitted = replace(order)
        if not submitted.order_id:
            submitted.mark_submitted(f"brk-{self._counter:04d}")
        self._counter += 1
        self._orders[submitted.order_id] = submitted
        return submitted

    def cancel_order(self, order_id: str) -> bool:
        return True


def _oms_with(manager: "RiskManager", tmp_path) -> "OrderManagementSystem":
    config = OMSConfig(
        state_path=tmp_path / "oms-state.json",
        auto_persist=False,
        max_retries=1,
        reserve_risk_exposure=True,
    )
    return OrderManagementSystem(_SeqConnector(), manager, config, lifecycle=None)


def _order() -> Order:
    return Order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        quantity=2.0,
        price=100.0,
        order_type=OrderType.LIMIT,
    )


def _submit_and_place(oms: "OrderManagementSystem", manager: "RiskManager", cid: str) -> Order:
    oms.submit(_order(), correlation_id=cid)
    assert manager.open_reservation_count() == 1
    placed = oms.process_next()
    assert placed.order_id is not None
    return placed


def test_sync_remote_cancel_releases_reservation(tmp_path) -> None:
    manager = RiskManager(RiskLimits(max_position=5.0, max_notional=float("inf")))
    oms = _oms_with(manager, tmp_path)
    placed = _submit_and_place(oms, manager, "c1")

    oms.sync_remote_state(replace(placed, status=OrderStatus.CANCELLED))

    assert manager.pending_position("BTCUSDT") == 0.0
    assert manager.open_reservation_count() == 0


def test_sync_remote_reject_releases_reservation(tmp_path) -> None:
    manager = RiskManager(RiskLimits(max_position=5.0, max_notional=float("inf")))
    oms = _oms_with(manager, tmp_path)
    placed = _submit_and_place(oms, manager, "c1")

    oms.sync_remote_state(
        replace(placed, status=OrderStatus.REJECTED, rejection_reason="venue reject")
    )

    assert manager.pending_position("BTCUSDT") == 0.0
    assert manager.open_reservation_count() == 0


def test_requeue_releases_the_prior_reservation(tmp_path) -> None:
    manager = RiskManager(RiskLimits(max_position=5.0, max_notional=float("inf")))
    oms = _oms_with(manager, tmp_path)
    placed = _submit_and_place(oms, manager, "c1")

    oms.requeue_order(placed.order_id)

    # The discarded order instance leaves no hold behind.
    assert manager.open_reservation_count() == 0
    assert manager.pending_position("BTCUSDT") == 0.0


def test_full_lifecycle_leaves_no_open_reservations(tmp_path) -> None:
    # A mix of terminal outcomes on distinct symbols must all net to zero holds.
    manager = RiskManager(RiskLimits(max_position=50.0, max_notional=float("inf")))
    oms = _oms_with(manager, tmp_path)

    filled = _submit_and_place(oms, manager, "fill")
    oms.register_fill(filled.order_id, 2.0, 100.0)  # convert

    cancelled = _submit_and_place(oms, manager, "cancel")
    assert oms.cancel(cancelled.order_id) is True  # release

    synced = _submit_and_place(oms, manager, "sync")
    oms.sync_remote_state(replace(synced, status=OrderStatus.CANCELLED))  # release

    assert manager.open_reservation_count() == 0


# ---------------------------------------------------------------------------
# DEFECT 2 (MED): a fill reported ONLY via venue reconciliation (sync_remote_state
# FILL branch, not the register_fill path) must book the fill into the RiskManager
# and convert/discharge its reservation. The prior code recorded lifecycle events
# only, so risk._positions under-counted real exposure and the hold leaked.
# ---------------------------------------------------------------------------
def _spy_register_fill(manager: "RiskManager") -> list:
    calls: list = []
    original = manager.register_fill

    def _spy(*args, **kwargs):
        calls.append((args, kwargs))
        return original(*args, **kwargs)

    manager.register_fill = _spy  # type: ignore[method-assign]
    return calls


def test_sync_remote_fill_books_risk_and_releases_reservation(tmp_path) -> None:
    manager = RiskManager(RiskLimits(max_position=5.0, max_notional=float("inf")))
    oms = _oms_with(manager, tmp_path)
    placed = _submit_and_place(oms, manager, "c1")
    assert manager.current_position("BTCUSDT") == 0.0
    assert manager.open_reservation_count() == 1

    calls = _spy_register_fill(manager)
    # Venue reports the order fully filled — arriving via reconciliation, NOT via
    # the normal register_fill path.
    oms.sync_remote_state(
        replace(placed, status=OrderStatus.FILLED, filled_quantity=2.0, average_price=100.0)
    )

    # risk.register_fill was invoked for the reconciled delta …
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[0] == "BTCUSDT" and args[2] == pytest.approx(2.0)
    assert kwargs.get("reservation_id") == "c1"
    # … real exposure is now counted, and the reservation is fully discharged.
    assert manager.current_position("BTCUSDT") == pytest.approx(2.0)
    assert manager.pending_position("BTCUSDT") == 0.0
    assert manager.open_reservation_count() == 0


def test_sync_remote_partial_fill_converts_partial_reservation(tmp_path) -> None:
    manager = RiskManager(RiskLimits(max_position=5.0, max_notional=float("inf")))
    oms = _oms_with(manager, tmp_path)
    placed = _submit_and_place(oms, manager, "c1")  # reserves qty=2.0

    oms.sync_remote_state(
        replace(
            placed,
            status=OrderStatus.PARTIALLY_FILLED,
            filled_quantity=1.0,
            average_price=100.0,
        )
    )

    # Half converted to actual, half still held: total exposure unchanged, no leak.
    assert manager.current_position("BTCUSDT") == pytest.approx(1.0)
    assert manager.pending_position("BTCUSDT") == pytest.approx(1.0)
    assert manager.open_reservation_count() == 1


# ---------------------------------------------------------------------------
# DEFECT 3 (MED): a pre-trade validate_order that reserves but overruns the
# ThreadPoolExecutor timeout must NOT orphan its reservation. The pooled call
# cannot be cancelled once running; the fix blocks on its completion before the
# TimeoutError reaches submit's except-handler, so the defensive release always
# sees (and discharges) the reservation the pooled call created.
# ---------------------------------------------------------------------------
def test_pre_trade_timeout_does_not_orphan_reservation(tmp_path) -> None:
    manager = RiskManager(RiskLimits(max_position=5.0, max_notional=float("inf")))
    config = OMSConfig(
        state_path=tmp_path / "oms-state.json",
        auto_persist=False,
        max_retries=1,
        reserve_risk_exposure=True,
        pre_trade_timeout=0.05,
    )
    oms = OrderManagementSystem(_SeqConnector(), manager, config, lifecycle=None)

    original_validate = manager.validate_order

    def _slow_validate(*args, **kwargs):
        # Overrun the 0.05s timeout, THEN create the reservation (the reservation
        # is only observable after the call returns — this is the orphan window).
        time.sleep(0.15)
        return original_validate(*args, **kwargs)

    manager.validate_order = _slow_validate  # type: ignore[method-assign]

    with pytest.raises(Exception):  # ComplianceViolation("Risk validation timed out")
        oms.submit(_order(), correlation_id="slow")

    # The window is closed: the reservation the pooled call created was released.
    assert manager.open_reservation_count() == 0
    assert manager.pending_position("BTCUSDT") == 0.0


# ---------------------------------------------------------------------------
# DEFECT 1 (HIGH): concurrent register_fill / process_next against a persisting
# snapshot must not raise "dict changed size during iteration", nor lose a fill
# (torn read-modify-write of filled_quantity → INV-OMS3 sequence consistency).
# ---------------------------------------------------------------------------
def test_concurrent_fills_and_registration_are_race_free(tmp_path) -> None:
    manager = RiskManager(
        RiskLimits(
            max_position=1e12,
            max_notional=float("inf"),
            max_orders_per_interval=0,  # disable throttle for the burst backlog
        )
    )
    config = OMSConfig(
        state_path=tmp_path / "oms-race.json",
        auto_persist=True,  # every mutation snapshots the shared dicts → persist race
        max_retries=1,
        reserve_risk_exposure=False,
    )
    oms = OrderManagementSystem(_SeqConnector(), manager, config, lifecycle=None)

    # One stable fill target with lots of headroom (stays PARTIALLY_FILLED).
    n_fill_threads, fills_per_thread = 4, 200
    total_fills = n_fill_threads * fills_per_thread
    target = Order(
        symbol="ETHUSDT",
        side=OrderSide.BUY,
        quantity=float(total_fills + 10),
        price=100.0,
        order_type=OrderType.LIMIT,
    )
    oms.submit(target, correlation_id="target")
    placed_target = oms.process_next()

    # A backlog of orders for the registration thread to place concurrently.
    for i in range(60):
        oms.submit(
            Order(
                symbol="ETHUSDT",
                side=OrderSide.BUY,
                quantity=1.0,
                price=100.0,
                order_type=OrderType.LIMIT,
            ),
            correlation_id=f"q{i}",
        )

    errors: list[BaseException] = []
    start = threading.Barrier(n_fill_threads + 3)

    def _fill_worker() -> None:
        start.wait()
        try:
            for _ in range(fills_per_thread):
                oms.register_fill(placed_target.order_id, 1.0, 100.0)
        except BaseException as exc:  # noqa: BLE001 - collect for assertion
            errors.append(exc)

    def _process_worker() -> None:
        start.wait()
        try:
            while True:
                try:
                    oms.process_next()
                except LookupError:
                    break
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    def _persist_worker() -> None:
        start.wait()
        try:
            for _ in range(400):
                oms._persist_state()
                list(oms.outstanding())
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=_fill_worker) for _ in range(n_fill_threads)]
    threads.append(threading.Thread(target=_process_worker))
    threads += [threading.Thread(target=_persist_worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not any(t.is_alive() for t in threads), "worker thread deadlocked / hung"
    assert errors == [], f"race raised: {errors!r}"
    # No fill lost: every record_fill's read-modify-write was serialised.
    assert placed_target.filled_quantity == pytest.approx(float(total_fills))
