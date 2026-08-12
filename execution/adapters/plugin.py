# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Plugin infrastructure for execution adapters.

Provides a lightweight registry capable of dynamically loading broker/exchange
connectors without modifying the execution core. Adapters describe their public
contract via :class:`AdapterContract`, expose optional self-diagnostics, and are
registered through :class:`AdapterRegistry` which supports explicit
registration, entry-point discovery, and runtime instantiation.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from importlib import metadata
from types import MappingProxyType
from typing import (
    Any,
    Callable,
    Iterable,
    Iterator,
    Mapping,
    MutableMapping,
    Optional,
    Tuple,
    TypeVar,
)

from execution.connectors import ExecutionConnector

__all__ = [
    "AdapterContract",
    "AdapterCheckResult",
    "AdapterDiagnostic",
    "AdapterFactory",
    "AdapterPlugin",
    "AdapterRegistry",
]

logger = logging.getLogger("execution.adapters.registry")

AdapterFactory = Callable[..., ExecutionConnector]
_T = TypeVar("_T", bound=ExecutionConnector)


@dataclass(frozen=True, slots=True)
class AdapterContract:
    """Describes the public contract for an adapter plugin."""

    identifier: str
    name: str
    provider: str
    version: str
    description: str
    transports: Mapping[str, str] = field(default_factory=dict)
    supports_sandbox: bool = True
    required_credentials: Tuple[str, ...] = ()
    optional_credentials: Tuple[str, ...] = ()
    capabilities: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.identifier:
            raise ValueError("AdapterContract.identifier must be non-empty")
        if "." not in self.identifier:
            raise ValueError("AdapterContract.identifier should be namespaced, e.g. 'binance.spot'")
        if not self.version:
            raise ValueError("AdapterContract.version must be provided")
        # Materialize tuples for credential collections for immutability
        object.__setattr__(self, "required_credentials", tuple(self.required_credentials))
        object.__setattr__(self, "optional_credentials", tuple(self.optional_credentials))
        object.__setattr__(self, "transports", MappingProxyType(dict(self.transports)))
        object.__setattr__(self, "capabilities", MappingProxyType(dict(self.capabilities)))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class AdapterCheckResult:
    """Represents the outcome of an individual adapter self-test check."""

    name: str
    status: str
    detail: Optional[str] = None

    def __post_init__(self) -> None:
        allowed = {"passed", "failed", "skipped"}
        if self.status not in allowed:
            raise ValueError(f"Unsupported check status '{self.status}'")
        if not self.name:
            raise ValueError("AdapterCheckResult.name must be non-empty")

    @property
    def passed(self) -> bool:
        return self.status == "passed"


@dataclass(frozen=True, slots=True)
class AdapterDiagnostic:
    """Aggregated diagnostics for a connector plugin."""

    adapter_id: str
    checks: Tuple[AdapterCheckResult, ...] = field(default_factory=tuple)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.adapter_id:
            raise ValueError("AdapterDiagnostic.adapter_id must be non-empty")
        object.__setattr__(self, "checks", tuple(self.checks))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)


@dataclass(slots=True)
class AdapterPlugin:
    """Container for a registered adapter implementation."""

    contract: AdapterContract
    factory: AdapterFactory
    implementation: type[_T] | None = None
    self_test: Callable[[], AdapterDiagnostic] | None = None
    module: str | None = None

    def create(self, **kwargs: Any) -> ExecutionConnector:
        return self.factory(**kwargs)

    def get_factory(self) -> AdapterFactory:
        return self.factory

    def get_implementation(self) -> type[_T] | None:
        impl = self.implementation
        if impl is None and isinstance(self.factory, type):
            if issubclass(self.factory, ExecutionConnector):
                impl = self.factory
        return impl

    def run_self_test(self) -> AdapterDiagnostic:
        if self.self_test is None:
            return AdapterDiagnostic(
                adapter_id=self.contract.identifier,
                checks=(
                    AdapterCheckResult(
                        name="self-test",
                        status="skipped",
                        detail="Adapter did not provide self-test",
                    ),
                ),
            )
        try:
            result = self.self_test()
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.exception(
                "Adapter self-test failed", extra={"adapter": self.contract.identifier}
            )
            return AdapterDiagnostic(
                adapter_id=self.contract.identifier,
                checks=(AdapterCheckResult(name="self-test", status="failed", detail=str(exc)),),
            )
        if result.adapter_id != self.contract.identifier:
            result = replace(result, adapter_id=self.contract.identifier)
        return result


