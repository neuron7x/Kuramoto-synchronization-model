# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
# no-bio-claim
"""Tests for the unified witness protocol (Task 4).

Each runtime-evaluable physics module's domain witness must be
projectable onto NormalizedInvariantWitness via its corresponding
adapter. Adapters are read-only — they do not mutate domain witnesses.
"""

from __future__ import annotations

import math

import pytest

from core.physics.anchored_substrate_gate import (
    SubstrateGateInputs,
    assess_anchored_substrate_gate,
)
from core.physics.arrow_of_time import (
    ObserverEntropyLedger,
    assess_arrow_of_time,
)
from core.physics.cosmological_compute_bound import (
    CausalDiamond,
    assess_compute_claim,
)
from core.physics.jacobson_observer_coherence import (
    ClausiusContext,
    assess_jacobson_observer,
)
from core.physics.observer_bandwidth import (
    assess_bandwidth_bound,
    decoherence_rate_hz,
    observer_bandwidth_hz,
)
from core.physics.simulation_falsification import build_canonical_ladder
from core.physics.thermodynamic_budget import SPEED_OF_LIGHT_M_S
from core.physics.witness_protocol import (
    NormalizedInvariantWitness,
    normalize_anchored_substrate_gate_witness,
    normalize_arrow_witness,
    normalize_bandwidth_witness,
    normalize_compute_budget_witness,
    normalize_jacobson_witness,
)

# ---------------------------------------------------------------------------
# Per-module normalization
# ---------------------------------------------------------------------------


def test_arrow_witness_normalizes_with_anchored_tier_and_correct_id() -> None:
    domain = assess_arrow_of_time(
        ObserverEntropyLedger(
            system_entropy_change_bits=1.0,
            observer_information_gain_bits=0.0,
        )
    )
    norm = normalize_arrow_witness(domain)
    assert isinstance(norm, NormalizedInvariantWitness)
    assert norm.invariant_id == "INV-ARROW-OF-TIME"
    assert norm.tier == "ANCHORED"
    assert norm.passed is True
    assert norm.reason is None


def test_arrow_witness_normalizes_failure_with_reason_passthrough() -> None:
    domain = assess_arrow_of_time(
        ObserverEntropyLedger(
            system_entropy_change_bits=-2.0,
            observer_information_gain_bits=0.0,
        )
    )
    norm = normalize_arrow_witness(domain)
    assert norm.passed is False
    assert norm.reason is not None
    assert "INV-ARROW-OF-TIME" in norm.reason


def test_anchored_substrate_gate_witness_normalizes() -> None:
    inputs = SubstrateGateInputs(
        radius_m=0.07,
        energy_J=1.4 * SPEED_OF_LIGHT_M_S**2,
        observed_information_bits=0.0,
        entropy_ledger=ObserverEntropyLedger(
            system_entropy_change_bits=1.0,
            observer_information_gain_bits=0.0,
        ),
    )
    domain = assess_anchored_substrate_gate(inputs)
    norm = normalize_anchored_substrate_gate_witness(domain)
    assert norm.invariant_id == "INV-ANCHORED-SUBSTRATE-GATE"
    assert norm.tier == "ANCHORED"
    assert norm.passed is True


def test_bandwidth_witness_normalizes_with_speculative_tier() -> None:
    domain = assess_bandwidth_bound(
        decoherence_rate_hz(1.0),
        observer_bandwidth_hz(10.0),
    )
    norm = normalize_bandwidth_witness(domain)
    assert norm.invariant_id == "INV-OBSERVER-BANDWIDTH"
    # Tier reflects PR #421 honest downgrade — SPECULATIVE, not EXTRAPOLATED.
    assert norm.tier == "SPECULATIVE"
    assert norm.passed is True


def test_bandwidth_witness_normalizes_failure() -> None:
    domain = assess_bandwidth_bound(
        decoherence_rate_hz(100.0),
        observer_bandwidth_hz(1.0),
    )
    norm = normalize_bandwidth_witness(domain)
    assert norm.passed is False
    assert norm.reason is not None
    assert "INV-OBSERVER-BANDWIDTH" in norm.reason


def test_compute_budget_witness_normalizes_with_extrapolated_tier() -> None:
    domain = assess_compute_claim(CausalDiamond(horizon_area_m2=1.0), 1.0)
    norm = normalize_compute_budget_witness(domain)
    assert norm.invariant_id == "INV-COSMOLOGICAL-COMPUTE"
    assert norm.tier == "EXTRAPOLATED"
    assert norm.passed is True


def test_jacobson_witness_normalizes_with_extrapolated_tier() -> None:
    domain = assess_jacobson_observer(
        ClausiusContext(
            heat_flow_J=10.0,
            unruh_temperature_K=2.0,
            entropy_change_J_per_K=5.0,
        )
    )
    norm = normalize_jacobson_witness(domain)
    assert norm.invariant_id == "INV-JACOBSON-OBSERVER"
    assert norm.tier == "EXTRAPOLATED"
    assert norm.passed is True
    # Default Jacobson context: c=0, residual ≈ 0 ≤ tolerance, both
    # pure and extended consistent. Adapter tracks `is_extended_consistent`.


# ---------------------------------------------------------------------------
# Cross-cutting properties
# ---------------------------------------------------------------------------


