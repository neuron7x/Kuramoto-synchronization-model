from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from application.api.authorization import (
    _normalise_roles,
    _resolve_audit_secret,
    require_permission,
    require_roles,
)
from application.security.rbac import AuthorizationGateway
from src.admin.remote_control import AdminIdentity


class TestNormaliseRoles:
    def test_trims_and_deduplicates_roles(self) -> None:
        roles = ["  Admin  ", "admin", "Operator", " operator "]

        assert _normalise_roles(roles) == ("admin", "operator")

    def test_raises_value_error_when_no_valid_roles(self) -> None:
        with pytest.raises(
            ValueError, match="At least one non-empty role must be provided"
        ):
            _normalise_roles(["   ", "\t\n"])  # only whitespace entries


class TestResolveAuditSecret:
    def test_raises_when_secret_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TRADEPULSE_RBAC_AUDIT_SECRET", raising=False)

        with pytest.raises(
            RuntimeError, match="TRADEPULSE_RBAC_AUDIT_SECRET must be set"
        ):
            _resolve_audit_secret()

    def test_strips_and_validates_secret(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(
            "TRADEPULSE_RBAC_AUDIT_SECRET", "  integration-rbac-secret  "
        )

        assert _resolve_audit_secret() == "integration-rbac-secret"

    def test_rejects_short_secret(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TRADEPULSE_RBAC_AUDIT_SECRET", "short-secret")

        with pytest.raises(ValueError, match="must be at least 16 characters"):
            _resolve_audit_secret()


@pytest.mark.anyio
class TestRequireRolesAllMatch:
    async def test_passes_when_all_roles_granted(self) -> None:
        identity = AdminIdentity(subject="alice", roles=("admin", "operator"))
        dependency = require_roles(["Admin", "Operator"], match="all")

        result = await dependency(identity)

        assert result is identity

    async def test_raises_http_403_with_missing_roles(self) -> None:
        identity = AdminIdentity(subject="bob", roles=("admin",))
        dependency = require_roles(["Admin", "Operator"], match="all")

        with pytest.raises(HTTPException) as exc_info:
            await dependency(identity)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == {
            "message": "Insufficient privileges for this operation.",
            "missing_roles": ["operator"],
        }


@pytest.mark.anyio
class TestRequireRolesAnyMatch:
    async def test_passes_when_at_least_one_role_matches(self) -> None:
        identity = AdminIdentity(subject="carol", roles=("auditor", "operator"))
        dependency = require_roles(["Admin", "Operator"], match="any")

        result = await dependency(identity)

        assert result is identity

    async def test_raises_http_403_when_no_roles_match(self) -> None:
        identity = AdminIdentity(subject="dave", roles=("auditor",))
        dependency = require_roles(["Admin", "Operator"], match="any")

        with pytest.raises(HTTPException) as exc_info:
            await dependency(identity)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == {
            "message": "One of the required roles is missing.",
            "required_roles": ["admin", "operator"],
        }


@pytest.mark.anyio
async def test_require_roles_invalid_match_mode() -> None:
    identity = AdminIdentity(subject="eve", roles=("admin",))
    dependency = require_roles(["Admin"], match="none")

    with pytest.raises(ValueError, match="Unsupported match strategy: none"):
        await dependency(identity)


@pytest.mark.anyio
async def test_require_permission_delegates_to_gateway() -> None:
    identity = AdminIdentity(subject="frank", roles=("trading:operator",))

    async def _identity_dependency() -> AdminIdentity:
        return identity

    gateway = MagicMock(spec=AuthorizationGateway)

    def _gateway_dependency() -> AuthorizationGateway:
        return gateway

    def _attributes_provider(request: Request, _: AdminIdentity) -> dict[str, str]:
        return {"desk": "execution"}

    dependency = require_permission(
        "orders",
        "submit",
        identity_dependency=_identity_dependency,
        attributes_provider=_attributes_provider,
        gateway_dependency=_gateway_dependency,
    )

    request = Request({"type": "http", "headers": []})
    result = await dependency(request, identity, gateway)

    assert result is identity
    gateway.enforce.assert_called_once()
    _, kwargs = gateway.enforce.call_args
    assert kwargs["resource"] == "orders"
    assert kwargs["action"] == "submit"
    assert kwargs["attributes"] == {"desk": "execution"}


@pytest.mark.anyio
async def test_require_permission_propagates_http_errors() -> None:
    identity = AdminIdentity(subject="grace", roles=("foundation:viewer",))

    async def _identity_dependency() -> AdminIdentity:
        return identity

    gateway = MagicMock(spec=AuthorizationGateway)
    gateway.enforce.side_effect = HTTPException(
        status_code=403,
        detail={"message": "denied"},
    )

    def _gateway_dependency() -> AuthorizationGateway:
        return gateway

    dependency = require_permission(
        "orders",
        "submit",
        identity_dependency=_identity_dependency,
        gateway_dependency=_gateway_dependency,
    )

    request = Request({"type": "http", "headers": []})
    with pytest.raises(HTTPException):
        await dependency(request, identity, gateway)

    gateway.enforce.assert_called_once()