class AdapterRegistry:
    """Registry coordinating discovery and loading of adapter plugins."""

    def __init__(self) -> None:
        self._plugins: MutableMapping[str, AdapterPlugin] = {}
        self._lock = threading.RLock()
        self._discovered_groups: set[str] = set()

    # -- mutation ---------------------------------------------------------
    def register(self, plugin: AdapterPlugin, *, override: bool = False) -> None:
        identifier = plugin.contract.identifier
        with self._lock:
            if identifier in self._plugins and not override:
                raise ValueError(f"Adapter '{identifier}' already registered")
            self._plugins[identifier] = plugin

    def unregister(self, identifier: str) -> None:
        with self._lock:
            self._plugins.pop(identifier, None)

    def clear(self) -> None:
        with self._lock:
            self._plugins.clear()
            self._discovered_groups.clear()

    # -- lookup -----------------------------------------------------------
    def get(self, identifier: str) -> AdapterPlugin:
        with self._lock:
            try:
                return self._plugins[identifier]
            except KeyError as exc:  # pragma: no cover - defensive guard
                raise LookupError(f"Unknown adapter '{identifier}'") from exc

    def __contains__(self, identifier: object) -> bool:
        with self._lock:
            return identifier in self._plugins

    def __iter__(self) -> Iterator[AdapterPlugin]:
        with self._lock:
            return iter(tuple(self._plugins.values()))

    # -- helper APIs ------------------------------------------------------
    def contracts(self) -> Mapping[str, AdapterContract]:
        with self._lock:
            return MappingProxyType({key: plugin.contract for key, plugin in self._plugins.items()})

    def identifiers(self) -> Iterable[str]:
        with self._lock:
            return tuple(self._plugins.keys())

    def get_factory(self, identifier: str) -> AdapterFactory:
        return self.get(identifier).get_factory()

    def get_implementation(self, identifier: str) -> type[_T] | None:
        return self.get(identifier).get_implementation()

    def create(self, identifier: str, **kwargs: Any) -> ExecutionConnector:
        plugin = self.get(identifier)
        return plugin.create(**kwargs)

    # -- self tests -------------------------------------------------------
    def self_test(self, identifier: str) -> AdapterDiagnostic:
        plugin = self.get(identifier)
        return plugin.run_self_test()

    def self_test_all(self) -> Mapping[str, AdapterDiagnostic]:
        with self._lock:
            return {
                identifier: plugin.run_self_test() for identifier, plugin in self._plugins.items()
            }

    # -- discovery --------------------------------------------------------
    def discover(self, group: str = "geosync.execution.adapters", *, reload: bool = False) -> None:
        """Discover adapters via ``importlib.metadata`` entry points."""

        if not reload and group in self._discovered_groups:
            return
        try:
            entry_points = metadata.entry_points()
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.debug("Adapter discovery failed", exc_info=exc)
            return

        # ``EntryPoints`` in Python 3.11 exposes ``select``. Fallback to manual filter.
        selected: Iterable[Any]
        if hasattr(entry_points, "select"):
            selected = entry_points.select(group=group)
        else:  # pragma: no cover - compatibility path
            selected = [ep for ep in entry_points if getattr(ep, "group", None) == group]

        for entry_point in selected:
            try:
                plugin = entry_point.load()
            except Exception as exc:  # pragma: no cover - defensive guard
                logger.warning("Failed to load adapter entry point %s", entry_point, exc_info=exc)
                continue
            if not isinstance(plugin, AdapterPlugin):
                logger.warning(
                    "Entry point %s did not return AdapterPlugin (got %s)",
                    entry_point,
                    type(plugin).__name__,
                )
                continue
            try:
                self.register(plugin)
            except ValueError:
                logger.debug(
                    "Adapter '%s' already registered; skipping entry point %s",
                    plugin.contract.identifier,
                    entry_point,
                )
        self._discovered_groups.add(group)

    # -- convenience ------------------------------------------------------
    def load(self, dotted_path: str, **kwargs: Any) -> ExecutionConnector:
        """Load adapter either by identifier or dotted path."""

        if dotted_path in self:
            return self.create(dotted_path, **kwargs)
        module_name, _, attr = dotted_path.rpartition(".")
        if not module_name:
            raise LookupError(
                f"Unable to resolve adapter '{dotted_path}'. Provide a registered identifier or module path."
            )
        module = __import__(module_name, fromlist=[attr])
        factory = getattr(module, attr)
        if not callable(factory):
            raise LookupError(f"Resolved attribute '{dotted_path}' is not callable")
        connector = factory(**kwargs)
        if not isinstance(connector, ExecutionConnector):  # pragma: no cover - defensive guard
            raise TypeError(
                f"Factory '{dotted_path}' did not return an ExecutionConnector instance"
            )
        return connector
