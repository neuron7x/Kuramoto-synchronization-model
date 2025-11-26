from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from execution.risk import RiskLimits, RiskManager
from src.risk.risk_manager import KillSwitchState, RiskManagerFacade
from src.security import AccessController, AccessDeniedError, AccessPolicy


def test_facade_engages_kill_switch_with_reason() -> None:
    manager = RiskManager(RiskLimits())
    facade = RiskManagerFacade(manager)

    state = facade.engage_kill_switch("manual intervention")

    assert isinstance(state, KillSwitchState)
    assert state.engaged is True
    assert state.reason == "manual intervention"
    assert state.already_engaged is False
    assert manager.kill_switch.is_triggered() is True


def test_facade_engage_reaffirms_without_new_reason() -> None:
    manager = RiskManager(RiskLimits())
    facade = RiskManagerFacade(manager)

    first = facade.engage_kill_switch("initial reason")
    assert first.engaged is True

    reaffirmed = facade.engage_kill_switch("")
    assert reaffirmed.already_engaged is True
    assert reaffirmed.reason == "initial reason"
    assert manager.kill_switch.reason == "initial reason"


def test_facade_engage_requires_reason_for_first_activation() -> None:
    manager = RiskManager(RiskLimits())
    facade = RiskManagerFacade(manager)

    with pytest.raises(ValueError):
        facade.engage_kill_switch("   ")


def test_facade_reset_returns_previous_reason() -> None:
    manager = RiskManager(RiskLimits())
    facade = RiskManagerFacade(manager)

    facade.engage_kill_switch("investigation")
    reset_state = facade.reset_kill_switch()

    assert reset_state.engaged is False
    assert reset_state.reason == "investigation"
    assert reset_state.already_engaged is True
    assert manager.kill_switch.is_triggered() is False


def test_facade_reset_clears_stale_reason_when_disengaged() -> None:
    manager = RiskManager(RiskLimits())
    facade = RiskManagerFacade(manager)

    # Simulate a persistence layer returning a stale reason despite the switch
    # being reported as disengaged.
    manager.kill_switch._triggered = False  # type: ignore[attr-defined]
    manager.kill_switch._reason = "stale"  # type: ignore[attr-defined]

    reset_state = facade.reset_kill_switch()

    assert reset_state.engaged is False
    assert reset_state.reason == ""
    assert reset_state.already_engaged is False
    assert manager.kill_switch.reason == ""


def test_facade_state_reflects_kill_switch() -> None:
    manager = RiskManager(RiskLimits())
    facade = RiskManagerFacade(manager)

    initial = facade.kill_switch_state()
    assert initial.engaged is False
    assert initial.reason == ""

    manager.kill_switch.trigger("ops override")
    current = facade.kill_switch_state()
    assert current.engaged is True
    assert current.reason == "ops override"


def _write_policy(tmp_path: Path, payload: dict[str, object]) -> AccessController:
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    policy = AccessPolicy.load(policy_path)
    return AccessController(policy)


def test_facade_enforces_permissions_for_kill_switch(tmp_path: Path) -> None:
    controller = _write_policy(
        tmp_path,
        {
            "subjects": {
                "system": {"permissions": ["engage_kill_switch", "reset_kill_switch"]}
            },
            "roles": {
                "risk_team": {
                    "permissions": ["engage_kill_switch", "reset_kill_switch"]
                },
                "operations": {"permissions": ["read_exchange_keys"]},
            },
        },
    )

    manager = RiskManager(RiskLimits())
    facade = RiskManagerFacade(manager, access_controller=controller)

    facade.engage_kill_switch("reason", actor="alice", roles=("risk_team",))
    assert manager.kill_switch.is_triggered() is True

    with pytest.raises(AccessDeniedError):
        facade.reset_kill_switch(actor="bob", roles=("operations",))


def test_facade_updates_limits_when_authorised(tmp_path: Path) -> None:
    controller = _write_policy(
        tmp_path,
        {
            "subjects": {
                "system": {
                    "permissions": [
                        "engage_kill_switch",
                        "reset_kill_switch",
                        "modify_risk_limits",
                    ]
                }
            },
            "roles": {
                "risk": {"permissions": ["modify_risk_limits"]},
            },
        },
    )

    manager = RiskManager(RiskLimits(max_notional=1000.0, max_position=5.0))
    facade = RiskManagerFacade(manager, access_controller=controller)

    result = facade.update_risk_limits(
        actor="carol",
        roles=("risk",),
        max_notional=500.0,
        max_position=2.0,
        kill_switch_violation_threshold=5,
    )

    assert isinstance(result, RiskManager)
    assert manager.limits.max_notional == 500.0
    assert manager.limits.max_position == 2.0
    assert manager.limits.kill_switch_violation_threshold == 5

    with pytest.raises(AccessDeniedError):
        facade.update_risk_limits(actor="dave", roles=(), max_notional=750.0)
