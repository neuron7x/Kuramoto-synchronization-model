import pytest

from runtime.behavior_contract import (
    ActionClass,
    SystemState,
    tacl_gate,
)
from runtime.dual_approval import DualApprovalManager
from runtime.kill_switch import activate_kill_switch, deactivate_kill_switch


@pytest.fixture(autouse=True)
def reset_kill_switch():
    deactivate_kill_switch()
    yield
    deactivate_kill_switch()


def test_tacl_gate_requires_dual_approval():
    decision = tacl_gate(
        module_name="thermo_controller",
        action_class=ActionClass.A2_SYSTEMIC,
        system_state=SystemState.NORMAL,
        F_now=0.12,
        F_next=0.115,
        epsilon=0.02,
        recovery_path=True,
        dual_approved=False,
    )
    assert decision.allowed is False
    assert decision.reason == "dual_approval_missing"


def test_tacl_gate_respects_monotonicity():
    decision = tacl_gate(
        module_name="thermo_controller",
        action_class=ActionClass.A2_SYSTEMIC,
        system_state=SystemState.NORMAL,
        F_now=0.1,
        F_next=0.3,
        epsilon=0.01,
        recovery_path=False,
        dual_approved=True,
    )
    assert decision.allowed is False
    assert decision.reason == "free_energy_spike"


def test_tacl_gate_blocks_when_kill_switch_active():
    activate_kill_switch()
    decision = tacl_gate(
        module_name="thermo_controller",
        action_class=ActionClass.A1_LOCAL_CORRECTION,
        system_state=SystemState.NORMAL,
        F_now=0.1,
        F_next=0.08,
        epsilon=0.01,
        recovery_path=True,
        dual_approved=True,
    )
    assert decision.allowed is False
    assert decision.reason == "kill_switch_active"


def test_dual_approval_manager_enforces_cooldown():
    manager = DualApprovalManager(secret="s3cret", cooldown_seconds=1.0)
    token = manager.issue_service_token(action_id="thermo_topology")
    manager.validate(action_id="thermo_topology", token=token)

    with pytest.raises(ValueError) as exc:
        manager.validate(action_id="thermo_topology", token=token)

    assert "cooldown" in str(exc.value)
