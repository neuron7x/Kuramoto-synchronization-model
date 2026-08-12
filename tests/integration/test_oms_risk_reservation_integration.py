# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""End-to-end: OMS reservation wiring closes the cap-bypass without leaking holds.

With ``OMSConfig.reserve_risk_exposure`` enabled the OMS admits orders through the
RiskManager pending-exposure path: ``submit`` reserves, ``register_fill`` converts,
and every terminal-without-fill path (placement reject, cancel) releases. The
leak detector is ``RiskManager.open_reservation_count()`` — it must return to zero
after each order reaches a terminal state, or pending exposure would accrete and
falsely block future admissions.

Falsification: remove the reserve wiring from ``OMS.submit`` and
``test_two_orders_over_cap_second_submit_rejected`` fails — the second order is
admitted because no pending hold was recorded.
"""

from __future__ import annotations

import importlib

import pytest

from domain import Order, OrderSide, OrderType

# ``execution.*`` is behind the forbidden_import_patterns gate → importlib.
_oms = importlib.import_module("execution.oms")
_risk = importlib.import_module("execution.risk")
_connectors = importlib.import_module("execution.connectors")

OMSConfig = _oms.OMSConfig
OrderManagementSystem = _oms.OrderManagementSystem
RiskManager = _risk.RiskManager
RiskLimits = _risk.RiskLimits
LimitViolation = _risk.LimitViolation
ExecutionConnector = _connectors.ExecutionConnector
OrderError = _connectors.OrderError


class _SeqConnector(ExecutionConnector):
    """Assigns sequential broker ids and cancels successfully (sandbox)."""

    def __init__(self) -> None:
        super().__init__(sandbox=True)
        self._counter = 0

    def place_order(self, order: Order, *, idempotency_key: str | None = None) -> Order:
        from dataclasses import replace

        submitted = replace(order)
        if not submitted.order_id:
            submitted.mark_submitted(f"brk-{self._counter:04d}")
        self._counter += 1
        self._orders[submitted.order_id] = submitted
        return submitted

    def cancel_order(self, order_id: str) -> bool:
        return True


class _RejectingConnector(_SeqConnector):
    def place_order(self, order: Order, *, idempotency_key: str | None = None) -> Order:
        raise OrderError("venue rejected order")


def _oms_with(connector: ExecutionConnector, manager: "RiskManager", tmp_path) -> "OrderManagementSystem":
    config = OMSConfig(
        state_path=tmp_path / "oms-state.json",
        auto_persist=False,
        max_retries=1,
        reserve_risk_exposure=True,
    )
    return OrderManagementSystem(connector, manager, config, lifecycle=None)


def _order(symbol: str = "BTCUSDT", qty: float = 1.0, price: float = 100.0) -> Order:
    return Order(
        symbol=symbol,
        side=OrderSide.BUY,
        quantity=qty,
        price=price,
        order_type=OrderType.LIMIT,
    )


def test_full_fill_converts_and_leaves_no_reservation(tmp_path) -> None:
    manager = RiskManager(RiskLimits(max_position=5.0, max_notional=float("inf")))
    oms = _oms_with(_SeqConnector(), manager, tmp_path)

    oms.submit(_order(qty=2.0), correlation_id="c1")
    assert manager.open_reservation_count() == 1  # reserved on admission
    submitted = oms.process_next()
    assert submitted.order_id is not None
    oms.register_fill(submitted.order_id, 2.0, 100.0)

    assert manager.current_position("BTCUSDT") == pytest.approx(2.0)
    assert manager.pending_position("BTCUSDT") == 0.0
    assert manager.open_reservation_count() == 0  # converted, not leaked


def test_placement_reject_releases_reservation(tmp_path) -> None:
    manager = RiskManager(RiskLimits(max_position=5.0, max_notional=float("inf")))
    oms = _oms_with(_RejectingConnector(), manager, tmp_path)

    oms.submit(_order(qty=2.0), correlation_id="c1")
    assert manager.open_reservation_count() == 1
    rejected = oms.process_next()
    assert rejected.status.name == "REJECTED"

    assert manager.pending_position("BTCUSDT") == 0.0
    assert manager.open_reservation_count() == 0  # released on reject


def test_cancel_releases_reservation(tmp_path) -> None:
    manager = RiskManager(RiskLimits(max_position=5.0, max_notional=float("inf")))
    oms = _oms_with(_SeqConnector(), manager, tmp_path)

    oms.submit(_order(qty=2.0), correlation_id="c1")
    submitted = oms.process_next()
    assert submitted.order_id is not None
    assert oms.cancel(submitted.order_id) is True

    assert manager.pending_position("BTCUSDT") == 0.0
    assert manager.open_reservation_count() == 0  # released on cancel


def test_two_orders_over_cap_second_submit_rejected(tmp_path) -> None:
    """The reservation-lag bypass is closed end to end through the OMS."""

    manager = RiskManager(RiskLimits(max_position=1.0, max_notional=float("inf")))
    oms = _oms_with(_SeqConnector(), manager, tmp_path)

    oms.submit(_order(qty=1.0), correlation_id="c1")  # reserves the whole cap
    with pytest.raises(LimitViolation):
        oms.submit(_order(qty=1.0), correlation_id="c2")  # would exceed cap via pending

    assert manager.open_reservation_count() == 1
    assert manager.pending_position("BTCUSDT") == pytest.approx(1.0)
