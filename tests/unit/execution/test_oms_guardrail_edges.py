# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Guardrail edge tests for execution.oms.

These tests target behavior that matters operationally: fail-closed rejection,
legacy recovery safety, and deterministic state ownership. They are deliberately
small so each assertion protects an explicit invariant rather than merely
increasing aggregate coverage.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from domain import Order, OrderStatus
from execution.compliance import ComplianceReport, ComplianceViolation, RiskDecision
from execution.connectors import ExecutionConnector
from execution.oms import OMSConfig, OrderManagementSystem


class StubRiskController:
    def __init__(self) -> None:
        self.validations: list[tuple[str, str, float, float]] = []
        self.fills: list[tuple[str, str, float, float]] = []
        self.hydrated: list[dict[str, tuple[float, float]]] = []
        self._balance = 10_000.0
        self._peak_equity = 10_000.0
        self._gross_notional = 0.0

    def validate_order(self, symbol: str, side: str, qty: float, price: float) -> None:
        self.validations.append((symbol, side, qty, price))

    def register_fill(self, symbol: str, side: str, qty: float, price: float) -> None:
        self.fills.append((symbol, side, qty, price))

    def current_position(self, symbol: str) -> float:
        return 0.0

    def current_notional(self, symbol: str) -> float:
        return 0.0

    def hydrate_positions(self, positions: dict[str, tuple[float, float]]) -> None:
        self.hydrated.append(positions)

    @property
    def kill_switch(self) -> object | None:
        return None


class DeterministicConnector(ExecutionConnector):
    def __init__(self) -> None:
        super().__init__(sandbox=True)
        self._counter = 0

    def place_order(self, order: Order, *, idempotency_key: str | None = None) -> Order:
        if idempotency_key and idempotency_key in self._idempotency_cache:
            return self._idempotency_cache[idempotency_key]
        submitted = replace(order)
        if submitted.order_id is None:
            submitted.mark_submitted(f"edge-{self._counter:04d}")
        self._counter += 1
        self._orders[submitted.order_id] = submitted
        if idempotency_key:
            self._idempotency_cache[idempotency_key] = submitted
        return submitted


class CaptureAudit:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def emit(self, payload: dict[str, object]) -> None:
        self.events.append(payload)


class WarningCompliance:
    def check(self, symbol: str, quantity: float, price: float | None) -> ComplianceReport:
        return ComplianceReport(
            symbol=symbol,
            requested_quantity=quantity,
            requested_price=price,
            normalized_quantity=quantity,
            normalized_price=price,
            violations=("rounded_to_venue_grid",),
            blocked=False,
        )


class OpenCircuitBreaker:
    def __init__(self) -> None:
        self.breaches: list[str] = []

    def can_execute(self) -> bool:
        return False

    def get_last_trip_reason(self) -> str:
        return "venue_outage"

    def get_time_until_recovery(self) -> float:
        return 12.5

    def record_risk_breach(self, reason: str) -> None:
        self.breaches.append(reason)


class RejectingRiskCompliance:
    def check_order(
        self,
        order: Order,
        market_data: dict[str, float],
        portfolio_state: dict[str, object],
    ) -> RiskDecision:
        return RiskDecision(
            allowed=False,
            reasons=("gross exposure would exceed release budget",),
            breached_limits={"max_gross_exposure": 123_456.0},
        )


def _order(**overrides: object) -> Order:
    payload = {
        "symbol": "BTC/USDT",
        "side": "buy",
        "quantity": 1.0,
        "price": 100.0,
    }
    payload.update(overrides)
    return Order(**payload)


def _make_oms(
    tmp_path: Path,
    *,
    risk: StubRiskController | None = None,
    compliance_monitor: object | None = None,
    risk_compliance: object | None = None,
    circuit_breaker: object | None = None,
    audit: CaptureAudit | None = None,
) -> OrderManagementSystem:
    config = OMSConfig(
        state_path=tmp_path / "oms-state.json",
        auto_persist=True,
        ledger_path=None,
        pre_trade_timeout=None,
    )
    return OrderManagementSystem(
        DeterministicConnector(),
        risk or StubRiskController(),
        config,
        compliance_monitor=compliance_monitor,
        risk_compliance=risk_compliance,
        circuit_breaker=circuit_breaker,
        audit_logger=audit or CaptureAudit(),
    )


