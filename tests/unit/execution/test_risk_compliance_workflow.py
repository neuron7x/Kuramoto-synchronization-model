# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from execution import (
    ComplianceMonitor,
    OrderRequest,
    RiskComplianceWorkflow,
    RiskLimits,
    RiskManager,
    SymbolNormalizer,
    SymbolSpecification,
)


def _make_workflow() -> RiskComplianceWorkflow:
    spec = SymbolSpecification(
        symbol="BTC-USD",
        min_qty=0.0001,
        min_notional=10.0,
        step_size=0.0001,
        tick_size=0.01,
    )
    normalizer = SymbolNormalizer(specifications={spec.symbol: spec})
    compliance_monitor = ComplianceMonitor(normalizer, strict=True, auto_round=True)
    limits = RiskLimits(
        max_notional=250_000.0,
        max_position=3.0,
        max_orders_per_interval=10,
        interval_seconds=1.0,
    )
    return RiskComplianceWorkflow(RiskManager(limits), compliance_monitor)


def test_workflow_accepts_in_policy_orders() -> None:
    workflow = _make_workflow()
    orders = [
        OrderRequest(symbol="BTC-USD", side="buy", quantity=0.25, price=64_000.0),
        OrderRequest(symbol="BTC-USD", side="sell", quantity=0.15, price=63_500.0),
    ]
    assessment = workflow.evaluate(orders)
    assert assessment.passed is True
    assert len(assessment.accepted) == 2
    assert assessment.rejected == ()
    assert len(assessment.compliance_reports) == 2


def test_workflow_blocks_limit_violation() -> None:
    workflow = _make_workflow()
    violation = OrderRequest(
        symbol="BTC-USD",
        side="buy",
        quantity=5.0,
        price=65_000.0,
    )
    assessment = workflow.evaluate([violation])
    assert assessment.passed is False
    assert assessment.accepted == ()
    assert len(assessment.rejected) == 1
    assert assessment.rejected[0].risk_error is not None
    assert (
        "Position cap" in assessment.rejected[0].risk_error
        or "Notional cap" in assessment.rejected[0].risk_error
    )