def test_normalized_witness_is_frozen_dataclass() -> None:
    domain = assess_arrow_of_time(
        ObserverEntropyLedger(
            system_entropy_change_bits=0.0,
            observer_information_gain_bits=0.0,
        )
    )
    norm = normalize_arrow_witness(domain)
    with pytest.raises(AttributeError):
        norm.passed = False  # type: ignore[misc]


def test_all_normalizers_produce_anchored_tier_for_anchored_axes_only() -> None:
    """ANCHORED tier is exactly: arrow + anchored gate.
    EXTRAPOLATED: cosmological + jacobson.
    SPECULATIVE: bandwidth.
    Pin tier assignment so honest-provenance contract (PR #414) cannot
    drift via adapter."""
    arrow = normalize_arrow_witness(
        assess_arrow_of_time(
            ObserverEntropyLedger(
                system_entropy_change_bits=0.0,
                observer_information_gain_bits=0.0,
            )
        )
    )
    gate = normalize_anchored_substrate_gate_witness(
        assess_anchored_substrate_gate(
            SubstrateGateInputs(
                radius_m=1.0,
                energy_J=1.0,
                observed_information_bits=0.0,
                entropy_ledger=ObserverEntropyLedger(
                    system_entropy_change_bits=0.0,
                    observer_information_gain_bits=0.0,
                ),
            )
        )
    )
    bandwidth = normalize_bandwidth_witness(
        assess_bandwidth_bound(decoherence_rate_hz(1.0), observer_bandwidth_hz(1.0))
    )
    cosmo = normalize_compute_budget_witness(
        assess_compute_claim(CausalDiamond(horizon_area_m2=1.0), 0.0)
    )
    jacobson = normalize_jacobson_witness(
        assess_jacobson_observer(
            ClausiusContext(
                heat_flow_J=0.0,
                unruh_temperature_K=0.0,
                entropy_change_J_per_K=0.0,
            )
        )
    )

    by_tier: dict[str, set[str]] = {"ANCHORED": set(), "EXTRAPOLATED": set(), "SPECULATIVE": set()}
    for n in (arrow, gate, bandwidth, cosmo, jacobson):
        by_tier[n.tier].add(n.invariant_id)

    assert by_tier["ANCHORED"] == {"INV-ARROW-OF-TIME", "INV-ANCHORED-SUBSTRATE-GATE"}
    assert by_tier["EXTRAPOLATED"] == {"INV-COSMOLOGICAL-COMPUTE", "INV-JACOBSON-OBSERVER"}
    assert by_tier["SPECULATIVE"] == {"INV-OBSERVER-BANDWIDTH"}


def test_simulation_falsification_has_no_substrate_state_normalizer() -> None:
    """INV-SIMULATION-FALSIFICATION is registry-only (a ladder), not a
    substrate-state evaluation. The adapter module deliberately does
    NOT export a normalize_*_witness for it. Mapping a 6-signature
    ladder to a single passed/failed boolean would be a lie.

    Per-signature point evaluations may gain their own normalizer in
    Task 5; that is a different surface than substrate-state."""
    import core.physics.witness_protocol as wp

    public = set(wp.__all__)
    forbidden_substring_patterns = ("simulation_falsification", "ladder", "signature")
    for name in public:
        for pattern in forbidden_substring_patterns:
            assert pattern not in name.lower(), (
                f"witness_protocol must not export a substrate-state "
                f"normalizer for simulation_falsification; found: {name}"
            )

    # Sanity: ladder still constructible and has 6 signatures (registry shape).
    ladder = build_canonical_ladder()
    assert len(ladder.signatures) == 6


def test_normalized_witness_carries_only_minimal_protocol_fields() -> None:
    """Pin the minimal-protocol contract: invariant_id, tier, passed,
    reason. No more. Adding fields requires explicit task + tests."""
    fields = {f.name for f in NormalizedInvariantWitness.__dataclass_fields__.values()}
    assert fields == {"invariant_id", "tier", "passed", "reason"}


def test_adapters_do_not_mutate_domain_witness() -> None:
    """Adapters read; they do not mutate. Idempotent."""
    domain = assess_arrow_of_time(
        ObserverEntropyLedger(
            system_entropy_change_bits=1.0,
            observer_information_gain_bits=0.5,
        )
    )
    snapshot = (
        domain.is_arrow_consistent,
        domain.net_entropy_production_bits,
        domain.landauer_floor_cost_bits,
        domain.reason,
    )
    _ = normalize_arrow_witness(domain)
    _ = normalize_arrow_witness(domain)
    assert (
        domain.is_arrow_consistent,
        domain.net_entropy_production_bits,
        domain.landauer_floor_cost_bits,
        domain.reason,
    ) == snapshot


def test_normalized_witness_repr_contains_all_four_fields() -> None:
    """For logging/ledger consumers — repr must expose all protocol fields."""
    n = NormalizedInvariantWitness(
        invariant_id="INV-TEST",
        tier="ANCHORED",
        passed=True,
        reason=None,
    )
    r = repr(n)
    assert "invariant_id" in r
    assert "tier" in r
    assert "passed" in r
    assert "reason" in r
    assert math.isfinite(0.0)  # smoke: math import not unused
