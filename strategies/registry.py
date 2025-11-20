"""Utilities for registering and resolving trading strategies.

The :mod:`strategies` package historically exposed a single ``get_strategy``
function backed by a module level dictionary.  As the strategy catalogue grew
it became hard to provide richer metadata, guard against accidental overrides,
and offer discovery features for tooling (CLIs, dashboards, tests).

This module introduces :class:`StrategyRegistry`, a lightweight registry that
encapsulates those responsibilities while keeping backward compatibility.  It
supports:

* explicit registration with optional descriptions
* safe overriding with a dedicated flag
* resolution helpers returning the instantiated strategy
* discovery of available strategies with metadata

The registry is intentionally simple and free from global state so that tests
can instantiate isolated registries when needed.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any, Callable, Dict, Mapping, MutableMapping, Tuple


class UnknownStrategyError(LookupError):
    """Raised when a requested strategy is not present in a registry."""


@dataclass(frozen=True, slots=True)
class StrategySpec:
    """Metadata describing a registered strategy."""

    name: str
    entrypoint: str
    description: str | None = None

    def load_factory(self) -> Callable[[Mapping[str, Any] | None], Any]:
        """Resolve the configured entrypoint into a callable factory."""

        try:
            module_name, factory_name = self.entrypoint.split(":", 1)
        except ValueError as exc:  # pragma: no cover - defensive guard
            raise ValueError(
                f"Invalid entrypoint '{self.entrypoint}'. Expected 'module:factory'."
            ) from exc

        module = import_module(module_name)
        factory = getattr(module, factory_name)
        if not callable(factory):  # pragma: no cover - defensive guard
            raise TypeError(f"Factory '{self.entrypoint}' is not callable.")
        return factory  # type: ignore[return-value]


class StrategyRegistry:
    """In-memory registry for mapping strategy names to factories."""

    def __init__(self) -> None:
        self._strategies: MutableMapping[str, StrategySpec] = {}

    def register(
        self,
        name: str,
        entrypoint: str,
        *,
        description: str | None = None,
        override: bool = False,
    ) -> None:
        """Register a strategy under ``name``.

        Parameters
        ----------
        name:
            Identifier used for lookup.
        entrypoint:
            Dotted path in the ``module:factory`` format.
        description:
            Optional human readable summary.
        override:
            Whether to override an existing registration.  ``False`` by
            default so duplicates raise a :class:`ValueError`.
        """

        if name in self._strategies and not override:
            raise ValueError(f"Strategy '{name}' already registered.")

        self._strategies[name] = StrategySpec(name=name, entrypoint=entrypoint, description=description)

    def unregister(self, name: str) -> None:
        """Remove a strategy from the registry if present."""

        self._strategies.pop(name, None)

    def get(self, name: str) -> StrategySpec:
        """Return the :class:`StrategySpec` for ``name`` or raise."""

        try:
            return self._strategies[name]
        except KeyError as exc:
            raise UnknownStrategyError(f"Unknown strategy '{name}'.") from exc

    def create(self, name: str, config: Mapping[str, Any] | None = None) -> Any:
        """Instantiate the strategy registered as ``name``.

        ``config`` is forwarded to the factory callable.  When ``None`` the
        factory is expected to handle defaults.
        """

        spec = self.get(name)
        factory = spec.load_factory()
        return factory(config)

    def contains(self, name: str) -> bool:
        return name in self._strategies

    def available(self) -> Tuple[StrategySpec, ...]:
        """Return registered strategies sorted by name."""

        return tuple(self._strategies[name] for name in sorted(self._strategies))

    def as_dict(self) -> Dict[str, StrategySpec]:
        """Return a shallow copy of the internal mapping."""

        return dict(self._strategies)


# Convenience helpers for the package level API ---------------------------------

_GLOBAL_REGISTRY = StrategyRegistry()


def global_registry() -> StrategyRegistry:
    """Expose the singleton registry used by :mod:`strategies`."""

    return _GLOBAL_REGISTRY


def register_strategy(
    name: str,
    entrypoint: str,
    *,
    description: str | None = None,
    override: bool = False,
) -> None:
    """Register a strategy in the global registry."""

    _GLOBAL_REGISTRY.register(name, entrypoint, description=description, override=override)


def available_strategies() -> Tuple[StrategySpec, ...]:
    """Expose all registered strategies."""

    return _GLOBAL_REGISTRY.available()


def resolve_strategy(name: str, config: Mapping[str, Any] | None = None) -> Any:
    """Instantiate a registered strategy using the global registry."""

    return _GLOBAL_REGISTRY.create(name, config=config)


__all__ = [
    "StrategyRegistry",
    "StrategySpec",
    "UnknownStrategyError",
    "available_strategies",
    "global_registry",
    "register_strategy",
    "resolve_strategy",
]
