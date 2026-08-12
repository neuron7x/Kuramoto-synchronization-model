# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Schema-versioned audit-ledger entries for epistemic state transitions.

Every accepted advance of an :class:`EpistemicState` lineage —
whether produced by :func:`core.neuro.epistemic_validation.update`,
:func:`core.neuro.epistemic_validation.verify_stream`, or
:func:`core.neuro.epistemic_validation.reset_with_external_proof` —
can be summarised into a single self-describing dictionary suitable
for serialisation alongside the system's existing chronology
artefacts. This module produces those dictionaries.

Why a separate module
---------------------

The :mod:`core.neuro.epistemic_validation` core is intentionally
*pure*: it has no JSON, no logging, no I/O, no opinions about how
state is persisted. The audit envelope is a *consumer* of that
purity, not a producer. Keeping it out of the core preserves two
contracts at once: every public function in the core remains a
total mathematical mapping, and the audit envelope can evolve its
schema without forcing a re-cut of the core's pinned hash format.

Schema
------

A :class:`EpistemicAuditEntry` is a frozen :class:`TypedDict`
containing the following fields:

* ``schema`` — the literal string ``"epistemic-audit/1"``. Bumped
  on a breaking shape change (field rename, type change,
  semantically incompatible meaning). Adding a field is additive
  and does NOT bump the version.
* ``transition`` — one of ``"advance"`` (a normal
  :func:`update` step), ``"halt"`` (the step on which a previously
  active state transitions to halted), or ``"reset"`` (output of
  :func:`reset_with_external_proof`).
* ``seq`` — the post-transition sequence number.
* ``prev_hash`` — the chain hash of the state *before* the
  transition.
* ``next_hash`` — the chain hash of the state *after* the
  transition.
* ``weight``, ``budget``, ``invariant_floor`` — post-transition
  values, copied verbatim.
* ``phase`` — ``"active"`` or ``"halted"`` (the
  :class:`EpistemicPhase` value).
* ``halt_reason`` — empty string for active states; one of
  ``"budget_exhausted"`` or ``"weight_collapse"`` for halts.
* ``cost_paid`` — the change in budget across the transition,
  always ``≥ 0`` (INV-FE2 component). For a ``"reset"`` transition
  the value is ``-1.0`` — a sentinel marking that the budget was
  re-allocated rather than spent (chosen specifically so that
  serialised entries cannot silently mix into a positive-cost
  aggregate).

The intended consumer is the system's existing schema-versioned,
SHA-256-checksummed envelope (e.g.,
``geosync_hpc.runtime_state.dump_envelope`` / ``load_envelope``).
This module emits the inner dictionary; framing is the consumer's
responsibility.
"""

from __future__ import annotations

from typing import Final, Literal, TypedDict

from core.neuro.epistemic_validation import EpistemicState

__all__ = [
    "AUDIT_SCHEMA_VERSION",
    "EpistemicAuditEntry",
    "advance_entry",
    "reset_entry",
]


AUDIT_SCHEMA_VERSION: Final[str] = "epistemic-audit/1"

_RESET_COST_SENTINEL: Final[float] = -1.0


TransitionKind = Literal["advance", "halt", "reset"]


class EpistemicAuditEntry(TypedDict):
    """Self-describing record of one state-lineage transition."""

    schema: str
    transition: TransitionKind
    seq: int
    prev_hash: str
    next_hash: str
    weight: float
    budget: float
    invariant_floor: float
    phase: str
    halt_reason: str
    cost_paid: float


def _classify(prev: EpistemicState, next_state: EpistemicState) -> TransitionKind:
    if not prev.is_halted and next_state.is_halted:
        return "halt"
    return "advance"


def advance_entry(prev: EpistemicState, next_state: EpistemicState) -> EpistemicAuditEntry:
    """Emit an audit entry for a normal update / halt transition.

    The ``cost_paid`` field is computed as ``prev.budget −
    next_state.budget``, which is non-negative by INV-FE2 (the
    budget register is monotonically non-increasing under
    :func:`update`). Use :func:`reset_entry` for the post-reset
    transition — its budget *increases* and that is not a valid
    "cost paid".

    Parameters
    ----------
    prev:
        State immediately before the transition.
    next_state:
        State after the transition. Must descend from ``prev`` —
        the caller is responsible for ensuring lineage continuity
        (the hash chain is the authoritative check); this function
        does not re-verify the chain.

    Raises
    ------
    ValueError
        If ``next_state.seq`` is not strictly greater than
        ``prev.seq`` — a non-advancing pair cannot be audited as an
        ``"advance"`` or ``"halt"``. Use :func:`reset_entry` for
        external-proof resets, and do not emit audit entries for
        sticky-halt no-ops (no transition occurred).
    """
    if next_state.seq <= prev.seq:
        raise ValueError(
            f"advance_entry: next_state.seq ({next_state.seq}) must be > "
            f"prev.seq ({prev.seq}). Sticky-halt no-ops do not produce audit "
            "entries; resets must use reset_entry()."
        )
    cost_paid = prev.budget - next_state.budget
    return EpistemicAuditEntry(
        schema=AUDIT_SCHEMA_VERSION,
        transition=_classify(prev, next_state),
        seq=next_state.seq,
        prev_hash=prev.state_hash,
        next_hash=next_state.state_hash,
        weight=next_state.weight,
        budget=next_state.budget,
        invariant_floor=next_state.invariant_floor,
        phase=next_state.phase.value,
        halt_reason=next_state.halt_reason,
        cost_paid=cost_paid,
    )


def reset_entry(halted: EpistemicState, fresh: EpistemicState) -> EpistemicAuditEntry:
    """Emit an audit entry for a post-reset transition.

    The ``cost_paid`` field is set to ``-1.0`` — a sentinel marking
    that the budget was re-allocated rather than spent. Aggregators
    that sum ``cost_paid`` across a window must therefore filter
    on ``transition == "advance"`` or ``transition == "halt"`` to
    avoid mixing the sentinel into a thermodynamic accounting.

    Parameters
    ----------
    halted:
        The halted state input to
        :func:`reset_with_external_proof`.
    fresh:
        The :attr:`EpistemicPhase.ACTIVE` state returned by the
        reset.

    Raises
    ------
    ValueError
        If ``halted`` is not actually halted, or if ``fresh.seq``
        is not exactly ``halted.seq + 1`` (the lineage continuity
        contract).
    """
    if not halted.is_halted:
        raise ValueError(
            f"reset_entry: halted argument is in phase {halted.phase.value!r}, not 'halted'."
        )
    if fresh.seq != halted.seq + 1:
        raise ValueError(
            f"reset_entry: fresh.seq ({fresh.seq}) must equal halted.seq + 1 ({halted.seq + 1})."
        )
    return EpistemicAuditEntry(
        schema=AUDIT_SCHEMA_VERSION,
        transition="reset",
        seq=fresh.seq,
        prev_hash=halted.state_hash,
        next_hash=fresh.state_hash,
        weight=fresh.weight,
        budget=fresh.budget,
        invariant_floor=fresh.invariant_floor,
        phase=fresh.phase.value,
        halt_reason=fresh.halt_reason,
        cost_paid=_RESET_COST_SENTINEL,
    )
