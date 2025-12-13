"""Role-based access control utilities."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from enum import Enum
from functools import wraps
from typing import Any, Callable, Iterable


class Permission(Enum):
    """Supported permissions for privileged actions."""

    TRADE_EXECUTE = "trade:execute"
    KILL_SWITCH = "system:kill"
    USER_MANAGE = "user:manage"
    CONFIG_WRITE = "config:write"


ROLES: dict[str, set[Permission]] = {
    "admin": {
        Permission.TRADE_EXECUTE,
        Permission.KILL_SWITCH,
        Permission.USER_MANAGE,
        Permission.CONFIG_WRITE,
    },
    "trader": {Permission.TRADE_EXECUTE},
    "viewer": set(),
}


@dataclass
class _User:
    role: str


_current_user: ContextVar[_User | None] = ContextVar("current_user", default=None)


def set_current_user(user: _User | None) -> None:
    """Set the current user context for RBAC checks."""

    _current_user.set(user)


def get_current_user() -> _User:
    """Return the current user or a default viewer."""

    user = _current_user.get()
    if user is None:
        return _User(role="viewer")
    return user


def require(permission: Permission) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to enforce RBAC permissions."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any):
            user = get_current_user()
            allowed_permissions = ROLES.get(user.role, set())
            if permission not in allowed_permissions:
                raise PermissionError(f"{permission.value} required")
            return func(*args, **kwargs)

        return wrapper

    return decorator
