"""Requirement decorators used for dynamic traceability generation."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

F = TypeVar("F", bound=Callable[..., object])


def requirement(requirement_id: str) -> Callable[[F], F]:
    """Attach a requirement identifier to a test function."""

    def decorator(func: F) -> F:
        setattr(func, "requirement_id", requirement_id)
        return func

    return decorator
