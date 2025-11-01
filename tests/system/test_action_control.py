"""Tests for the action control governor enforcing TACL and mandate rules."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.audit.audit_logger import AuditLogger
from src.audit.stores import AuditLedgerEntry

from src.system.action_control import (
    ActionClass,
    ActionGovernor,
    ActionIntent,
    AuditLoggerActionSink,
    FreeEnergyForecast,
    Mandate,
    StatePermission,
    SystemState,
    TaclGate,
)


@dataclass
class _MemoryStore:
    entries: list[AuditLedgerEntry]

    def __init__(self) -> None:
        self.entries = []

    def append(self, record):  # type: ignore[override]
        entry = AuditLedgerEntry(
            sequence=len(self.entries),
            record=record,
            record_hash=f"hash-{len(self.entries)}",
            chain_hash=f"chain-{len(self.entries)}",
        )
        self.entries.append(entry)
        return entry


def _make_governor(store: _MemoryStore) -> ActionGovernor:
    state_permissions = {
        SystemState.NORMAL: StatePermission(
            allowed_classes=frozenset({ActionClass.A0, ActionClass.A1}),
        ),
        SystemState.DEGRADED: StatePermission(
            allowed_classes=frozenset({ActionClass.A0, ActionClass.A1, ActionClass.A2}),
        ),
        SystemState.CRISIS: StatePermission(
            allowed_classes=frozenset({ActionClass.A0, ActionClass.A1, ActionClass.A2}),
            manual_corridor=frozenset({"activate-crisis-fallback"}),
        ),
    }
    mandate = Mandate(
        module="planner",
        allowed_classes=frozenset({ActionClass.A0, ActionClass.A1, ActionClass.A2}),
        object_scope=frozenset({"buffers", "links"}),
        state_permissions=state_permissions,
    )
    audit_logger = AuditLogger(secret="test-secret", store=store)
    audit_sink = AuditLoggerActionSink(audit_logger, ip_address="10.0.0.1")
    return ActionGovernor(
        {"planner": mandate}, tacl_gate=TaclGate(max_free_energy=1.4), audit_sink=audit_sink
    )


def _latest_details(store: _MemoryStore) -> dict[str, object]:
    assert store.entries, "expected at least one audit entry"
    return store.entries[-1].record.details


def test_a1_action_allows_when_energy_descends_and_mandate_ok() -> None:
    store = _MemoryStore()
    governor = _make_governor(store)
    intent = ActionIntent(
        module="planner",
        action_class=ActionClass.A1,
        operation="retune-buffer",
        description="retune buffer thresholds",
        target="buffers",
    )
    forecast = FreeEnergyForecast(current=1.2, projected=1.1)

    decision = governor.evaluate(intent, state=SystemState.NORMAL, forecast=forecast)

    assert decision.allowed is True
    assert decision.tacl is not None and decision.tacl.allowed is True
    details = _latest_details(store)
    assert details["allowed"] is True
    assert details["mandate_allowed"] is True
    assert details["tacl_allowed"] is True
    assert details["forecast"]["current"] == pytest.approx(1.2)
    assert details["forecast"]["projected"] == pytest.approx(1.1)


def test_a1_action_blocked_when_energy_increases_without_recovery() -> None:
    store = _MemoryStore()
    governor = _make_governor(store)
    intent = ActionIntent(
        module="planner",
        action_class=ActionClass.A1,
        operation="retune-buffer",
        description="retune buffer thresholds",
        target="buffers",
    )
    forecast = FreeEnergyForecast(current=1.2, projected=1.3)

    decision = governor.evaluate(intent, state=SystemState.NORMAL, forecast=forecast)

    assert decision.allowed is False
    assert decision.tacl is not None and decision.tacl.allowed is False
    assert (
        decision.reason
        == "projected free energy increases without a guaranteed recovery path"
    )
    details = _latest_details(store)
    assert details["allowed"] is False
    assert details["tacl_allowed"] is False
    assert details["mandate_allowed"] is True


def test_a2_requires_state_permission_and_manual_corridor() -> None:
    store = _MemoryStore()
    governor = _make_governor(store)
    intent = ActionIntent(
        module="planner",
        action_class=ActionClass.A2,
        operation="switch-link",
        description="switch primary link protocol",
        target="links",
    )
    forecast = FreeEnergyForecast(current=1.1, projected=1.0)

    # Not permitted in normal state
    decision = governor.evaluate(intent, state=SystemState.NORMAL, forecast=forecast)
    assert decision.allowed is False
    assert decision.mandate.allowed is False
    assert decision.reason == "action class A2 not permitted in state"

    # Crisis state requires operation to be part of the manual corridor
    crisis_intent = ActionIntent(
        module="planner",
        action_class=ActionClass.A2,
        operation="activate-crisis-fallback",
        description="activate pre-approved crisis fallback",
        target="links",
    )
    crisis_decision = governor.evaluate(
        crisis_intent,
        state=SystemState.CRISIS,
        forecast=forecast,
    )
    assert crisis_decision.allowed is True
    assert crisis_decision.mandate.allowed is True
    assert crisis_decision.mandate.engaged_corridor is True
    details = _latest_details(store)
    assert details["manual_corridor"] is True
    assert details["allowed"] is True


def test_non_passive_actions_require_forecast() -> None:
    store = _MemoryStore()
    governor = _make_governor(store)
    intent = ActionIntent(
        module="planner",
        action_class=ActionClass.A2,
        operation="activate-crisis-fallback",
        description="activate pre-approved crisis fallback",
        target="links",
    )

    with pytest.raises(ValueError, match="Free energy forecast required"):
        governor.evaluate(intent, state=SystemState.DEGRADED)
