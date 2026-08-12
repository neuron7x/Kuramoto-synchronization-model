# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Canonical-Seven orchestrator — composes all seven pillars.

End-to-end glue that takes the supplied evidence inputs (firewall,
leakage, ladder, fragility, replication) and produces:

    1. The aggregate :class:`TierTransition` from the death engine.
    2. The post-application :class:`GovernanceFSM` state.

This is the capstone function: callers can drive a claim through one
canonical round by collecting outcomes from each pillar and passing
them here. The orchestrator is **stateless** — it never reads from
disk, never mutates inputs, and is fully deterministic on its
arguments.

Pure-function API. No I/O.
"""

from __future__ import annotations

from dataclasses import dataclass

from .death_conditions import (
    DataFirewallResultLike,
    DeathConditionsRegistry,
    DeathState,
    FragilityResultLike,
    LadderResultLike,
    LeakageResultLike,
    ReplicationResultLike,
    TierTransition,
    default_registry,
)
from .governance_fsm import GovernanceFSM

__all__ = [
    "CanonicalSevenInputs",
    "CanonicalSevenOutcome",
    "run_canonical_seven",
]


@dataclass(frozen=True, slots=True)
class CanonicalSevenInputs:
    """Bundle of pillar outputs consumed by the orchestrator.

    Each field is optional; missing inputs simply produce
    ``fired=False`` outcomes for the corresponding trigger (per the
    contract of :class:`DeathConditionsRegistry`).

    Attributes
    ----------
    firewall
        Output of :func:`research.systemic_risk.data_firewall
        .run_data_firewall`. ``passed_all=False`` drives ``STOP``
        via T5.
    leakage
        Output of :func:`research.systemic_risk.leakage_sentinel
        .run_leakage_audit`. ``detected=True`` drives
        ``INVALIDATE`` via T2.
    ladder
        Output of :func:`research.systemic_risk.adversarial_ladder
        .run_adversarial_ladder`. Non-empty ``losing_paths`` drives
        ``DEMOTE`` via T1.
    fragility
        Output of the parameter-fragility audit. ``fragile=True``
        drives ``QUARANTINE`` via T3.
    replication
        Output of :func:`research.systemic_risk.replication_capsule
        .compare_run_outputs`. ``matched=False`` drives ``KILL`` via
        T4.
    """

    firewall: DataFirewallResultLike | None = None
    leakage: LeakageResultLike | None = None
    ladder: LadderResultLike | None = None
    fragility: FragilityResultLike | None = None
    replication: ReplicationResultLike | None = None


@dataclass(frozen=True, slots=True)
class CanonicalSevenOutcome:
    """Capstone outcome of a single canonical round.

    Attributes
    ----------
    transition
        Aggregate :class:`TierTransition` from the death engine — the
        single dominant action under
        ``KILL > INVALIDATE > QUARANTINE > DEMOTE > STOP > NONE``.
    fsm_after
        :class:`GovernanceFSM` after applying the transition.
    """

    transition: TierTransition
    fsm_after: GovernanceFSM


def run_canonical_seven(
    *,
    inputs: CanonicalSevenInputs,
    fsm_before: GovernanceFSM,
    registry: DeathConditionsRegistry | None = None,
) -> CanonicalSevenOutcome:
    """Drive one claim through one canonical round.

    Parameters
    ----------
    inputs
        Bundle of pillar outputs (firewall, leakage, ladder,
        fragility, replication). Any subset may be ``None``.
    fsm_before
        Current :class:`GovernanceFSM` state of the claim. Must not
        be in :data:`research.systemic_risk.governance_fsm.TERMINAL_STATES`
        unless the caller is intentionally re-validating an absorbed
        claim (in which case the FSM's absorbing logic returns the
        same state with an audit row).
    registry
        Optional custom death-conditions registry. Defaults to
        :func:`default_registry` (the canonical 5 triggers).

    Returns
    -------
    CanonicalSevenOutcome
        Aggregate transition + post-application FSM state.
    """
    death_state = DeathState(
        ladder=inputs.ladder,
        leakage=inputs.leakage,
        fragility=inputs.fragility,
        replication=inputs.replication,
        firewall=inputs.firewall,
    )
    reg = registry if registry is not None else default_registry()
    transition = reg.evaluate(death_state)
    fsm_after = fsm_before.apply(transition)
    return CanonicalSevenOutcome(transition=transition, fsm_after=fsm_after)