def test_default_ledger_path_is_scoped_to_state_file(tmp_path: Path) -> None:
    state_path = tmp_path / "nested" / "oms-state.json"

    config = OMSConfig(state_path=state_path)

    assert config.ledger_path == state_path.parent / "oms-state_ledger.jsonl"
    assert config.ledger_path.parent.exists()


def test_legacy_snapshot_without_fingerprints_is_rehydrated(tmp_path: Path) -> None:
    state_path = tmp_path / "oms-state.json"
    legacy_order = _order(order_id="legacy-001", status="open")
    state_path.write_text(
        json.dumps(
            {
                "orders": [legacy_order.to_dict()],
                "queue": [],
                "processed": {"corr-legacy": "legacy-001"},
                "correlations": {"legacy-001": "corr-legacy"},
            }
        )
    )
    config = OMSConfig(
        state_path=state_path,
        auto_persist=True,
        ledger_path=None,
        pre_trade_timeout=None,
    )

    oms = OrderManagementSystem(
        DeterministicConnector(),
        StubRiskController(),
        config,
        audit_logger=CaptureAudit(),
    )

    assert oms.correlation_for("legacy-001") == "corr-legacy"
    assert oms.order_for_broker("legacy-001") is not None
    assert oms._fingerprints["corr-legacy"] == oms._fingerprint(
        oms._orders["legacy-001"]
    )


def test_warning_compliance_audits_but_still_queues_order(tmp_path: Path) -> None:
    audit = CaptureAudit()
    risk = StubRiskController()
    oms = _make_oms(tmp_path, risk=risk, compliance_monitor=WarningCompliance(), audit=audit)

    order = oms.submit(_order(), correlation_id="corr-warning")

    assert order.status == OrderStatus.PENDING
    assert len(oms._queue) == 1
    assert risk.validations == [("BTC/USDT", "buy", 1.0, 100.0)]
    assert audit.events[-1]["event"] == "compliance_check"
    assert audit.events[-1]["status"] == "warning"


def test_open_circuit_breaker_rejects_before_risk_validation(tmp_path: Path) -> None:
    audit = CaptureAudit()
    risk = StubRiskController()
    breaker = OpenCircuitBreaker()
    oms = _make_oms(tmp_path, risk=risk, circuit_breaker=breaker, audit=audit)
    order = _order()

    with pytest.raises(ComplianceViolation, match="Circuit breaker is OPEN"):
        oms.submit(order, correlation_id="corr-circuit-open")

    assert order.status == OrderStatus.REJECTED
    assert order.rejection_reason == "Circuit breaker is OPEN: venue_outage"
    assert risk.validations == []
    assert len(oms._queue) == 0
    assert "corr-circuit-open" not in oms._fingerprints
    assert audit.events[-1]["event"] == "risk_check"
    assert audit.events[-1]["status"] == "blocked"


def test_risk_compliance_rejection_records_breach_and_cleans_idempotency(
    tmp_path: Path,
) -> None:
    audit = CaptureAudit()
    breaker = OpenCircuitBreaker()
    breaker.can_execute = lambda: True  # type: ignore[method-assign]
    oms = _make_oms(
        tmp_path,
        risk_compliance=RejectingRiskCompliance(),
        circuit_breaker=breaker,
        audit=audit,
    )
    order = _order()

    with pytest.raises(ComplianceViolation, match="Risk limit breach"):
        oms.submit(order, correlation_id="corr-risk-block")

    assert order.status == OrderStatus.REJECTED
    assert order.rejection_reason == "RISK_LIMIT_BREACH"
    assert breaker.breaches == ["gross exposure would exceed release budget"]
    assert "corr-risk-block" not in oms._fingerprints
    assert audit.events[-1]["breached_limits"] == {"max_gross_exposure": 123_456.0}


def test_adopt_filled_order_hydrates_risk_and_does_not_leave_active_order(
    tmp_path: Path,
) -> None:
    risk = StubRiskController()
    oms = _make_oms(tmp_path, risk=risk)
    recovered = _order(
        order_id="venue-777",
        status="filled",
        quantity=2.0,
        filled_quantity=2.0,
        average_price=55.0,
    )

    oms.adopt_open_order(recovered, correlation_id="corr-recovered-filled")

    assert oms.correlation_for("venue-777") == "corr-recovered-filled"
    assert list(oms.outstanding()) == []
    assert risk.hydrated == [{"BTC/USDT": (2.0, 110.0)}]
    assert "venue-777" not in oms._lifecycle_sequences
