# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Hypothesis Death Engine — typed registry of kill / demote triggers.

Operationalises § 1 of the canonical-7 charter. A hypothesis is
scientific iff it carries explicit conditions for its own death;
this module ships those conditions as a typed trigger registry
together with the precedence rule that maps the disjunction of
fired triggers to a single tier transition.

Precedence (charter § 1 PATCH 1.2):

    KILL > INVALIDATE > QUARANTINE > DEMOTE > STOP

Five tier actions are defined; each has a single, distinct
operational meaning so a future demotion cannot silently net out
against another demotion:

* **KILL** — terminal transition to ``REJECTED``.
* **INVALIDATE** — drop to ``IDEA``; prior evidence is struck
  from the ledger; new instrumentation required.
* **QUARANTINE** — freeze the current tier; require external
  sign-off to unfreeze.
* **DEMOTE** — drop one tier; prior evidence retained.
* **STOP** — refuse to advance the *run* pipeline; the *claim*
  is unaffected.

Pure-function API. No I/O.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, Protocol

__all__ = [
    "TierAction",
    "Trigger",
    "TriggerOutcome",
    "TierTransition",
    "DeathConditionsRegistry",
    "LadderResultLike",
    "FragilityResultLike",
    "LeakageResultLike",
    "ReplicationResultLike",
    "DataFirewallResultLike",
    "trigger_baseline_dominance",
    "trigger_leakage_positive",
    "trigger_parameter_fragility",
    "trigger_replication_mismatch",
    "trigger_data_proxy_invalid",
    "default_registry",
]


TierAction = Literal[
    "NONE",
    "STOP",
    "DEMOTE",
    "QUARANTINE",
    "INVALIDATE",
    "KILL",
]


# Precedence is encoded algebraically in research.systemic_risk.verdict_lattice
# as the join (⊔) on the totally-ordered TierLattice; see that module for the
# formal axioms (commutativity / associativity / idempotence / identity at
# NONE) and the Hypothesis-checked property tests.


# ---------------------------------------------------------------------------
# Structural protocols — keep death_conditions decoupled from concrete types
# ---------------------------------------------------------------------------


class LadderResultLike(Protocol):
    """Anything with a ``losing_paths`` tuple counts as a ladder result."""

    losing_paths: tuple[str, ...]


class FragilityResultLike(Protocol):
    """Output of a single-knob parameter-fragility audit."""

    fragile: bool


class LeakageResultLike(Protocol):
    """Output of the leakage sentinel."""

    detected: bool


class ReplicationResultLike(Protocol):
    """Outcome of a capsule rerun comparison."""

    matched: bool


class DataFirewallResultLike(Protocol):
    """Outcome of the data-reality firewall (eight-gate)."""

    passed_all: bool


# ---------------------------------------------------------------------------
# Trigger record + outcome
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TriggerOutcome:
    """One trigger evaluation.

    Attributes
    ----------
    name
        Trigger identifier.
    fired
        Whether the trigger condition evaluated True.
    action
        Tier action implied by *this* trigger when fired; ``NONE``
        when not fired.
    reason
        Free-form explanation suitable for inclusion in an audit
        report.
    """

    name: str
    fired: bool
    action: TierAction
    reason: str


@dataclass(frozen=True, slots=True)
class TierTransition:
    """Aggregate transition across the trigger registry.

    Attributes
    ----------
    action
        The single dominant action under
        ``KILL > INVALIDATE > QUARANTINE > DEMOTE > STOP > NONE``.
    fired_triggers
        Names of every trigger that fired.
    outcomes
        Full per-trigger evaluation log (fired and non-fired).
    """

    action: TierAction
    fired_triggers: tuple[str, ...]
    outcomes: tuple[TriggerOutcome, ...]


# ---------------------------------------------------------------------------
# Built-in trigger functions (each maps a state to a TriggerOutcome)
# ---------------------------------------------------------------------------


def trigger_baseline_dominance(
    ladder: LadderResultLike | None,
) -> TriggerOutcome:
    """T1 — any prosecutor not beaten on the engaged ladder → DEMOTE."""
    if ladder is None:
        return TriggerOutcome(
            name="baseline_dominance",
            fired=False,
            action="NONE",
            reason="no ladder result supplied",
        )
    fired = bool(ladder.losing_paths)
    return TriggerOutcome(
        name="baseline_dominance",
        fired=fired,
        action="DEMOTE" if fired else "NONE",
        reason=(
            f"{len(ladder.losing_paths)} prosecutors not beaten: {ladder.losing_paths}"
            if fired
            else "candidate beat every engaged prosecutor"
        ),
    )


def trigger_leakage_positive(
    leakage: LeakageResultLike | None,
) -> TriggerOutcome:
    """T2 — leakage sentinel detected any forbidden time-flow → INVALIDATE."""
    if leakage is None:
        return TriggerOutcome(
            name="leakage_positive",
            fired=False,
            action="NONE",
            reason="no leakage audit supplied",
        )
    fired = bool(leakage.detected)
    return TriggerOutcome(
        name="leakage_positive",
        fired=fired,
        action="INVALIDATE" if fired else "NONE",
        reason=("leakage detected — claim invalidated to IDEA" if fired else "leakage audit clean"),
    )


