# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Market regime modulation algorithms.

Sprint 4 split: the previous monolithic ``RegimeModulator`` combined
three responsibilities — blending, classification, and process-level
execution — into one class that had to be reconstructed on any tuning
change. Those responsibilities are now three orthogonal objects:

* ``ModulationPolicy`` — pure, stateless, computes ``(valence,
  confidence)`` from an incoming tick. Hot-swappable at runtime.
* ``_classify`` — the thresholds that turn numerical valence into a
  label. Kept as a free function because it is orthogonal to policy
  choice.
* ``RegimeModulator`` — the executor that holds the current policy
  pointer and applies it. ``swap_policy`` replaces the pointer
  atomically without recreating the modulator, so the long-running
  cortex service can change blending behaviour in flight.

``ExponentialDecayPolicy`` preserves the pre-Sprint-4 behaviour
byte-for-byte — it is constructed by default so every existing caller
continues to work without changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from threading import Lock
from typing import Callable, Protocol, runtime_checkable

from ..config import RegimeSettings
from ..constants import (
    REGIME_CONFIDENCE_THRESHOLD_INDETERMINATE,
    REGIME_VALENCE_THRESHOLD_BEARISH,
    REGIME_VALENCE_THRESHOLD_BULLISH,
)


@dataclass(slots=True, frozen=True)
class RegimeState:
    """The inferred state of the market regime.

    Attributes:
        label: Regime classification (bullish, bearish, neutral, indeterminate).
        valence: Numerical valence score after blending.
        confidence: Confidence in the regime classification.
        as_of: Timestamp of this regime state.
    """

    label: str
    valence: float
    confidence: float
    as_of: datetime


@runtime_checkable
class ModulationPolicy(Protocol):
    """Pluggable blending policy.

    A policy is a *pure* function of ``(previous, feedback, volatility)``.
    It is stateless between calls — the modulator owns any history that
    crosses a swap boundary so the policy can be swapped at any time.
    """

    def compute(
        self,
        previous: RegimeState | None,
        feedback: float,
        volatility: float,
    ) -> tuple[float, float]:
        """Return ``(bounded_valence, confidence)`` for the current tick."""
        ...


class ExponentialDecayPolicy:
    """Legacy ``RegimeModulator`` blending, extracted verbatim.

    ``valence_t = (1 − decay) · valence_{t-1} + decay · feedback``;
    ``confidence_t = max(confidence_floor, 1 − volatility)``.
    Bit-identical to the pre-Sprint-4 behaviour; the default policy so
    existing deployments keep running.
    """

    __slots__ = ("_settings",)

    def __init__(self, settings: RegimeSettings) -> None:
        self._settings = settings

    def compute(
        self,
        previous: RegimeState | None,
        feedback: float,
        volatility: float,
    ) -> tuple[float, float]:
        decay = self._settings.decay
        if previous is None:
            seed_valence = feedback
        else:
            seed_valence = (1 - decay) * previous.valence + decay * feedback
        bounded_valence = max(
            self._settings.min_valence,
            min(self._settings.max_valence, seed_valence),
        )
        confidence = max(self._settings.confidence_floor, 1.0 - volatility)
        return bounded_valence, confidence


def _classify(valence: float, confidence: float) -> str:
    """Turn a bounded valence/confidence pair into a regime label."""
    if confidence < REGIME_CONFIDENCE_THRESHOLD_INDETERMINATE:
        return "indeterminate"
    if valence >= REGIME_VALENCE_THRESHOLD_BULLISH:
        return "bullish"
    if valence <= REGIME_VALENCE_THRESHOLD_BEARISH:
        return "bearish"
    return "neutral"


