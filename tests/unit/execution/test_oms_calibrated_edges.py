# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Calibrated OMS edge tests for context and recovery invariants."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from domain import Order, OrderStatus
from execution.compliance import RiskDecision
from tests.unit.execution.test_oms_guardrail_edges import _make_oms, _order, StubRiskController


class PortfolioRiskController(StubRiskController):
    def __init__(self) -> None:
        super().__init__()
        self._balance = 12_000.0
        self._peak_equity = 15_000.0
        self._gross_notional = 789.0

    def current_position(self, symbol: str) -> float:
        return 3.0 if symbol == "BTC/USDT" else 0.0


class AllowingRiskCompliance:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def check_order(
        self,
        order: Order,
        market_data: dict[str, float],
        portfolio_state: dict[str, object],
    ) -> RiskDecision:
        self.calls.append(
            {
                "symbol": order.symbol,
                "side": order.side.value,
                "quantity": float(order.quantity),
                "market_data": dict(market_data),
                "portfolio_state": dict(portfolio_state),
            }
        )
        return RiskDecision(allowed=True, reasons=(), breached_limits={})


def test_allowed_risk_compliance_receives_calibrated_portfolio_state(
    tmp_path: Path,
) -> None:
    risk = PortfolioRiskController()
    risk_compliance = AllowingRiskCompliance()
    oms = _make_oms(tmp_path, risk=risk, risk_compliance=risk_compliance)

    submitted = oms.submit(_order(quantity=2.0, price=250.0), correlation_id="corr-allowed")

    assert submitted.status == OrderStatus.PENDING
    assert len(oms._queue) == 1
    assert risk.validations == [("BTC/USDT", "buy", 2.0, 250.0)]
    assert risk_compliance.calls == [
        {
            "symbol": "BTC/USDT",
            "side": "buy",
            "quantity": 2.0,
            "market_data": {"price": 250.0},
            "portfolio_state": {
                "positions": {"BTC/USDT": 3.0},
                "gross_exposure": 789.0,
                "equity": 12_000.0,
                "peak_equity": 15_000.0,
            },
        }
    ]


def test_requeue_order_clears_remote_lookup_and_restores_pending_identity(
    tmp_path: Path,
) -> None:
    oms = _make_oms(tmp_path)
    oms.submit(_order(), correlation_id="corr-live")
    routed = oms.process_next()
    order_id = routed.order_id
    remote_id = routed.broker_order_id

    assert order_id is not None
    assert remote_id is not None
    assert oms.order_for_broker(remote_id) is routed

    correlation = oms.requeue_order(order_id)

    assert correlation == "corr-live"
    assert oms.order_for_broker(remote_id) is None
    assert oms.correlation_for(order_id) is None
    assert len(oms._queue) == 1
    assert oms._queue[0].order.order_id is None
    assert oms._queue[0].order.broker_order_id is None
    assert oms._queue[0].order.status == OrderStatus.PENDING
    assert oms._pending["corr-live"] is oms._queue[0].order
    assert "corr-live" in oms._fingerprints
