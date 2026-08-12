# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Simple registry of secret backend adapters for execution connectors."""

from __future__ import annotations

from typing import Callable, Mapping

VaultResolver = Callable[[str], Mapping[str, str]]


class SecretManagerError(RuntimeError):
    """Raised when a secret backend cannot be resolved."""


class SecretManager:
    """Registry mapping backend identifiers to resolver callables."""

    def __init__(self, backends: Mapping[str, VaultResolver] | None = None) -> None:
        self._backends: dict[str, VaultResolver] = {}
        if backends:
            for name, resolver in backends.items():
                self.register(name, resolver)

    def register(self, name: str, resolver: VaultResolver) -> None:
        """Register or replace the resolver associated with ``name``."""

        if not name:
            raise ValueError("backend name must be provided")
        if not callable(resolver):
            raise ValueError("resolver must be callable")
        self._backends[name.lower()] = resolver

    def get_resolver(self, name: str) -> VaultResolver:
        """Return the resolver callable registered for ``name``."""

        try:
            return self._backends[name.lower()]
        except KeyError as exc:  # pragma: no cover - defensive guard
            raise SecretManagerError(f"Unknown secret backend '{name}'") from exc

    def resolve(self, name: str, path: str) -> Mapping[str, str]:
        """Resolve ``path`` using the backend registered under ``name``."""

        resolver = self.get_resolver(name)
        return resolver(path)


__all__ = ["SecretManager", "SecretManagerError", "VaultResolver"]
