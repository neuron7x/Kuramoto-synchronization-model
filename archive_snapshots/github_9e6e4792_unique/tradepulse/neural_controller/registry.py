from __future__ import annotations

from typing import Any

_COMPONENT_REGISTRY: dict[str, Any] = {}


def register_component(name: str, component: Any) -> None:
    """Register a neural controller component for discovery."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Component name must be a non-empty string.")
    _COMPONENT_REGISTRY[name] = component
