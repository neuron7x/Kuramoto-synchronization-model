from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tacl import (
    ActionClass,
    ActionRequest,
    AgentState,
    Approval,
    Forecast,
    FreeEnergyInputs,
    Mandate,
    MandateRole,
    StabilizationPlan,
    SystemBand,
    TACLController,
)


@pytest.fixture
def mandate() -> Mandate:
    return Mandate(
        agent_id="agent-123",
        role=MandateRole.REMEDIATOR,
        scope="core",
        expiry=datetime.now(tz=timezone.utc) + timedelta(hours=1),
        constraints=None,
        issued_by="security",
        signature="sig",
    )


@pytest.fixture
def controller() -> TACLController:
    return TACLController()


def test_free_energy_classification(controller: TACLController) -> None:
    inputs = FreeEnergyInputs(
        resource_pressure=0.1,
        latency_risk=0.1,
        safety_violations=0.0,
        external_impact_risk=0.0,
    )
    fe, band = controller.observe_system(inputs)
    assert fe >= 0
    assert band is SystemBand.GREEN
    assert controller.state is AgentState.ACTION_POTENTIAL


def test_state_transitions(controller: TACLController) -> None:
    controller.observe_system(
        FreeEnergyInputs(
            resource_pressure=0.8,
            latency_risk=0.9,
            safety_violations=0.4,
            external_impact_risk=0.3,
        )
    )
    assert controller.state is AgentState.ELEVATED
    controller.observe_system(
        FreeEnergyInputs(
            resource_pressure=1.5,
            latency_risk=1.2,
            safety_violations=0.8,
            external_impact_risk=0.6,
        )
    )
    assert controller.state is AgentState.QUIESCED


def test_allow_action_denied_by_kill_switch(controller: TACLController, mandate: Mandate) -> None:
    controller.observe_system(
        FreeEnergyInputs(
            resource_pressure=0.1,
            latency_risk=0.1,
            safety_violations=0.0,
            external_impact_risk=0.0,
        )
    )
    controller.kill_switch.activate()
    request = ActionRequest(
        agent_id=mandate.agent_id,
        action_class=ActionClass.REMEDIATION,
        description="reduce load",
        critical=False,
        mandate=mandate,
        forecast=Forecast(fe_after=controller.current_fe - 0.1),
    )
    decision = controller.allow_action(request)
    assert not decision.allowed
    assert decision.reason == "kill-switch"
    assert decision.audit_event.decision == "deny"


def test_allow_action_requires_dual_approval(controller: TACLController, mandate: Mandate) -> None:
    controller.observe_system(
        FreeEnergyInputs(
            resource_pressure=0.2,
            latency_risk=0.2,
            safety_violations=0.1,
            external_impact_risk=0.1,
        )
    )
    plan = StabilizationPlan(
        description="scale-out",
        fe_ceiling=controller.current_fe,
        verification_steps=("monitor",),
    )
    request = ActionRequest(
        agent_id=mandate.agent_id,
        action_class=ActionClass.ADMINISTRATIVE,
        description="update config",
        critical=True,
        mandate=mandate,
        forecast=Forecast(fe_after=controller.current_fe - 0.05, stabilization_plan=plan),
        approvals=(
            Approval("approver-1", "sig", datetime.now(tz=timezone.utc), "reviewed"),
        ),
    )
    decision = controller.allow_action(request)
    assert not decision.allowed
    assert decision.reason == "missing_dual_approval"


def test_monotonic_fe_enforced(controller: TACLController, mandate: Mandate) -> None:
    controller.observe_system(
        FreeEnergyInputs(
            resource_pressure=0.2,
            latency_risk=0.2,
            safety_violations=0.1,
            external_impact_risk=0.1,
        )
    )
    request = ActionRequest(
        agent_id=mandate.agent_id,
        action_class=ActionClass.REMEDIATION,
        description="rolling restart",
        critical=False,
        mandate=mandate,
        forecast=Forecast(fe_after=controller.current_fe + 0.2),
    )
    decision = controller.allow_action(request)
    assert not decision.allowed
    assert decision.reason == "violates_monotonic_fe"


def test_monotonic_fe_with_plan_allows_action(controller: TACLController, mandate: Mandate) -> None:
    controller.observe_system(
        FreeEnergyInputs(
            resource_pressure=0.3,
            latency_risk=0.2,
            safety_violations=0.1,
            external_impact_risk=0.1,
        )
    )
    plan = StabilizationPlan(
        description="rollback",
        fe_ceiling=controller.current_fe,
        verification_steps=("check",),
    )
    request = ActionRequest(
        agent_id=mandate.agent_id,
        action_class=ActionClass.REMEDIATION,
        description="temporary throttle",
        critical=False,
        mandate=mandate,
        forecast=Forecast(fe_after=controller.current_fe + 0.1, stabilization_plan=plan),
    )
    decision = controller.allow_action(request)
    assert decision.allowed
    assert decision.audit_event.decision == "allow"


def test_audit_event_contains_expected_fields(controller: TACLController, mandate: Mandate) -> None:
    controller.observe_system(
        FreeEnergyInputs(
            resource_pressure=0.1,
            latency_risk=0.1,
            safety_violations=0.0,
            external_impact_risk=0.0,
        )
    )
    plan = StabilizationPlan(
        description="safe change",
        fe_ceiling=controller.current_fe,
        verification_steps=("verify",),
    )
    approvals = (
        Approval("approver-1", "sig1", datetime.now(tz=timezone.utc), "ok"),
        Approval("approver-2", "sig2", datetime.now(tz=timezone.utc), "ok"),
    )
    request = ActionRequest(
        agent_id=mandate.agent_id,
        action_class=ActionClass.ADMINISTRATIVE,
        description="rotate keys",
        critical=True,
        mandate=mandate,
        forecast=Forecast(fe_after=controller.current_fe - 0.05, stabilization_plan=plan),
        approvals=approvals,
        correlation_id="corr-1",
    )
    decision = controller.allow_action(request)
    assert decision.allowed
    audit = decision.audit_event
    assert audit.correlation_id == "corr-1"
    assert audit.approvals == approvals
    assert audit.decision == "allow"
    assert audit.reason is None

