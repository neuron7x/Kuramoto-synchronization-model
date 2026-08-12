# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from tools.production_gates import (
    Gate,
    GateSeverity,
    GateStatus,
    ProductionGateValidator,
)


def test_validate_all_maps_statuses() -> None:
    """Validate that gates map to the correct status symbols."""

    def _raise() -> bool:
        raise RuntimeError("boom")

    gates = [
        Gate("pass_gate", "passes", lambda: True, severity=GateSeverity.CRITICAL, automated=True),
        Gate("fail_gate", "fails", lambda: False, severity=GateSeverity.HIGH, automated=True),
        Gate(
            "pending_gate",
            "pending",
            lambda: True,
            severity=GateSeverity.MEDIUM,
            automated=False,
        ),
        Gate("warning_gate", "warns", _raise, severity=GateSeverity.MEDIUM, automated=True),
    ]
    validator = ProductionGateValidator(gates=gates)

    statuses = validator.validate_all()

    assert statuses["pass_gate"] == GateStatus.PASS
    assert statuses["fail_gate"] == GateStatus.FAIL
    assert statuses["pending_gate"] == GateStatus.PENDING
    assert statuses["warning_gate"] == GateStatus.WARNING


def test_generate_report_contains_summary() -> None:
    """Ensure generate_report produces a readable summary."""
    gates = [
        Gate("pass_gate", "passes", lambda: True, severity=GateSeverity.CRITICAL, automated=True),
        Gate("fail_gate", "fails", lambda: False, severity=GateSeverity.HIGH, automated=True),
    ]
    validator = ProductionGateValidator(gates=gates)

    report = validator.generate_report()

    assert "pass_gate" in report
    assert "fail_gate" in report
    assert "Total Gates" in report
    assert "Production Ready?" in report


def test_as_report_payload_exposes_metadata() -> None:
    """Payload should include severity, automation flag, and symbols."""
    gate = Gate(
        "docs_complete",
        "All docs current and valid",
        lambda: True,
        severity=GateSeverity.MEDIUM,
        automated=True,
    )
    validator = ProductionGateValidator(gates=[gate])

    payload = validator.as_report_payload()

    assert "docs_complete" in payload
    item = payload["docs_complete"]
    assert item["severity"] == GateSeverity.MEDIUM.value
    assert item["status"] == GateStatus.PASS.name
    assert item["automated"] is True
    assert item["symbol"] == GateStatus.PASS.value
