# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Cognitive core — the system's value function over the physical-invariant manifold.

The cognitive core is the active invariant centre: a single deterministic gate
that takes a live system snapshot and routes it through every configured physical
invariant at once, returning one fail-closed admissibility verdict and naming the
binding constraint. It generalises the three-invariant
``coherence_bridge/physics_contract.py`` seed (INV-K1, INV-RC1, T3) to the full
live-state spine.

It is the system's VALUE FUNCTION in the control-theoretic sense:

    V(snapshot) = GO   iff   snapshot lies inside the invariant manifold
                = NO_GO otherwise (fail-closed).

The core never generates options; it preserves controllability — converting a
reality-divergence (a snapshot leaving the manifold) into a fired gate with a
named binding constraint, so downstream actuation can refuse to act. Every gate
is total and fail-closed: an empty snapshot, a missing configured field, a
non-finite value, or an out-of-range value yields NO_GO with no silent pass.

Each gate cites the invariant it enforces. The bounds are the same ones proven
elsewhere in the executable falsification catalog (physics_contracts/), so the
core is the live-state composition of laws that are individually witnessed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Final, Mapping


class Decision(str, Enum):
    """Fail-closed admissibility decision. Downstream MUST act on this, not on raw fields."""

    GO = "GO"
    NO_GO = "NO_GO"


class Status(str, Enum):
    """Why the verdict was reached."""

    ADMISSIBLE = "ADMISSIBLE"  # every configured gate passed
    INADMISSIBLE = "INADMISSIBLE"  # at least one configured gate fired
    INSUFFICIENT = "INSUFFICIENT"  # empty snapshot — refuse to vacuously pass


@dataclass(frozen=True)
class GateResult:
    """Per-invariant outcome inside the core."""

    invariant: str
    field_name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class CoreVerdict:
    """The cognitive core's deterministic admissibility verdict (the value-function output)."""

    decision: Decision
    status: Status
    gates: tuple[GateResult, ...]
    violations: tuple[str, ...]
    binding_constraint: str | None  # the first invariant that fired, or None

    @property
    def admissible(self) -> bool:
        return self.decision is Decision.GO


@dataclass(frozen=True)
class _Gate:
    """A single live-state invariant gate."""

    invariant: str
    field_name: str
    # Returns (passed, detail). Only called with a value that is present.
    check: Callable[[object], tuple[bool, str]]


def _finite(x: object) -> float | None:
    """Coerce to a finite float, or None if not a finite real scalar.

    ``bool`` is rejected as an ambiguous scalar; ``int``/``float`` (and numpy
    float subclasses) are accepted. Strings, ``None`` and anything else -> None.
    """
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    v = float(x)
    return v if math.isfinite(v) else None


def _unit_interval(invariant: str) -> Callable[[object], tuple[bool, str]]:
    """Gate factory: value must be a finite scalar in [0, 1]."""

    def check(x: object) -> tuple[bool, str]:
        v = _finite(x)
        if v is None:
            return False, f"{invariant}: non-finite or non-scalar (fail-closed)"
        if not (0.0 <= v <= 1.0):
            return False, f"{invariant}: {v:.6g} left [0, 1]"
        return True, f"{invariant}: {v:.6g} in [0, 1]"

    return check


def _upper_bound(invariant: str, hi: float) -> Callable[[object], tuple[bool, str]]:
    """Gate factory: value must be a finite scalar <= hi (universal upper bound only)."""

    def check(x: object) -> tuple[bool, str]:
        v = _finite(x)
        if v is None:
            return False, f"{invariant}: non-finite or non-scalar (fail-closed)"
        if v > hi:
            return False, f"{invariant}: {v:.6g} exceeds upper bound {hi:g}"
        return True, f"{invariant}: {v:.6g} <= {hi:g}"

    return check


def _abs_bound(invariant: str, mag: float) -> Callable[[object], tuple[bool, str]]:
    """Gate factory: |value| must be a finite scalar <= mag."""

    def check(x: object) -> tuple[bool, str]:
        v = _finite(x)
        if v is None:
            return False, f"{invariant}: non-finite or non-scalar (fail-closed)"
        if abs(v) > mag:
            return False, f"{invariant}: |{v:.6g}| exceeds {mag:g}"
        return True, f"{invariant}: |{v:.6g}| <= {mag:g}"

    return check


def _nonneg_finite(invariant: str) -> Callable[[object], tuple[bool, str]]:
    """Gate factory: value must be a finite scalar >= 0."""

    def check(x: object) -> tuple[bool, str]:
        v = _finite(x)
        if v is None:
            return False, f"{invariant}: non-finite or non-scalar (fail-closed)"
        if v < 0.0:
            return False, f"{invariant}: {v:.6g} < 0"
        return True, f"{invariant}: {v:.6g} >= 0"

    return check


