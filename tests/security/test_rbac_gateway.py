from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from application.security.rbac import AuthorizationGateway, load_rbac_configuration
from src.admin.remote_control import AdminIdentity
from src.audit.audit_logger import AuditLogger


@pytest.fixture()
def rbac_policy_path(tmp_path: Path) -> Path:
    policy = tmp_path / "policy.yaml"
    policy.write_text(
        """
        roles:
          foundation:viewer:
            description: Read system state
            permissions:
              - resource: system.status
                action: read
          trading:operator:
            description: Submit orders
            inherits:
              - foundation:viewer
            permissions:
              - resource: orders
                action: submit
                attributes:
                  desk: ["execution"]
        temporary_grants:
          - subject: bob
            resource: orders
            action: submit
            attributes:
              desk: ["rescue"]
            expires_at: "2030-01-01T00:00:00Z"
            reason: Emergency trading window
        """,
        encoding="utf-8",
    )
    return policy


def _build_gateway(
    policy_path: Path,
    *,
    clock: Callable[[], datetime] | None = None,
) -> tuple[AuthorizationGateway, MagicMock]:
    configuration = load_rbac_configuration(policy_path)
    audit_logger = MagicMock(spec=AuditLogger)
    gateway = AuthorizationGateway(
        policy=configuration.policy,
        audit_logger=audit_logger,
        clock=clock or (lambda: datetime(2025, 1, 1, tzinfo=timezone.utc)),
    )
    gateway.register_temporary_grants(configuration.temporary_grants)
    return gateway, audit_logger


def test_load_rbac_configuration_parses_roles(rbac_policy_path: Path) -> None:
    configuration = load_rbac_configuration(rbac_policy_path)

    roles = configuration.policy.roles_granting("system.status", "read")

    assert roles == ("foundation:viewer", "trading:operator")
    assert configuration.temporary_grants[0].subject == "bob"


def test_authorized_identity_allows_and_audits(rbac_policy_path: Path) -> None:
    gateway, audit_logger = _build_gateway(rbac_policy_path)
    identity = AdminIdentity(subject="alice", roles=("trading:operator",))

    gateway.enforce(
        identity=identity,
        resource="orders",
        action="submit",
        attributes={"desk": "execution"},
    )

    audit_logger.log_event.assert_called_with(  # type: ignore[attr-defined]
        event_type="authorization.allow",
        actor="alice",
        ip_address="unknown",
        details={
            "resource": "orders",
            "action": "submit",
            "roles": ["trading:operator"],
            "temporary": False,
            "matched_source": "role:trading:operator",
        },
    )


def test_missing_role_is_denied(rbac_policy_path: Path) -> None:
    gateway, audit_logger = _build_gateway(rbac_policy_path)
    identity = AdminIdentity(subject="carol", roles=("foundation:viewer",))

    with pytest.raises(HTTPException) as exc_info:
        gateway.enforce(
            identity=identity,
            resource="orders",
            action="submit",
            attributes={"desk": "execution"},
        )

    detail = exc_info.value.detail
    assert detail["failure_reason"] == "missing_role"
    assert detail["required_roles"] == ["trading:operator"]

    assert audit_logger.log_event.call_args_list[-1][1]["event_type"] == "authorization.deny"  # type: ignore[index]


def test_attribute_mismatch_is_denied(rbac_policy_path: Path) -> None:
    gateway, _ = _build_gateway(rbac_policy_path)
    identity = AdminIdentity(subject="dave", roles=("trading:operator",))

    with pytest.raises(HTTPException) as exc_info:
        gateway.enforce(
            identity=identity,
            resource="orders",
            action="submit",
            attributes={"desk": "research"},
        )

    detail = exc_info.value.detail
    assert detail["failure_reason"] == "attribute_mismatch"
    assert detail["required_roles"] == ["trading:operator"]


def test_temporary_grant_respects_expiry(rbac_policy_path: Path) -> None:
    now = {"value": datetime(2025, 1, 1, tzinfo=timezone.utc)}

    def _clock() -> datetime:
        return now["value"]

    gateway, _ = _build_gateway(rbac_policy_path, clock=_clock)

    identity = AdminIdentity(subject="bob", roles=())

    gateway.enforce(
        identity=identity,
        resource="orders",
        action="submit",
        attributes={"desk": "rescue"},
    )

    now["value"] = now["value"] + timedelta(days=3650)

    with pytest.raises(HTTPException):
        gateway.enforce(
            identity=identity,
            resource="orders",
            action="submit",
            attributes={"desk": "rescue"},
        )
