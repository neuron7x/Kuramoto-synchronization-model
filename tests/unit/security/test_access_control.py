# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from pathlib import Path

import pytest
import yaml

from application.security.access_control import AccessController, AccessDeniedError, AccessPolicy


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
    assert not controller.is_allowed("reset_kill_switch", actor="bob", roles=("operations",))


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


def _resource_scoped_controller(tmp_path: Path) -> AccessController:
    return _load_controller(
        tmp_path,
        {
            "subjects": {
                "system": {"permissions": [{"action": "read_keys", "resources": ["binance"]}]},
            },
            "roles": {},
        },
    )


def test_whitespace_action_is_rejected(tmp_path: Path) -> None:
    """`if not action or not action.strip(): raise` — a blank action must never be evaluated.

    Under `Or -> And` a whitespace-only action ("   ") slips the guard (`not action` is False,
    so the conjunction is False) and would be normalised to "" and silently evaluated. An
    access decision on an empty action is a security hole, not a no-op.
    """
    controller = _resource_scoped_controller(tmp_path)
    with pytest.raises(ValueError, match="non-empty"):
        controller.is_allowed("   ", actor="system")
    with pytest.raises(ValueError, match="non-empty"):
        controller.is_allowed("", actor="system")


def test_missing_actor_falls_back_and_does_not_crash(tmp_path: Path) -> None:
    """`if actor and actor.strip():` selects the actor identity, else the fallback subject.

    Under `And -> Or` the default `actor=None` hits `None or None.strip()` -> AttributeError,
    crashing every fallback evaluation. The kill-switch/system paths call is_allowed WITHOUT an
    actor; they must resolve via the fallback subject.
    """
    controller = _resource_scoped_controller(tmp_path)  # fallback_subject defaults to "system"
    assert controller.is_allowed("read_keys", resource="binance") is True


def test_non_string_role_is_skipped_not_crashed(tmp_path: Path) -> None:
    """`if isinstance(role, str) and role.strip():` filters the roles iterable.

    Under `And -> Or` a non-string role hits `isinstance(x, str) or x.strip()` -> AttributeError.
    A malformed roles entry must be skipped, never crash the access check.
    """
    controller = _resource_scoped_controller(tmp_path)
    assert controller.is_allowed("read_keys", resource="binance", roles=[123, None]) is True


def test_denied_message_names_the_fallback_subject_not_none(tmp_path: Path) -> None:
    """`subject = actor or self._fallback or "unknown"` builds the denial message.

    Under `Or -> And` an actor-less denial reports `Actor 'None'` instead of the fallback
    subject -- a misleading audit trail on exactly the security-relevant path.
    """
    controller = _resource_scoped_controller(tmp_path)
    with pytest.raises(AccessDeniedError, match="system"):
        controller.require("delete_everything")  # no actor -> fallback 'system'


def test_explicit_resource_scope_is_preserved_not_widened(tmp_path: Path) -> None:
    """`resources = frozenset(cleaned or {"*"})` defaults to "*" ONLY when none were given.

    Under `Or -> And` an explicitly-scoped permission (`resources: [binance]`) collapses to
    `{"*"}`, silently widening a binance-only grant to every resource. A permission scoped to
    one resource must NOT authorise another.
    """
    controller = _resource_scoped_controller(tmp_path)
    assert controller.is_allowed("read_keys", actor="system", resource="binance") is True
    assert controller.is_allowed("read_keys", actor="system", resource="kraken") is False


def test_empty_policy_key_is_rejected(tmp_path: Path) -> None:
    """`if not isinstance(name, str) or not name.strip(): raise` guards policy keys at load.

    Under `Or -> And` an empty-string key ("") slips (`not isinstance("", str)` is False), so a
    nameless policy entry loads. Pinned by a blank subject key.
    """
    policy_path = tmp_path / "bad.yaml"
    policy_path.write_text(yaml.safe_dump({"subjects": {"": {"permissions": ["x"]}}}), "utf-8")
    with pytest.raises(ValueError, match="non-empty string keys"):
        AccessPolicy.load(policy_path)
