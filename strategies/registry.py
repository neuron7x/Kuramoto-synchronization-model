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
from enum import Enum
from importlib import import_module
import logging
from typing import Any, Callable, Dict, Mapping, MutableMapping, Tuple


logger = logging.getLogger(__name__)


class MarketRegime(Enum):
    KILL = "KILL"
    CAUTION = "CAUTION"
    EMERGENT = "EMERGENT"


class SystemStress(Enum):
    LOW = "LOW"
    ELEVATED = "ELEVATED"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskLevel(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


def _coerce_enum(value: Any, enum_cls: type[Enum], field_name: str) -> Enum:
    if isinstance(value, enum_cls):
        return value
    if isinstance(value, str):
        normalized = value.strip().upper()
        for candidate in enum_cls:
            if candidate.name == normalized or candidate.value == normalized:
                return candidate
    raise ValueError(f"{field_name} must be one of {list(enum_cls)}; got {value!r}")


@dataclass(frozen=True, slots=True)
class StrategyStateInput:
    market_regime: MarketRegime
    system_stress: SystemStress
    risk_level: RiskLevel

    @classmethod
    def from_raw(
        cls,
        market_regime: MarketRegime | str,
        system_stress: SystemStress | str,
        risk_level: RiskLevel | str,
    ) -> "StrategyStateInput":
        return cls(
            market_regime=_coerce_enum(market_regime, MarketRegime, "market_regime"),
            system_stress=_coerce_enum(system_stress, SystemStress, "system_stress"),
            risk_level=_coerce_enum(risk_level, RiskLevel, "risk_level"),
        )

    def validate(self) -> None:
        _coerce_enum(self.market_regime, MarketRegime, "market_regime")
        _coerce_enum(self.system_stress, SystemStress, "system_stress")
        _coerce_enum(self.risk_level, RiskLevel, "risk_level")


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

        self._strategies[name] = StrategySpec(
            name=name, entrypoint=entrypoint, description=description
        )

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


@dataclass(frozen=True, slots=True)
class StrategyRoutingPolicy:
    policy_map: Mapping[Tuple[MarketRegime, SystemStress, RiskLevel], str]
    default_strategy: str

    def validate(self, registry: StrategyRegistry) -> None:
        missing = [
            name
            for name in self.policy_map.values()
            if not registry.contains(name)
        ]
        if not registry.contains(self.default_strategy):
            missing.append(self.default_strategy)
        if missing:
            raise ValueError(
                "Routing policy references unregistered strategies: "
                + ", ".join(sorted(set(missing)))
            )

    def select(self, state_input: StrategyStateInput) -> str:
        key = (
            state_input.market_regime,
            state_input.system_stress,
            state_input.risk_level,
        )
        return self.policy_map.get(key, self.default_strategy)


class StrategyRouter:
    def __init__(
        self,
        registry: StrategyRegistry,
        policy: StrategyRoutingPolicy,
        *,
        log: logging.Logger | None = None,
    ) -> None:
        self._registry = registry
        self._policy = policy
        self._logger = log or logger
        self._last_strategy: str | None = None
        self._policy.validate(registry)

    def select_name(self, state_input: StrategyStateInput) -> str:
        state_input.validate()
        selected = self._policy.select(state_input)
        if not self._registry.contains(selected):
            raise UnknownStrategyError(f"Unknown strategy '{selected}'.")
        if selected == self._policy.default_strategy and (
            (
                state_input.market_regime,
                state_input.system_stress,
                state_input.risk_level,
            )
            not in self._policy.policy_map
        ):
            self._logger.warning(
                "Strategy routing defaulted to %s for regime=%s stress=%s risk=%s",
                selected,
                state_input.market_regime.value,
                state_input.system_stress.value,
                state_input.risk_level.value,
            )
        return selected

    def route(
        self, state_input: StrategyStateInput, config: Mapping[str, Any] | None = None
    ) -> Any:
        selected = self.select_name(state_input)
        if selected != self._last_strategy:
            self._logger.info(
                "Switching strategy from %s to %s (regime=%s stress=%s risk=%s)",
                self._last_strategy,
                selected,
                state_input.market_regime.value,
                state_input.system_stress.value,
                state_input.risk_level.value,
            )
            self._last_strategy = selected
        return self._registry.create(selected, config=config)


def default_routing_policy() -> StrategyRoutingPolicy:
    return StrategyRoutingPolicy(
        policy_map={
            (MarketRegime.KILL, SystemStress.CRITICAL, RiskLevel.HIGH): "neuro_trade",
            (MarketRegime.KILL, SystemStress.HIGH, RiskLevel.HIGH): "neuro_trade",
            (MarketRegime.CAUTION, SystemStress.HIGH, RiskLevel.MEDIUM): "neuro_trade",
            (MarketRegime.CAUTION, SystemStress.ELEVATED, RiskLevel.HIGH): "neuro_trade",
            (MarketRegime.EMERGENT, SystemStress.LOW, RiskLevel.LOW): "quantum_neural",
            (MarketRegime.EMERGENT, SystemStress.LOW, RiskLevel.MEDIUM): "quantum_neural",
            (MarketRegime.CAUTION, SystemStress.ELEVATED, RiskLevel.MEDIUM): "quantum_neural",
        },
        default_strategy="quantum_neural",
    )


# Convenience helpers for the package level API ---------------------------------

_GLOBAL_REGISTRY = StrategyRegistry()


def global_registry() -> StrategyRegistry:
    """Expose the singleton registry used by :mod:`strategies`."""

    return _GLOBAL_REGISTRY


_GLOBAL_ROUTER: StrategyRouter | None = None


def global_router() -> StrategyRouter:
    """Expose the singleton router used for state-based strategy selection."""

    global _GLOBAL_ROUTER
    if _GLOBAL_ROUTER is None:
        _GLOBAL_ROUTER = StrategyRouter(_GLOBAL_REGISTRY, default_routing_policy())
    return _GLOBAL_ROUTER


def register_strategy(
    name: str,
    entrypoint: str,
    *,
    description: str | None = None,
    override: bool = False,
) -> None:
    """Register a strategy in the global registry."""

    _GLOBAL_REGISTRY.register(
        name, entrypoint, description=description, override=override
    )


def available_strategies() -> Tuple[StrategySpec, ...]:
    """Expose all registered strategies."""

    return _GLOBAL_REGISTRY.available()


def resolve_strategy(name: str, config: Mapping[str, Any] | None = None) -> Any:
    """Instantiate a registered strategy using the global registry."""

    return _GLOBAL_REGISTRY.create(name, config=config)


def route_strategy(
    market_regime: MarketRegime | str,
    system_stress: SystemStress | str,
    risk_level: RiskLevel | str,
    config: Mapping[str, Any] | None = None,
    *,
    policy: StrategyRoutingPolicy | None = None,
    registry: StrategyRegistry | None = None,
    log: logging.Logger | None = None,
) -> Any:
    """Route to a strategy using state inputs and instantiate it."""

    state_input = StrategyStateInput.from_raw(
        market_regime=market_regime,
        system_stress=system_stress,
        risk_level=risk_level,
    )
    if policy or registry or log:
        router = StrategyRouter(
            registry or _GLOBAL_REGISTRY,
            policy or default_routing_policy(),
            log=log,
        )
    else:
        router = global_router()
    return router.route(state_input, config=config)


__all__ = [
    "MarketRegime",
    "RiskLevel",
    "StrategyRegistry",
    "StrategyRouter",
    "StrategyRoutingPolicy",
    "StrategySpec",
    "StrategyStateInput",
    "SystemStress",
    "UnknownStrategyError",
    "available_strategies",
    "default_routing_policy",
    "global_registry",
    "global_router",
    "register_strategy",
    "resolve_strategy",
    "route_strategy",
]
