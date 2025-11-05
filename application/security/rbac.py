"""Centralised role-based and attribute-based access control policies."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, MutableMapping, Sequence

import yaml
from fastapi import HTTPException, Request, status

from src.admin.remote_control import AdminIdentity
from src.audit.audit_logger import AuditLogger

__all__ = [
    "AttributeConstraint",
    "AuthorizationDecision",
    "AuthorizationGateway",
    "PermissionGrant",
    "RBACConfiguration",
    "RBACPolicy",
    "ResolvedPermission",
    "TemporaryAccessGrant",
    "build_authorization_gateway",
    "load_rbac_configuration",
]


_LOGGER = logging.getLogger("tradepulse.rbac")


def _normalise_token(value: str, *, label: str) -> str:
    candidate = value.strip().lower()
    if not candidate:
        raise ValueError(f"{label} must be a non-empty string")
    return candidate


def _normalise_role(value: str) -> str:
    return _normalise_token(value, label="role")


def _normalise_subject(value: str) -> str:
    return _normalise_token(value, label="subject")


def _ensure_utc(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


def _parse_iso8601(timestamp: str) -> datetime:
    value = timestamp.strip()
    if not value:
        raise ValueError("expires_at must be a non-empty ISO8601 string")
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:  # pragma: no cover - defensive guard
        raise ValueError(f"Invalid ISO8601 timestamp: {timestamp}") from exc
    return _ensure_utc(parsed)


def _resolve_request_ip(request: Request | None) -> str:
    if request is None:
        return "unknown"
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        for part in forwarded_for.split(","):
            candidate = part.strip()
            if candidate:
                return candidate
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip() or "unknown"
    if request.client is not None and request.client.host:
        return request.client.host
    return "unknown"


def _normalise_attribute_value(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        candidate = value.strip().lower()
        return {candidate} if candidate else set()
    if isinstance(value, Mapping):
        collected: set[str] = set()
        for inner in value.values():
            collected.update(_normalise_attribute_value(inner))
        return collected
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray)):
        collected: set[str] = set()
        for entry in value:
            collected.update(_normalise_attribute_value(entry))
        return collected
    candidate = str(value).strip().lower()
    return {candidate} if candidate else set()


def _normalise_attributes(attributes: Mapping[str, Any]) -> dict[str, set[str]]:
    normalised: dict[str, set[str]] = {}
    for key, value in attributes.items():
        if not isinstance(key, str):
            continue
        name = key.strip().lower()
        if not name:
            continue
        values = _normalise_attribute_value(value)
        if values:
            normalised[name] = values
    return normalised


@dataclass(frozen=True)
class AttributeConstraint:
    """Attribute constraint enforced during authorisation."""

    name: str
    allowed_values: frozenset[str] = field(default_factory=frozenset)
    allow_any: bool = False
    allow_subject: bool = False

    def is_satisfied(
        self,
        values: set[str] | None,
        *,
        identity: AdminIdentity,
    ) -> bool:
        if values is None or not values:
            return False
        if self.allow_any:
            return True
        if self.allow_subject and identity.subject.lower() in values:
            return True
        return bool(self.allowed_values.intersection(values))


@dataclass(frozen=True)
class PermissionGrant:
    """Concrete permission for a resource/action pair."""

    resource: str
    action: str
    attributes: tuple[AttributeConstraint, ...] = ()

    def matches(
        self,
        *,
        resource: str,
        action: str,
        attributes: Mapping[str, set[str]],
        identity: AdminIdentity,
    ) -> bool:
        if self.resource != resource or self.action != action:
            return False
        return all(
            constraint.is_satisfied(attributes.get(constraint.name), identity=identity)
            for constraint in self.attributes
        )


@dataclass(frozen=True)
class ResolvedPermission:
    """Permission resolved for a particular role or grant source."""

    permission: PermissionGrant
    source: str
    temporary: bool = False


@dataclass(frozen=True)
class RoleDefinition:
    name: str
    description: str
    permissions: tuple[PermissionGrant, ...]
    inherits: tuple[str, ...] = ()


@dataclass(frozen=True)
class TemporaryAccessGrant:
    """Time-bound access delegation for a specific subject."""

    subject: str
    permission: PermissionGrant
    expires_at: datetime
    reason: str
    requested_by: str | None = None

    @property
    def subject_key(self) -> str:
        return _normalise_subject(self.subject)

    def as_resolved_permission(self) -> ResolvedPermission:
        return ResolvedPermission(
            permission=self.permission,
            source=f"temporary:{self.reason}",
            temporary=True,
        )


@dataclass(frozen=True)
class AuthorizationDecision:
    """Result of an authorisation evaluation."""

    allowed: bool
    resource: str
    action: str
    attributes: Mapping[str, set[str]]
    raw_attributes: Mapping[str, Any]
    matched_source: str | None = None
    temporary: bool = False
    required_roles: tuple[str, ...] = ()
    failure_reason: str | None = None


class RBACPolicy:
    """In-memory representation of RBAC role definitions."""

    def __init__(self, roles: Mapping[str, RoleDefinition]) -> None:
        if not roles:
            raise ValueError("At least one RBAC role must be defined")
        self._roles: dict[str, RoleDefinition] = dict(roles)
        self._resolved_permissions: MutableMapping[str, tuple[ResolvedPermission, ...]] = {}
        self._permission_index: MutableMapping[tuple[str, str], set[str]] = {}
        self._build_indexes()

    def _build_indexes(self) -> None:
        for role_name in self._roles:
            resolved = self._resolve_role(role_name)
            self._resolved_permissions[role_name] = resolved
            for entry in resolved:
                key = (entry.permission.resource, entry.permission.action)
                self._permission_index.setdefault(key, set()).add(role_name)

    def _resolve_role(
        self,
        role_name: str,
        *,
        _stack: tuple[str, ...] = (),
    ) -> tuple[ResolvedPermission, ...]:
        if role_name not in self._roles:
            raise KeyError(f"Unknown role: {role_name}")
        if role_name in _stack:
            raise ValueError("Detected circular RBAC role inheritance")

        definition = self._roles[role_name]
        resolved: dict[PermissionGrant, ResolvedPermission] = {}

        for permission in definition.permissions:
            resolved.setdefault(
                permission,
                ResolvedPermission(permission=permission, source=f"role:{role_name}"),
            )

        for parent in definition.inherits:
            parent_permissions = self._resolve_role(parent, _stack=_stack + (role_name,))
            for entry in parent_permissions:
                resolved.setdefault(entry.permission, entry)

        return tuple(resolved.values())

    def permissions_for_role(self, role_name: str) -> tuple[ResolvedPermission, ...]:
        return self._resolved_permissions.get(role_name, ())

    def roles_granting(self, resource: str, action: str) -> tuple[str, ...]:
        key = (resource, action)
        roles = self._permission_index.get(key, set())
        return tuple(sorted(roles))


@dataclass(frozen=True)
class RBACConfiguration:
    policy: RBACPolicy
    temporary_grants: tuple[TemporaryAccessGrant, ...]


class AuthorizationGateway:
    """Centralised policy decision point for REST and UI components."""

    def __init__(
        self,
        *,
        policy: RBACPolicy,
        audit_logger: AuditLogger,
        clock: Callable[[], datetime] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._policy = policy
        self._audit_logger = audit_logger
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._logger = logger or _LOGGER
        self._temporary: dict[str, list[TemporaryAccessGrant]] = {}
        self._lock = threading.Lock()

    def register_temporary_grants(self, grants: Sequence[TemporaryAccessGrant]) -> None:
        for grant in grants:
            self.add_temporary_grant(grant)

    def add_temporary_grant(self, grant: TemporaryAccessGrant) -> None:
        with self._lock:
            bucket = self._temporary.setdefault(grant.subject_key, [])
            bucket.append(grant)
            bucket.sort(key=lambda item: item.expires_at)

    def evaluate(
        self,
        *,
        identity: AdminIdentity,
        resource: str,
        action: str,
        attributes: Mapping[str, Any] | None = None,
    ) -> AuthorizationDecision:
        raw_attributes = dict(attributes or {})
        normalised_resource = _normalise_token(resource, label="resource")
        normalised_action = _normalise_token(action, label="action")
        normalised_attributes = _normalise_attributes(raw_attributes)

        attribute_mismatch = False
        for role in sorted(identity.role_set):
            permissions = self._policy.permissions_for_role(role)
            for entry in permissions:
                if entry.permission.resource != normalised_resource:
                    continue
                if entry.permission.action != normalised_action:
                    continue
                if entry.permission.matches(
                    resource=normalised_resource,
                    action=normalised_action,
                    attributes=normalised_attributes,
                    identity=identity,
                ):
                    return AuthorizationDecision(
                        allowed=True,
                        resource=normalised_resource,
                        action=normalised_action,
                        attributes=normalised_attributes,
                        raw_attributes=raw_attributes,
                        matched_source=entry.source,
                        temporary=entry.temporary,
                        required_roles=(),
                    )
                attribute_mismatch = True

        now = self._clock()
        subject_key = identity.subject.lower()
        for grant in self._active_grants(subject_key, now):
            entry = grant.as_resolved_permission()
            if entry.permission.resource != normalised_resource:
                continue
            if entry.permission.action != normalised_action:
                continue
            if entry.permission.matches(
                resource=normalised_resource,
                action=normalised_action,
                attributes=normalised_attributes,
                identity=identity,
            ):
                return AuthorizationDecision(
                    allowed=True,
                    resource=normalised_resource,
                    action=normalised_action,
                    attributes=normalised_attributes,
                    raw_attributes=raw_attributes,
                    matched_source=entry.source,
                    temporary=True,
                    required_roles=(),
                )
            attribute_mismatch = True

        reason = "attribute_mismatch" if attribute_mismatch else "missing_role"
        required_roles = self._policy.roles_granting(
            normalised_resource, normalised_action
        )
        return AuthorizationDecision(
            allowed=False,
            resource=normalised_resource,
            action=normalised_action,
            attributes=normalised_attributes,
            raw_attributes=raw_attributes,
            matched_source=None,
            temporary=False,
            required_roles=required_roles,
            failure_reason=reason,
        )

    def enforce(
        self,
        *,
        identity: AdminIdentity,
        resource: str,
        action: str,
        attributes: Mapping[str, Any] | None = None,
        request: Request | None = None,
    ) -> AuthorizationDecision:
        decision = self.evaluate(
            identity=identity,
            resource=resource,
            action=action,
            attributes=attributes,
        )
        if decision.allowed:
            self._log_allow(identity, decision, request)
            return decision
        self._log_deny(identity, decision, request)
        detail = {
            "message": "Insufficient privileges for this operation.",
            "resource": decision.resource,
            "action": decision.action,
        }
        if decision.required_roles:
            detail["required_roles"] = list(decision.required_roles)
        if decision.failure_reason:
            detail["failure_reason"] = decision.failure_reason
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)

    def _active_grants(
        self,
        subject_key: str,
        now: datetime,
    ) -> list[TemporaryAccessGrant]:
        with self._lock:
            grants = self._temporary.get(subject_key)
            if not grants:
                return []
            active: list[TemporaryAccessGrant] = []
            remaining: list[TemporaryAccessGrant] = []
            for grant in grants:
                if grant.expires_at >= now:
                    active.append(grant)
                    remaining.append(grant)
                else:
                    self._logger.info(
                        "Expired temporary access grant", extra={"grant_reason": grant.reason}
                    )
            if remaining:
                self._temporary[subject_key] = remaining
            else:
                self._temporary.pop(subject_key, None)
            return active

    def _log_allow(
        self,
        identity: AdminIdentity,
        decision: AuthorizationDecision,
        request: Request | None,
    ) -> None:
        ip_address = _resolve_request_ip(request)
        self._logger.info(
            "authorization.allowed",
            extra={
                "subject": identity.subject,
                "resource": decision.resource,
                "action": decision.action,
                "roles": sorted(identity.role_set),
                "temporary": decision.temporary,
            },
        )
        self._audit_logger.log_event(
            event_type="authorization.allow",
            actor=identity.subject,
            ip_address=ip_address,
            details={
                "resource": decision.resource,
                "action": decision.action,
                "roles": sorted(identity.role_set),
                "temporary": decision.temporary,
                "matched_source": decision.matched_source,
            },
        )

    def _log_deny(
        self,
        identity: AdminIdentity,
        decision: AuthorizationDecision,
        request: Request | None,
    ) -> None:
        ip_address = _resolve_request_ip(request)
        self._logger.warning(
            "authorization.denied",
            extra={
                "subject": identity.subject,
                "resource": decision.resource,
                "action": decision.action,
                "roles": sorted(identity.role_set),
                "failure_reason": decision.failure_reason,
            },
        )
        self._audit_logger.log_event(
            event_type="authorization.deny",
            actor=identity.subject,
            ip_address=ip_address,
            details={
                "resource": decision.resource,
                "action": decision.action,
                "roles": sorted(identity.role_set),
                "failure_reason": decision.failure_reason,
                "required_roles": list(decision.required_roles),
                "attributes": {
                    key: sorted(value) for key, value in decision.attributes.items()
                },
            },
        )


def _parse_attribute_constraints(
    payload: Mapping[str, Any] | None,
) -> tuple[AttributeConstraint, ...]:
    if not payload:
        return ()
    constraints: list[AttributeConstraint] = []
    for raw_name, raw_value in payload.items():
        if not isinstance(raw_name, str):
            raise ValueError("Attribute names must be strings")
        name = raw_name.strip().lower()
        if not name:
            raise ValueError("Attribute names must be non-empty strings")
        allow_any = False
        allow_subject = False
        allowed: set[str] = set()
        values: Iterable[Any]
        if isinstance(raw_value, str):
            values = [raw_value]
        elif isinstance(raw_value, Iterable) and not isinstance(
            raw_value, (bytes, bytearray)
        ):
            values = raw_value
        else:
            values = [raw_value]
        for entry in values:
            if isinstance(entry, str) and entry.strip() == "*":
                allow_any = True
                continue
            if isinstance(entry, str) and entry.strip().lower() == "$self":
                allow_subject = True
                continue
            candidate = str(entry).strip().lower()
            if candidate:
                allowed.add(candidate)
        constraints.append(
            AttributeConstraint(
                name=name,
                allowed_values=frozenset(allowed),
                allow_any=allow_any,
                allow_subject=allow_subject,
            )
        )
    return tuple(constraints)


def _parse_permission(payload: Mapping[str, Any]) -> PermissionGrant:
    try:
        resource = _normalise_token(str(payload["resource"]), label="resource")
        action = _normalise_token(str(payload["action"]), label="action")
    except KeyError as exc:
        raise ValueError("Permission entries must define resource and action") from exc
    attributes_payload = payload.get("attributes")
    if attributes_payload is not None and not isinstance(attributes_payload, Mapping):
        raise ValueError("Permission attributes must be a mapping")
    constraints = _parse_attribute_constraints(attributes_payload)
    return PermissionGrant(resource=resource, action=action, attributes=constraints)


def _parse_role(name: str, payload: Mapping[str, Any]) -> RoleDefinition:
    description = str(payload.get("description", "")).strip()
    if not description:
        raise ValueError(f"Role {name} is missing a description")
    permissions_payload = payload.get("permissions")
    if not isinstance(permissions_payload, Sequence) or not permissions_payload:
        raise ValueError(f"Role {name} must define at least one permission")
    permissions = tuple(
        _parse_permission(entry)
        for entry in permissions_payload
        if isinstance(entry, Mapping)
    )
    inherits_payload = payload.get("inherits", ())
    if isinstance(inherits_payload, str):
        inherits_payload = [inherits_payload]
    inherits = tuple(_normalise_role(str(role)) for role in inherits_payload)
    return RoleDefinition(
        name=_normalise_role(name),
        description=description,
        permissions=permissions,
        inherits=inherits,
    )


def _parse_temporary_grant(payload: Mapping[str, Any]) -> TemporaryAccessGrant:
    try:
        subject = str(payload["subject"])
        resource = str(payload["resource"])
        action = str(payload["action"])
        expires_at = str(payload["expires_at"])
    except KeyError as exc:
        raise ValueError("Temporary grants require subject, resource, action, expires_at") from exc

    permission = _parse_permission({
        "resource": resource,
        "action": action,
        "attributes": payload.get("attributes"),
    })
    return TemporaryAccessGrant(
        subject=subject,
        permission=permission,
        expires_at=_parse_iso8601(expires_at),
        reason=str(payload.get("reason", "temporary grant")),
        requested_by=payload.get("requested_by"),
    )


def load_rbac_configuration(path: Path) -> RBACConfiguration:
    if not path.exists():
        raise FileNotFoundError(f"RBAC policy file not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    roles_payload = data.get("roles")
    if not isinstance(roles_payload, Mapping):
        raise ValueError("RBAC configuration must define roles")
    roles: dict[str, RoleDefinition] = {}
    for name, payload in roles_payload.items():
        if not isinstance(payload, Mapping):
            raise ValueError("Role definitions must be mappings")
        role = _parse_role(str(name), payload)
        roles[role.name] = role
    policy = RBACPolicy(roles)

    grants_payload = data.get("temporary_grants", ())
    grants: list[TemporaryAccessGrant] = []
    if isinstance(grants_payload, Sequence):
        for entry in grants_payload:
            if not isinstance(entry, Mapping):
                raise ValueError("Temporary grant entries must be mappings")
            grants.append(_parse_temporary_grant(entry))
    elif grants_payload:
        raise ValueError("temporary_grants must be a sequence")

    return RBACConfiguration(policy=policy, temporary_grants=tuple(grants))


def build_authorization_gateway(
    *,
    policy_path: Path,
    audit_logger: AuditLogger,
    clock: Callable[[], datetime] | None = None,
    logger: logging.Logger | None = None,
) -> AuthorizationGateway:
    configuration = load_rbac_configuration(policy_path)
    gateway = AuthorizationGateway(
        policy=configuration.policy,
        audit_logger=audit_logger,
        clock=clock,
        logger=logger,
    )
    gateway.register_temporary_grants(configuration.temporary_grants)
    return gateway

