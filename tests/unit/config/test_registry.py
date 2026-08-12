# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the centralized configuration registry."""

from __future__ import annotations

from typing import Mapping

import pytest
from packaging.version import Version

from core.config.registry import (
    ConfigApprovalError,
    ConfigCompatibilityError,
    ConfigPublicationError,
    ConfigRegistry,
    ConfigValidationError,
    Environment,
)


def _base_payload(**overrides: object) -> Mapping[str, object]:
    payload = {
        "schema_version": 2,
        "limits": {"risk": 10_000, "exposure": 250_000},
        "features": ["alpha", "beta"],
    }
    payload.update(overrides)
    return payload


def test_register_and_list_versions() -> None:
    registry = ConfigRegistry()
    version = registry.register_profile(
        "alpha-strategy",
        "1.0.0",
        _base_payload(),
        actor="researcher",
        change_reason="Initial rollout",
    )

    assert version == Version("1.0.0")
    assert registry.list_versions("alpha-strategy") == [Version("1.0.0")]
    assert registry.get_active_version("alpha-strategy", Environment.STAGE) is None


def test_publish_requires_sufficient_approvals() -> None:
    registry = ConfigRegistry()
    registry.register_profile(
        "alpha-strategy",
        "1.0.0",
        _base_payload(),
        actor="quant",
        required_approvals=2,
    )

    with pytest.raises(ConfigApprovalError):
        registry.publish_profile(
            "alpha-strategy",
            "1.0.0",
            actor="deployer",
            environments=[Environment.STAGE],
        )

    registry.approve_profile(
        "alpha-strategy",
        "1.0.0",
        approver="risk-officer",
    )

    with pytest.raises(ConfigApprovalError):
        registry.publish_profile(
            "alpha-strategy",
            "1.0.0",
            actor="deployer",
            environments=[Environment.STAGE],
        )

    registry.approve_profile(
        "alpha-strategy",
        "1.0.0",
        approver="qa-lead",
    )

    registry.publish_profile(
        "alpha-strategy",
        "1.0.0",
        actor="deployer",
        environments=[Environment.STAGE],
    )

    assert registry.get_active_version("alpha-strategy", Environment.STAGE) == Version("1.0.0")


def test_validator_enforced() -> None:
    def validator(_: str, payload: Mapping[str, object]) -> None:
        limit = payload.get("limits", {}).get("risk", 0)
        if not isinstance(limit, (int, float)) or limit <= 0:
            raise ValueError("risk limit must be positive")

    registry = ConfigRegistry(validators=[validator])

    with pytest.raises(ConfigValidationError):
        registry.register_profile(
            "alpha-strategy",
            "1.0.0",
            _base_payload(limits={"risk": 0}),
            actor="quant",
        )

    registry.register_profile(
        "alpha-strategy",
        "1.0.1",
        _base_payload(limits={"risk": 50_000}),
        actor="quant",
    )


def test_compatibility_policy_blocks_incompatible_payload() -> None:
    class SchemaPolicy:
        def __init__(self, expected_schema: int) -> None:
            self._expected_schema = expected_schema

        def ensure(
            self,
            profile_name: str,
            version: Version,
            payload: Mapping[str, object],
        ) -> None:
            if payload.get("schema_version") != self._expected_schema:
                raise ConfigCompatibilityError(
                    f"Profile {profile_name} v{version} incompatible with runtime"
                )

    registry = ConfigRegistry(compatibility_policies=[SchemaPolicy(expected_schema=2)])
    registry.register_profile(
        "alpha-strategy",
        "1.0.0",
        _base_payload(schema_version=2),
        actor="quant",
        required_approvals=0,
    )
    registry.publish_profile(
        "alpha-strategy",
        "1.0.0",
        actor="deployer",
        environments=[Environment.STAGE],
    )

    registry.register_profile(
        "alpha-strategy",
        "1.1.0",
        _base_payload(schema_version=1),
        actor="quant",
        required_approvals=0,
    )

    with pytest.raises(ConfigCompatibilityError):
        registry.publish_profile(
            "alpha-strategy",
            "1.1.0",
            actor="deployer",
            environments=[Environment.STAGE],
        )


def test_release_checks_run_for_production_promotions() -> None:
    calls: list[tuple[str, Version, Mapping[str, object]]] = []

    def release_check(profile: str, version: Version, payload: Mapping[str, object]) -> None:
        calls.append((profile, version, payload))

    registry = ConfigRegistry(release_checks=[release_check])
    registry.register_profile(
        "alpha-strategy",
        "2.0.0",
        _base_payload(),
        actor="quant",
        required_approvals=0,
    )

    registry.publish_profile(
        "alpha-strategy",
        "2.0.0",
        actor="release",
        environments=[Environment.PROD],
    )

    assert calls == [
        (
            "alpha-strategy",
            Version("2.0.0"),
            _base_payload(),
        )
    ]


def test_release_checks_are_atomic_with_environment_updates() -> None:
    def failing_check(_: str, __: Version, ___: Mapping[str, object]) -> None:
        raise RuntimeError("simulated failure")

    registry = ConfigRegistry(release_checks=[failing_check])
    registry.register_profile(
        "alpha-strategy",
        "3.0.0",
        _base_payload(),
        actor="quant",
        required_approvals=0,
    )

    with pytest.raises(ConfigPublicationError):
        registry.publish_profile(
            "alpha-strategy",
            "3.0.0",
            actor="release",
            environments=[Environment.STAGE, Environment.PROD],
        )

    assert registry.get_active_version("alpha-strategy", Environment.STAGE) is None
    assert registry.get_active_version("alpha-strategy", Environment.PROD) is None