class RegimeModulator:
    """Executor for the active :class:`ModulationPolicy`.

    The modulator owns the *current policy pointer*; computation is
    delegated to the policy. ``swap_policy`` replaces the pointer under
    a lock so a hot-swap is atomic with respect to concurrent ``update``
    calls. No tick is ever dropped by the swap — either it ran on the
    old policy or it runs on the new one.
    """

    __slots__ = ("_settings", "_policy", "_lock")

    def __init__(
        self,
        settings: RegimeSettings,
        policy: ModulationPolicy | None = None,
    ) -> None:
        self._settings = settings
        self._policy: ModulationPolicy = (
            policy if policy is not None else ExponentialDecayPolicy(settings)
        )
        self._lock = Lock()

    @property
    def policy(self) -> ModulationPolicy:
        """Current policy — snapshot read, safe without the lock."""
        return self._policy

    def swap_policy(self, new_policy: ModulationPolicy) -> ModulationPolicy:
        """Atomically install ``new_policy`` and return the previous one.

        Concurrent ``update`` calls see either the old or the new
        policy, never a mix — the modulator takes the lock just long
        enough to flip the pointer.
        """
        if not isinstance(new_policy, ModulationPolicy):
            raise TypeError(f"new_policy must implement ModulationPolicy; got {type(new_policy)!r}")
        with self._lock:
            previous = self._policy
            self._policy = new_policy
        return previous

    def update(
        self,
        previous: RegimeState | None,
        feedback: float,
        volatility: float,
        as_of: datetime,
    ) -> RegimeState:
        """Apply the current policy to one tick.

        Reads the policy pointer once so a concurrent swap cannot
        interleave half the computation. Result is produced from a
        consistent policy view.
        """
        policy = self._policy  # single read — swap safety
        bounded_valence, confidence = policy.compute(previous, feedback, volatility)
        return RegimeState(
            label=_classify(bounded_valence, confidence),
            valence=bounded_valence,
            confidence=confidence,
            as_of=as_of,
        )


class PolicyRegistry:
    """Process-wide lookup so an event-driven update path can resolve a
    policy by name without coupling to concrete classes.

    A runtime reconfiguration flow looks like:

        1. controller emits ``PolicyChanged(policy_name="trendless_linear")``
        2. service handler fetches the policy via ``registry.resolve(name)``
        3. handler calls ``modulator.swap_policy(resolved)``

    The registry is plain Python and intentionally synchronous —
    concurrency on reload is handled by ``RegimeModulator.swap_policy``
    itself (Sprint-4 lock).
    """

    def __init__(self) -> None:
        self._factories: dict[str, "Callable[[], ModulationPolicy]"] = {}

    def register(self, name: str, factory: "Callable[[], ModulationPolicy]") -> None:
        if not name:
            raise ValueError("policy name must be non-empty")
        if name in self._factories:
            raise ValueError(f"policy {name!r} already registered")
        self._factories[name] = factory

    def resolve(self, name: str) -> ModulationPolicy:
        try:
            factory = self._factories[name]
        except KeyError as exc:
            raise KeyError(
                f"unknown policy {name!r}; registered: " + ", ".join(sorted(self._factories))
            ) from exc
        policy = factory()
        if not isinstance(policy, ModulationPolicy):
            raise TypeError(
                f"factory for {name!r} produced {type(policy)!r}, "
                "which does not implement ModulationPolicy"
            )
        return policy

    def known(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))


def apply_policy_change(
    modulator: RegimeModulator,
    registry: PolicyRegistry,
    policy_name: str,
) -> ModulationPolicy:
    """Runtime reconfiguration path — resolve by name, swap atomically.

    Returns the previous policy so the caller can log / audit the
    change. Never raises on a failed swap: if ``resolve`` raises, the
    modulator is untouched and the exception propagates.
    """
    new_policy = registry.resolve(policy_name)
    return modulator.swap_policy(new_policy)


__all__ = [
    "ExponentialDecayPolicy",
    "ModulationPolicy",
    "PolicyRegistry",
    "RegimeModulator",
    "RegimeState",
    "apply_policy_change",
]
