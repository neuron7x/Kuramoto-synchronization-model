"""Authorization helpers for securing FastAPI endpoints."""

from __future__ import annotations

import inspect
import os
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable, Literal, Mapping, Sequence

from fastapi import Depends, HTTPException, Request, status

from application.security.rbac import AuthorizationGateway, build_authorization_gateway
from src.admin.remote_control import AdminIdentity
from src.audit.audit_logger import AuditLogger

from .security import verify_request_identity

__all__ = ["require_roles", "require_permission", "get_authorization_gateway"]


_POLICY_PATH_ENV = "TRADEPULSE_RBAC_POLICY_PATH"
_AUDIT_SECRET_ENV = "TRADEPULSE_RBAC_AUDIT_SECRET"  # pragma: allowlist secret
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_POLICY_PATH = _PROJECT_ROOT / "configs" / "rbac" / "policy.yaml"
_REPO_ROOT = _PROJECT_ROOT


def _normalise_roles(roles: Iterable[str]) -> tuple[str, ...]:
    normalised = []
    for role in roles:
        candidate = role.strip().lower()
        if not candidate:
            continue
        if candidate not in normalised:
            normalised.append(candidate)
    if not normalised:
        raise ValueError("At least one non-empty role must be provided")
    return tuple(normalised)


def require_roles(
    roles: Sequence[str] | str,
    *,
    identity_dependency: Callable[..., Awaitable[AdminIdentity]] | None = None,
    match: Literal["all", "any"] = "all",
) -> Callable[[AdminIdentity], AdminIdentity]:
    """Return a dependency enforcing role based access control."""

    if isinstance(roles, str):
        required = _normalise_roles([roles])
    else:
        required = _normalise_roles(roles)

    dependency = identity_dependency or verify_request_identity()

    async def _dependency(
        identity: AdminIdentity = Depends(dependency),
    ) -> AdminIdentity:
        granted = identity.role_set
        if match == "all":
            missing = [role for role in required if role not in granted]
            if missing:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "message": "Insufficient privileges for this operation.",
                        "missing_roles": missing,
                    },
                )
        elif match == "any":
            if not any(role in granted for role in required):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "message": "One of the required roles is missing.",
                        "required_roles": list(required),
                    },
                )
        else:  # pragma: no cover - defensive guard for enum evolution
            raise ValueError(f"Unsupported match strategy: {match}")
        return identity

    return _dependency


def _resolve_audit_secret() -> str:
    secret = os.getenv(_AUDIT_SECRET_ENV)
    if secret is None:
        raise RuntimeError(
            "TRADEPULSE_RBAC_AUDIT_SECRET must be set to enable audit logging"
        )
    candidate = secret.strip()
    if not candidate:
        raise RuntimeError("RBAC audit secret cannot be empty or whitespace")
    if len(candidate) < 16:
        raise ValueError("RBAC audit secret must be at least 16 characters long")
    return candidate


def _build_default_gateway() -> AuthorizationGateway:
    policy_path = Path(os.getenv(_POLICY_PATH_ENV, str(_DEFAULT_POLICY_PATH)))
    if not policy_path.is_absolute():
        policy_path = _REPO_ROOT / policy_path
    audit_logger = AuditLogger(secret=_resolve_audit_secret())
    return build_authorization_gateway(
        policy_path=policy_path, audit_logger=audit_logger
    )


def get_authorization_gateway() -> AuthorizationGateway:
    """Return a cached :class:`AuthorizationGateway` instance."""

    if not hasattr(get_authorization_gateway, "_instance"):
        get_authorization_gateway._instance = _build_default_gateway()  # type: ignore[attr-defined]
    return get_authorization_gateway._instance  # type: ignore[attr-defined]


def require_permission(
    resource: str,
    action: str,
    *,
    identity_dependency: Callable[..., Awaitable[AdminIdentity]] | None = None,
    attributes_provider: (
        Callable[
            [Request, AdminIdentity],
            Mapping[str, Any] | Awaitable[Mapping[str, Any] | None] | None,
        ]
        | None
    ) = None,
    gateway_dependency: Callable[[], AuthorizationGateway] | None = None,
) -> Callable[[Request, AdminIdentity, AuthorizationGateway], Awaitable[AdminIdentity]]:
    """Return a dependency enforcing granular RBAC permissions."""

    identity_dep = identity_dependency or verify_request_identity()

    def _gateway_dependency() -> AuthorizationGateway:
        if gateway_dependency is not None:
            return gateway_dependency()
        return get_authorization_gateway()

    async def _dependency(
        request: Request,
        identity: AdminIdentity = Depends(identity_dep),
        gateway: AuthorizationGateway = Depends(_gateway_dependency),
    ) -> AdminIdentity:
        provided_attributes: Mapping[str, Any] | None = None
        if attributes_provider is not None:
            candidate = attributes_provider(request, identity)
            if inspect.isawaitable(candidate):
                candidate = await candidate
            if candidate is None:
                provided_attributes = {}
            elif isinstance(candidate, Mapping):
                provided_attributes = candidate
            else:
                raise TypeError(
                    "attributes_provider must return a mapping, None, or awaitable resolving to one"
                )
        gateway.enforce(
            identity=identity,
            resource=resource,
            action=action,
            attributes=provided_attributes,
            request=request,
        )
        return identity

    return _dependency