def test_rollback_restores_previous_version() -> None:
    registry = ConfigRegistry()
    registry.register_profile(
        "alpha-strategy",
        "1.0.0",
        _base_payload(risk_mode="baseline"),
        actor="quant",
        required_approvals=0,
    )
    registry.publish_profile(
        "alpha-strategy",
        "1.0.0",
        actor="deployer",
        environments=[Environment.STAGE],
    )

    registry.register_profile(
        "alpha-strategy",
        "1.1.0",
        _base_payload(risk_mode="aggressive"),
        actor="quant",
        required_approvals=0,
    )
    registry.publish_profile(
        "alpha-strategy",
        "1.1.0",
        actor="deployer",
        environments=[Environment.STAGE],
    )

    registry.rollback_profile(
        "alpha-strategy",
        environment=Environment.STAGE,
        target_version="1.0.0",
        actor="deployer",
        reason="Stage smoke tests failed",
    )

    assert registry.get_active_version("alpha-strategy", Environment.STAGE) == Version("1.0.0")


def test_rollback_requires_approvals_for_target_version() -> None:
    registry = ConfigRegistry()
    registry.register_profile(
        "alpha-strategy",
        "1.0.0",
        _base_payload(risk_mode="baseline"),
        actor="quant",
        required_approvals=0,
    )
    registry.publish_profile(
        "alpha-strategy",
        "1.0.0",
        actor="deployer",
        environments=[Environment.STAGE],
    )

    registry.register_profile(
        "alpha-strategy",
        "1.1.0",
        _base_payload(risk_mode="aggressive"),
        actor="quant",
        required_approvals=2,
    )

    with pytest.raises(ConfigApprovalError):
        registry.rollback_profile(
            "alpha-strategy",
            environment=Environment.STAGE,
            target_version="1.1.0",
            actor="deployer",
            reason="Rolling forward without approvals should fail",
        )

    assert registry.get_active_version("alpha-strategy", Environment.STAGE) == Version("1.0.0")


def test_audit_trail_includes_lifecycle_events() -> None:
    registry = ConfigRegistry()
    registry.register_profile(
        "alpha-strategy",
        "1.0.0",
        _base_payload(),
        actor="quant",
    )
    registry.approve_profile(
        "alpha-strategy",
        "1.0.0",
        approver="risk",
    )
    registry.publish_profile(
        "alpha-strategy",
        "1.0.0",
        actor="release",
        environments=[Environment.STAGE],
    )

    events = registry.audit_trail("alpha-strategy")
    assert [event.action for event in events] == ["register", "approve", "publish"]


def test_publish_atomically_updates_multiple_environments() -> None:
    registry = ConfigRegistry()
    registry.register_profile(
        "alpha-strategy",
        "4.0.0",
        _base_payload(),
        actor="quant",
        required_approvals=0,
    )

    registry.publish_profile(
        "alpha-strategy",
        "4.0.0",
        actor="release",
        environments=[Environment.STAGE, Environment.PROD],
    )

    assert registry.get_active_version("alpha-strategy", Environment.STAGE) == Version("4.0.0")
    assert registry.get_active_version("alpha-strategy", Environment.PROD) == Version("4.0.0")


def test_publish_comment_overrides_default_audit_message() -> None:
    """`message = comment or ", ".join(...)` -- a supplied comment wins.

    Under Or->And a truthy comment collapses to the joined environment names
    (`x and y` returns y), losing the operator's own audit note.
    """
    registry = ConfigRegistry()
    registry.register_profile("alpha-strategy", "1.0.0", _base_payload(), actor="quant")
    registry.approve_profile("alpha-strategy", "1.0.0", approver="risk")
    registry.publish_profile(
        "alpha-strategy",
        "1.0.0",
        actor="release",
        environments=[Environment.STAGE],
        comment="hand-written rollout note",
    )
    publish_msgs = [e.message for e in registry.audit_trail("alpha-strategy") if e.action == "publish"]
    assert publish_msgs == ["hand-written rollout note"]


def test_rollback_runs_release_checks_only_for_prod(monkeypatch) -> None:
    """`if env == Environment.PROD` gates release checks to PROD rollbacks only.

    Under Eq->NotEq the guard inverts: a STAGE rollback would trigger the
    (potentially blocking) production release gate while a PROD rollback skips it.
    """
    registry = ConfigRegistry()
    registry.register_profile("alpha-strategy", "1.0.0", _base_payload(), actor="quant")
    registry.register_profile("alpha-strategy", "1.1.0", _base_payload(), actor="quant")
    for version in ("1.0.0", "1.1.0"):
        registry.approve_profile("alpha-strategy", version, approver="risk")
    registry.publish_profile(
        "alpha-strategy", "1.1.0", actor="release",
        environments=[Environment.STAGE, Environment.PROD],
    )

    calls: list[str] = []
    monkeypatch.setattr(
        registry, "_run_release_checks", lambda name, record: calls.append(name)
    )

    registry.rollback_profile(
        "alpha-strategy", environment=Environment.STAGE, target_version="1.0.0", actor="release"
    )
    assert calls == []  # STAGE rollback must not invoke the production gate

    registry.rollback_profile(
        "alpha-strategy", environment=Environment.PROD, target_version="1.0.0", actor="release"
    )
    assert calls == ["alpha-strategy"]  # PROD rollback must invoke it exactly once