def trigger_parameter_fragility(
    fragility: FragilityResultLike | None,
) -> TriggerOutcome:
    """T3 — parameter sweep flips the verdict → QUARANTINE."""
    if fragility is None:
        return TriggerOutcome(
            name="parameter_fragility",
            fired=False,
            action="NONE",
            reason="no fragility audit supplied",
        )
    fired = bool(fragility.fragile)
    return TriggerOutcome(
        name="parameter_fragility",
        fired=fired,
        action="QUARANTINE" if fired else "NONE",
        reason=(
            "AUC range exceeds tolerance — quarantine pending external review"
            if fired
            else "verdict stable across parameter sweep"
        ),
    )


def trigger_replication_mismatch(
    replication: ReplicationResultLike | None,
) -> TriggerOutcome:
    """T4 — capsule rerun does not match → KILL."""
    if replication is None:
        return TriggerOutcome(
            name="replication_mismatch",
            fired=False,
            action="NONE",
            reason="no replication result supplied",
        )
    fired = not replication.matched
    return TriggerOutcome(
        name="replication_mismatch",
        fired=fired,
        action="KILL" if fired else "NONE",
        reason=(
            "capsule rerun diverged from original — claim REJECTED"
            if fired
            else "capsule rerun matched"
        ),
    )


def trigger_data_proxy_invalid(
    firewall: DataFirewallResultLike | None,
) -> TriggerOutcome:
    """T5 — eight-gate data firewall failed → STOP."""
    if firewall is None:
        return TriggerOutcome(
            name="data_proxy_invalid",
            fired=False,
            action="NONE",
            reason="no firewall result supplied",
        )
    fired = not firewall.passed_all
    return TriggerOutcome(
        name="data_proxy_invalid",
        fired=fired,
        action="STOP" if fired else "NONE",
        reason=(
            "data-reality firewall rejected ingress — run halted"
            if fired
            else "all eight data gates passed"
        ),
    )


# ---------------------------------------------------------------------------
# Trigger registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Trigger:
    """One registered trigger.

    A trigger is a callable that accepts the registry's state
    payload and returns a :class:`TriggerOutcome`. The registry
    invokes every registered trigger in registration order; each
    trigger is responsible for its own short-circuit semantics.
    """

    name: str
    action_when_fired: TierAction
    evaluate: Callable[["DeathState"], TriggerOutcome]


@dataclass(frozen=True, slots=True)
class DeathState:
    """Read-only state passed to every trigger.

    Each field is optional so triggers can be added in any order
    and missing inputs simply produce ``fired=False`` outcomes.
    """

    ladder: LadderResultLike | None = None
    leakage: LeakageResultLike | None = None
    fragility: FragilityResultLike | None = None
    replication: ReplicationResultLike | None = None
    firewall: DataFirewallResultLike | None = None


@dataclass(frozen=True, slots=True)
class DeathConditionsRegistry:
    """Composes registered triggers into a single :class:`TierTransition`.

    Frozen by design — to add a new trigger, build a new registry
    with :meth:`extend`. The registry never mutates the trigger
    list in place.
    """

    triggers: tuple[Trigger, ...] = field(default_factory=tuple)

    def extend(self, trigger: Trigger) -> "DeathConditionsRegistry":
        return DeathConditionsRegistry(triggers=self.triggers + (trigger,))

    def evaluate(self, state: DeathState) -> TierTransition:
        # Pair each registered trigger with its outcome so the
        # fired_triggers tuple reports the *registered* name (e.g.
        # "T1_baseline_dominance") rather than the outcome name
        # produced by the underlying check function.
        evaluated = [(t, t.evaluate(state)) for t in self.triggers]
        outcomes = tuple(o for _, o in evaluated)
        fired = tuple(t.name for t, o in evaluated if o.fired)
        # Algebraic aggregation: the precedence rule
        #   KILL > INVALIDATE > QUARANTINE > DEMOTE > STOP > NONE
        # is exactly the join (⊔) over the totally-ordered TierLattice.
        # See research.systemic_risk.verdict_lattice for the formal
        # algebra and Hypothesis-checked lattice axioms.
        from .verdict_lattice import TierLattice, aggregate_actions

        joined = aggregate_actions(
            TierLattice.from_action_name(o.action) for _, o in evaluated if o.fired
        )
        action: TierAction = joined.name  # type: ignore[assignment]
        return TierTransition(
            action=action,
            fired_triggers=fired,
            outcomes=outcomes,
        )


# ---------------------------------------------------------------------------
# Default registry — the five canonical triggers
# ---------------------------------------------------------------------------


def default_registry() -> DeathConditionsRegistry:
    """Return the canonical 5-trigger registry from charter § 1."""
    triggers = (
        Trigger(
            name="T1_baseline_dominance",
            action_when_fired="DEMOTE",
            evaluate=lambda s: trigger_baseline_dominance(s.ladder),
        ),
        Trigger(
            name="T2_leakage_positive",
            action_when_fired="INVALIDATE",
            evaluate=lambda s: trigger_leakage_positive(s.leakage),
        ),
        Trigger(
            name="T3_parameter_fragility",
            action_when_fired="QUARANTINE",
            evaluate=lambda s: trigger_parameter_fragility(s.fragility),
        ),
        Trigger(
            name="T4_replication_mismatch",
            action_when_fired="KILL",
            evaluate=lambda s: trigger_replication_mismatch(s.replication),
        ),
        Trigger(
            name="T5_data_proxy_invalid",
            action_when_fired="STOP",
            evaluate=lambda s: trigger_data_proxy_invalid(s.firewall),
        ),
    )
    return DeathConditionsRegistry(triggers=triggers)
