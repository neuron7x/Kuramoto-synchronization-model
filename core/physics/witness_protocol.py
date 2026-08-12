# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unified witness protocol — minimal cross-invariant evidence shape.

Each runtime-evaluable physics-invariant module ships its own
domain-specific witness type (ArrowOfTimeWitness, BandwidthWitness,
ComputeBudgetWitness, JacobsonObserverWitness,
AnchoredSubstrateGateWitness). The domain types preserve all the
math fields a caller needs for downstream physics computation.

This module adds normalization adapters — `normalize_*_witness` — that
project each domain witness onto a small common shape so cross-axis
telemetry (logging, dashboards, integration tests, evidence ledgers)
can read every witness through one interface without touching the
domain types.

Option A from protocol §4: adapter functions. Chosen because adding
fields to existing dataclasses (Option B) or wrapping witnesses
(Option C) would either destabilize public APIs or force callers to
unwrap. Adapters are additive, non-breaking, and one-way (no
information lost — the original witness can still be passed through).

Common shape:
  - invariant_id: str             — e.g. "INV-ARROW-OF-TIME"
  - tier: ProvenanceTier          — ANCHORED / EXTRAPOLATED / SPECULATIVE
  - passed: bool                  — True iff this axis admits the input
  - reason: str | None            — failure rationale or None on pass

Registry-only invariants (e.g. INV-SIMULATION-FALSIFICATION as a
ladder) deliberately do NOT have a normalize_* adapter. They have no
single substrate-state evaluation; mapping a ladder to a single
"passed" boolean would be a lie. Per-signature point evaluations may
gain their own normalizer in a separate task (T5).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from core.physics.anchored_substrate_gate import AnchoredSubstrateGateWitness
from core.physics.arrow_of_time import ArrowOfTimeWitness
from core.physics.cosmological_compute_bound import ComputeBudgetWitness
from core.physics.jacobson_observer_coherence import JacobsonObserverWitness
from core.physics.observer_bandwidth import BandwidthWitness

__all__ = [
    "NormalizedInvariantWitness",
    "ProvenanceTier",
    "normalize_anchored_substrate_gate_witness",
    "normalize_arrow_witness",
    "normalize_bandwidth_witness",
    "normalize_compute_budget_witness",
    "normalize_jacobson_witness",
]

ProvenanceTier = Literal["ANCHORED", "EXTRAPOLATED", "SPECULATIVE"]


@dataclass(frozen=True, slots=True)
class NormalizedInvariantWitness:
    """Minimal cross-invariant witness shape.

    Carries only what a generic consumer (logger, ledger, dashboard,
    integration assertion) needs. Domain witnesses remain the source
    of truth for math; this projection is read-only telemetry.
    """

    invariant_id: str
    tier: ProvenanceTier
    passed: bool
    reason: str | None


def normalize_arrow_witness(witness: ArrowOfTimeWitness) -> NormalizedInvariantWitness:
    """INV-ARROW-OF-TIME, ANCHORED tier."""
    return NormalizedInvariantWitness(
        invariant_id="INV-ARROW-OF-TIME",
        tier="ANCHORED",
        passed=witness.is_arrow_consistent,
        reason=witness.reason,
    )


def normalize_anchored_substrate_gate_witness(
    witness: AnchoredSubstrateGateWitness,
) -> NormalizedInvariantWitness:
    """INV-ANCHORED-SUBSTRATE-GATE, ANCHORED tier (composite)."""
    return NormalizedInvariantWitness(
        invariant_id="INV-ANCHORED-SUBSTRATE-GATE",
        tier="ANCHORED",
        passed=witness.is_thermodynamically_admissible,
        reason=witness.reason,
    )


def normalize_bandwidth_witness(witness: BandwidthWitness) -> NormalizedInvariantWitness:
    """INV-OBSERVER-BANDWIDTH, SPECULATIVE tier (post-PR #421)."""
    return NormalizedInvariantWitness(
        invariant_id="INV-OBSERVER-BANDWIDTH",
        tier="SPECULATIVE",
        passed=witness.is_bound_consistent,
        reason=witness.reason,
    )


def normalize_compute_budget_witness(
    witness: ComputeBudgetWitness,
) -> NormalizedInvariantWitness:
    """INV-COSMOLOGICAL-COMPUTE, EXTRAPOLATED tier."""
    return NormalizedInvariantWitness(
        invariant_id="INV-COSMOLOGICAL-COMPUTE",
        tier="EXTRAPOLATED",
        passed=witness.is_within_budget,
        reason=witness.reason,
    )


def normalize_jacobson_witness(
    witness: JacobsonObserverWitness,
) -> NormalizedInvariantWitness:
    """INV-JACOBSON-OBSERVER, EXTRAPOLATED tier.

    Reports `passed = is_extended_consistent` — the contract that
    consumes the observer-coherence correction. Pure-Jacobson
    consistency is also exposed via the domain witness directly.
    """
    return NormalizedInvariantWitness(
        invariant_id="INV-JACOBSON-OBSERVER",
        tier="EXTRAPOLATED",
        passed=witness.is_extended_consistent,
        reason=witness.reason,
    )
