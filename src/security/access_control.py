"""Access control primitives for sensitive TradePulse operations."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Mapping

import yaml

__all__ = [
    "AccessDeniedError",
    "AccessController",
    "AccessPolicy",
    "Permission",
]


class AccessDeniedError(PermissionError):
    """Raised when an actor attempts an unauthorised operation."""


@dataclass(frozen=True)
class Permission:
    """Declarative authorisation rule for an action/resource pair."""

    action: str
    resources: frozenset[str]

    def allows(self, action: str, resource: str | None) -> bool:
        if self.action != action:
            return False
        if not self.resources or "*" in self.resources:
            return True
        if resource is None:
            return False
        return resource in self.resources


@dataclass(frozen=True)
class _PolicyNode:
    permissions: tuple[Permission, ...]
    inherits: tuple[str, ...]


class AccessPolicy:
    """Immutable representation of the access policy table."""

    def __init__(self, nodes: Mapping[str, _PolicyNode]) -> None:
        self._nodes: dict[str, _PolicyNode] = {
            key.lower(): value for key, value in nodes.items()
        }

    @classmethod
    def load(cls, path: Path) -> "AccessPolicy":
        """Load an :class:`AccessPolicy` from a YAML or TOML file."""

        if not path.exists():
            raise FileNotFoundError(f"Access policy file not found: {path}")

        raw_text = path.read_text(encoding="utf-8")
        try:
            data = yaml.safe_load(raw_text)
        except yaml.YAMLError as exc:  # pragma: no cover - PyYAML provides context
            raise ValueError(f"Failed to parse access policy: {exc}") from exc

        if not isinstance(data, Mapping):
            raise ValueError("Access policy document must be a mapping")

        nodes: dict[str, _PolicyNode] = {}
        for section in ("subjects", "roles"):
            payload = data.get(section) or {}
            if not isinstance(payload, Mapping):
                raise ValueError(f"{section} must be a mapping of entries")
            for name, definition in payload.items():
                if not isinstance(name, str) or not name.strip():
                    raise ValueError("Policy entries must use non-empty string keys")
                if not isinstance(definition, Mapping):
                    raise ValueError(
                        f"Policy entry '{name}' must be defined using a mapping"
                    )
                permissions = tuple(
                    _parse_permission(item, name)
                    for item in definition.get("permissions", [])
                )
                inherits = tuple(
                    str(entry).strip().lower()
                    for entry in definition.get("inherits", [])
                    if str(entry).strip()
                )
                nodes[name.lower()] = _PolicyNode(
                    permissions=permissions, inherits=inherits
                )

        return cls(nodes)

    def permissions_for(self, identifier: str) -> frozenset[Permission]:
        """Return the resolved permission set for ``identifier``."""

        key = identifier.lower().strip()
        if not key:
            return frozenset()
        return self._collect_permissions(key)

    @lru_cache(maxsize=256)
    def _collect_permissions(self, key: str) -> frozenset[Permission]:
        visited: set[str] = set()
        aggregated: set[Permission] = set()

        def _walk(candidate: str) -> None:
            candidate_key = candidate.lower()
            if candidate_key in visited:
                return
            visited.add(candidate_key)
            node = self._nodes.get(candidate_key)
            if node is None:
                return
            aggregated.update(node.permissions)
            for parent in node.inherits:
                _walk(parent)

        _walk(key)
        return frozenset(aggregated)


class AccessController:
    """Evaluate whether actors are allowed to perform privileged actions."""

    def __init__(
        self, policy: AccessPolicy, *, fallback_subject: str = "system"
    ) -> None:
        self._policy = policy
        self._fallback = fallback_subject.strip().lower()

    def is_allowed(
        self,
        action: str,
        *,
        actor: str | None = None,
        roles: Iterable[str] = (),
        resource: str | None = None,
    ) -> bool:
        if not action or not action.strip():
            raise ValueError("action must be a non-empty string")
        normalised_action = action.strip().lower()
        identifiers: list[str] = []
        if actor and actor.strip():
            identifiers.append(actor.strip().lower())
        elif self._fallback:
            identifiers.append(self._fallback)
        for role in roles:
            if isinstance(role, str) and role.strip():
                identifiers.append(role.strip().lower())
        resource_key = resource.strip().lower() if isinstance(resource, str) else None

        for identifier in identifiers:
            permissions = self._policy.permissions_for(identifier)
            for permission in permissions:
                if permission.allows(normalised_action, resource_key):
                    return True
        return False

    def require(
        self,
        action: str,
        *,
        actor: str | None = None,
        roles: Iterable[str] = (),
        resource: str | None = None,
    ) -> None:
        if self.is_allowed(action, actor=actor, roles=roles, resource=resource):
            return
        subject = actor or self._fallback or "unknown"
        raise AccessDeniedError(
            f"Actor '{subject}' is not permitted to perform '{action}'"
        )


def _parse_permission(value: object, context: str) -> Permission:
    if isinstance(value, str):
        action = value.strip().lower()
        if not action:
            raise ValueError(
                f"Permission entries for '{context}' must not be empty strings"
            )
        return Permission(action=action, resources=frozenset({"*"}))

    if isinstance(value, Mapping):
        raw_action = str(value.get("action", "")).strip().lower()
        if not raw_action:
            raise ValueError(
                f"Permission mappings for '{context}' must define a non-empty 'action'"
            )
        resources_value = value.get("resources", ["*"])
        if resources_value is None:
            resources: frozenset[str] = frozenset()
        else:
            if isinstance(resources_value, str):
                items = [resources_value]
            else:
                items = list(resources_value)
            cleaned = {str(item).strip().lower() for item in items if str(item).strip()}
            resources = frozenset(cleaned or {"*"})
        return Permission(action=raw_action, resources=resources)

    raise ValueError(
        f"Permissions for '{context}' must be strings or mappings, got {type(value)!r}"
    )