def _free_energy_components(invariant: str) -> Callable[[object], tuple[bool, str]]:
    """Gate factory: INV-FE2 — each of (U, T, S_q) >= 0 (the composite F may be negative)."""

    def check(x: object) -> tuple[bool, str]:
        if not isinstance(x, (tuple, list)) or len(x) != 3:
            return False, f"{invariant}: components not a (U, T, S) triple (fail-closed)"
        u, t, s = _finite(x[0]), _finite(x[1]), _finite(x[2])
        if u is None or t is None or s is None:
            return False, f"{invariant}: non-finite or non-scalar component (fail-closed)"
        if min(u, t, s) < 0.0:
            return False, f"{invariant}: a component < 0 (U={u:.4g}, T={t:.4g}, S={s:.4g})"
        return True, f"{invariant}: U={u:.4g}, T={t:.4g}, S={s:.4g} all >= 0"

    return check


# The live-state invariant spine. Each configured snapshot key is required and
# gated by the named invariant. Bounds match the executable falsification catalog.
_GATES: Final[tuple[_Gate, ...]] = (
    _Gate("INV-K1", "order_parameter_R", _unit_interval("INV-K1")),
    _Gate("INV-OA1", "z_abs", _unit_interval("INV-OA1")),
    _Gate("INV-RC1", "ollivier_kappa", _upper_bound("INV-RC1", 1.0)),
    _Gate("INV-DRO2", "gamma", _nonneg_finite("INV-DRO2")),
    _Gate("INV-5HT2", "serotonin_level", _unit_interval("INV-5HT2")),
    _Gate("INV-GABA1", "gaba_gate", _unit_interval("INV-GABA1")),
    _Gate("INV-DA8", "dopamine_signal", _abs_bound("INV-DA8", 1.0)),
    _Gate("INV-KELLY2", "kelly_fraction", _unit_interval("INV-KELLY2")),
    _Gate("INV-FE2", "free_energy_components", _free_energy_components("INV-FE2")),
)

GATED_FIELDS: Final[frozenset[str]] = frozenset(g.field_name for g in _GATES)

# Public, immutable view of the default invariant spine so callers can build a
# restricted core (a subset of gates) without reaching into private state.
DEFAULT_GATES: Final[tuple[_Gate, ...]] = _GATES


class CognitiveCore:
    """The active invariant centre: one fail-closed admissibility value function."""

    def __init__(self, gates: tuple[_Gate, ...] = _GATES) -> None:
        if not gates:
            raise ValueError("CognitiveCore requires at least one invariant gate")
        self._gates = gates

    def admissibility(self, snapshot: Mapping[str, object]) -> CoreVerdict:
        """Route a live snapshot through every configured invariant gate, fail-closed.

        An empty snapshot is ``INSUFFICIENT`` -> ``NO_GO`` (the core never
        vacuously approves). For a non-empty snapshot, every configured gate is
        required: a missing field is itself a violation, any failing value is a
        violation, and only a complete in-manifold snapshot can return ``GO``.
        """
        if not snapshot:
            return CoreVerdict(
                decision=Decision.NO_GO,
                status=Status.INSUFFICIENT,
                gates=(),
                violations=(),
                binding_constraint=None,
            )

        results: list[GateResult] = []
        violations: list[str] = []
        for gate in self._gates:
            if gate.field_name not in snapshot:
                detail = f"{gate.invariant}: missing {gate.field_name!r} (fail-closed)"
                results.append(GateResult(gate.invariant, gate.field_name, False, detail))
                violations.append(gate.invariant)
                continue
            passed, detail = gate.check(snapshot[gate.field_name])
            results.append(GateResult(gate.invariant, gate.field_name, passed, detail))
            if not passed:
                violations.append(gate.invariant)

        if violations:
            return CoreVerdict(
                decision=Decision.NO_GO,
                status=Status.INADMISSIBLE,
                gates=tuple(results),
                violations=tuple(violations),
                binding_constraint=violations[0],
            )
        return CoreVerdict(
            decision=Decision.GO,
            status=Status.ADMISSIBLE,
            gates=tuple(results),
            violations=(),
            binding_constraint=None,
        )


class InadmissibleStateError(RuntimeError):
    """Raised when actuation is attempted on a snapshot outside the invariant manifold.

    Carries the full :class:`CoreVerdict` so the caller can log the binding
    constraint. This is the runtime teeth of the cognitive core: the value
    function does not merely *report* NO_GO, it *prevents* the action.
    """

    def __init__(self, verdict: CoreVerdict) -> None:
        self.verdict = verdict
        constraint = verdict.binding_constraint or verdict.status.value
        super().__init__(
            f"INADMISSIBLE: actuation refused — snapshot left the invariant manifold "
            f"(status={verdict.status.value}, binding_constraint={constraint}, "
            f"violations={list(verdict.violations)}). Fail-closed."
        )


_DEFAULT_CORE: Final[CognitiveCore] = CognitiveCore()


def require_admissible(
    snapshot: Mapping[str, object], core: CognitiveCore | None = None
) -> CoreVerdict:
    """Runtime enforcement gate: return the verdict iff GO, else raise (fail-closed).

    Actuation paths call this to REFUSE to act on a state outside the invariant
    manifold. It is the live wiring of the value function into control: a GO
    snapshot passes through with its verdict; any NO_GO (a fired gate or an
    insufficient/empty snapshot) raises :class:`InadmissibleStateError`. There is
    no silent path to action.
    """
    verdict = (core or _DEFAULT_CORE).admissibility(snapshot)
    if not verdict.admissible:
        raise InadmissibleStateError(verdict)
    return verdict
