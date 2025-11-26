from pathlib import Path

import pytest
import yaml

from src.security import AccessController, AccessDeniedError, AccessPolicy


def _load_controller(tmp_path: Path, payload: dict[str, object]) -> AccessController:
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    policy = AccessPolicy.load(policy_path)
    return AccessController(policy)


def test_access_policy_inheritance_and_permissions(tmp_path: Path) -> None:
    controller = _load_controller(
        tmp_path,
        {
            "subjects": {
                "system": {"permissions": ["engage_kill_switch", "read_exchange_keys"]},
                "ops-service": {"inherits": ["operations"]},
            },
            "roles": {
                "operations": {"permissions": ["read_exchange_keys"]},
                "risk": {
                    "inherits": ["operations"],
                    "permissions": ["modify_risk_limits", "reset_kill_switch"],
                },
            },
        },
    )

    assert controller.is_allowed(
        "read_exchange_keys",
        actor="ops-service",
        roles=("operations",),
        resource="binance",
    )
    assert controller.is_allowed("modify_risk_limits", actor="alice", roles=("risk",))
    assert not controller.is_allowed(
        "reset_kill_switch", actor="bob", roles=("operations",)
    )


def test_access_controller_require_raises_on_denial(tmp_path: Path) -> None:
    controller = _load_controller(
        tmp_path,
        {
            "subjects": {"system": {"permissions": ["engage_kill_switch"]}},
            "roles": {"ops": {"permissions": ["read_exchange_keys"]}},
        },
    )

    controller.require("engage_kill_switch", actor="system")
    with pytest.raises(AccessDeniedError):
        controller.require("modify_risk_limits", actor="system")
