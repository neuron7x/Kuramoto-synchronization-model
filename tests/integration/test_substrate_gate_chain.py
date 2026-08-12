# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
# no-bio-claim
"""Substrate-gate chain integration test.

Composes the seven runtime-evaluable physics-invariant modules from this
session against a single deterministic synthetic substrate state, and
proves their verdicts are non-contradictory.

Tier mapping (anchored from each module's PROVENANCE_TIER):

  ANCHORED:
    - core.physics.arrow_of_time
    - core.physics.anchored_substrate_gate (composite)
    - bekenstein_cognitive_ceiling (function in core.physics.thermodynamic_budget;
      registered ANCHORED via INV-BEKENSTEIN-COGNITIVE in INVARIANTS.yaml)

  EXTRAPOLATED:
    - core.physics.jacobson_observer_coherence
    - core.physics.cosmological_compute_bound

  SPECULATIVE:
    - core.physics.observer_bandwidth (downgraded in PR #421)

  REGISTRY-ONLY (point-eval, not state-eval):
    - core.physics.simulation_falsification — `FalsificationLadder` is a
      pre-registered signature catalog. `hardware_class_ruled_out(id, value)`
      is runtime-evaluable per signature, but no single substrate state
      naturally maps to all six signatures. Exercised by registry-shape
      assertions only.

Failure-axis identifiers in the anchored composite are the literal
strings "BEKENSTEIN" and "ARROW" (per
core/physics/anchored_substrate_gate.py:144 — stable ordering when both
fail: ("BEKENSTEIN", "ARROW")).

Test scope: composition behavior. NOT unit-style smoke. Each scenario
mutates exactly one field of the baseline substrate, except scenario 4
which intentionally violates two anchored axes to assert deterministic
multi-failure ordering.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from core.physics.anchored_substrate_gate import (
    PROVENANCE_TIER as ANCHORED_GATE_TIER,
)
from core.physics.anchored_substrate_gate import (
    SubstrateGateInputs,
    assess_anchored_substrate_gate,
)
from core.physics.arrow_of_time import (
    PROVENANCE_TIER as ARROW_TIER,
)
from core.physics.arrow_of_time import (
    ObserverEntropyLedger,
    assess_arrow_of_time,
)
from core.physics.cosmological_compute_bound import (
    PROVENANCE_TIER as COSMOLOGICAL_TIER,
)
from core.physics.cosmological_compute_bound import (
    CausalDiamond,
    assess_compute_claim,
)
from core.physics.jacobson_observer_coherence import (
    PROVENANCE_TIER as JACOBSON_TIER,
)
from core.physics.jacobson_observer_coherence import (
    ClausiusContext,
    assess_jacobson_observer,
)
from core.physics.observer_bandwidth import (
    PROVENANCE_TIER as BANDWIDTH_TIER,
)
from core.physics.observer_bandwidth import (
    assess_bandwidth_bound,
    decoherence_rate_hz,
    observer_bandwidth_hz,
)
from core.physics.simulation_falsification import (
    FalsificationLadder,
    ObservationStatus,
    build_canonical_ladder,
)
from core.physics.thermodynamic_budget import (
    SPEED_OF_LIGHT_M_S,
    bekenstein_cognitive_ceiling,
)


@dataclass(frozen=True, slots=True)
class SubstrateState:
    """One deterministic synthetic substrate fixture driving every axis.

    Field semantics:
      - radius_m, mass_kg → spatial extent + rest mass; Bekenstein input
        is (R, E) where E = m·c².
      - claimed_information_bits → information content compared against
        Bekenstein ceiling.
      - system_entropy_change_bits, observer_information_gain_bits →
        Arrow-of-Time ledger inputs.
      - decoherence_rate_hz, observer_bandwidth_bits_per_second →
        observer-bandwidth comparison Γ ≤ Σ̇ (1 bit/s ↔ 1 Hz ansatz per
        the SPECULATIVE-tier docstring).
      - causal_diamond_area_m2, compute_claim_bits → cosmological compute
        bound (Bekenstein-Hawking on horizon area).
      - heat_flow_J, unruh_temperature_K, entropy_change_J_per_K,
        observer_coherence_correction_J → Jacobson Clausius residual
        δQ − T·dS − c.
    """

    radius_m: float
    mass_kg: float
    claimed_information_bits: float
    system_entropy_change_bits: float
    observer_information_gain_bits: float
    decoherence_rate_hz: float
    observer_bandwidth_bits_per_second: float
    causal_diamond_area_m2: float
    compute_claim_bits: float
    heat_flow_J: float
    unruh_temperature_K: float
    entropy_change_J_per_K: float
    observer_coherence_correction_J: float

    @property
    def energy_J(self) -> float:
        return self.mass_kg * SPEED_OF_LIGHT_M_S**2


# Baseline values are chosen to lie comfortably inside every bound.
# Brain-scale spatial/mass numbers picked because Bekenstein margin scan
# (spikes/bekenstein_margin_scan.py, PR #420) used the same scale.
#
# Why each baseline value is safely inside its bound:
#   - Bekenstein:   I_max(R=0.07m, E=1.4·c²·J) ≈ 2.5e42 bits;
#                   claim 2.5e15 → margin ~1e-27, ~27 OOM headroom.
#   - Arrow:        ΔS=+1, ΔI=0 → Σ_net = +1 ≥ 0; standard 2nd law.
#   - Bandwidth:    Γ=1 Hz, Σ̇=10 bit/s → slack +9; passes.
#   - Cosmological: horizon area for sphere of R=0.07m is 4πR² ≈ 0.0616 m²;
#                   I_max ≈ A/(4·ℓp²·ln 2) ≈ 8e67 bits; claim 1e30 << bound.
#   - Jacobson:     δQ=10 J, T=2 K, dS=5 J/K → δQ − T·dS = 0; pure
#                   Jacobson holds. c=0 → extended residual = 0 ≤ default
#                   tolerance 1e-30 J.
_BASELINE: SubstrateState = SubstrateState(
    radius_m=0.07,
    mass_kg=1.4,
    claimed_information_bits=2.5e15,
    system_entropy_change_bits=1.0,
    observer_information_gain_bits=0.0,
    decoherence_rate_hz=1.0,
    observer_bandwidth_bits_per_second=10.0,
    causal_diamond_area_m2=4.0 * math.pi * 0.07**2,
    compute_claim_bits=1.0e30,
    heat_flow_J=10.0,
    unruh_temperature_K=2.0,
    entropy_change_J_per_K=5.0,
    observer_coherence_correction_J=0.0,
)


def _build_anchored_inputs(state: SubstrateState) -> SubstrateGateInputs:
    return SubstrateGateInputs(
        radius_m=state.radius_m,
        energy_J=state.energy_J,
        observed_information_bits=state.claimed_information_bits,
        entropy_ledger=ObserverEntropyLedger(
            system_entropy_change_bits=state.system_entropy_change_bits,
            observer_information_gain_bits=state.observer_information_gain_bits,
        ),
    )


def _evaluate_extrapolated_axes(state: SubstrateState) -> dict[str, object]:
    """Evaluate every EXTRAPOLATED + SPECULATIVE axis on the same state.

    Returns a dict keyed by tier+axis name. Each value is the witness
    object from the corresponding module — no string conversion, no
    coercion, full witness preserved for downstream assertions.
    """
    bandwidth_witness = assess_bandwidth_bound(
        decoherence_rate_hz(state.decoherence_rate_hz),
        observer_bandwidth_hz(state.observer_bandwidth_bits_per_second),
    )
    cosmological_witness = assess_compute_claim(
        CausalDiamond(horizon_area_m2=state.causal_diamond_area_m2),
        state.compute_claim_bits,
    )
    jacobson_witness = assess_jacobson_observer(
        ClausiusContext(
            heat_flow_J=state.heat_flow_J,
            unruh_temperature_K=state.unruh_temperature_K,
            entropy_change_J_per_K=state.entropy_change_J_per_K,
            observer_coherence_correction_J=state.observer_coherence_correction_J,
        )
    )
    return {
        "SPECULATIVE.observer_bandwidth": bandwidth_witness,
        "EXTRAPOLATED.cosmological_compute": cosmological_witness,
        "EXTRAPOLATED.jacobson_observer": jacobson_witness,
    }


# ---------------------------------------------------------------------------
# Scenario 1 — admissible baseline
# ---------------------------------------------------------------------------


def test_substrate_gate_chain_admissible_baseline() -> None:
    """All ANCHORED axes pass; composite admissible; EXTRAPOLATED+SPECULATIVE
    axes also pass at baseline values (chosen safely inside every bound)."""
    inputs = _build_anchored_inputs(_BASELINE)
    composite = assess_anchored_substrate_gate(inputs)

    assert composite.bekenstein_axis_holds is True
    assert composite.arrow_axis_holds is True
    assert composite.is_thermodynamically_admissible is True
    assert composite.failure_axes == ()
    assert composite.reason is None

    # Tier sanity — module-declared tiers must match registry expectations.
    assert ANCHORED_GATE_TIER == "ANCHORED"
    assert ARROW_TIER == "ANCHORED"

    # EXTRAPOLATED + SPECULATIVE: at baseline values they pass independently;
    # the composite verdict above does not consume them.
    extra = _evaluate_extrapolated_axes(_BASELINE)
    assert extra["SPECULATIVE.observer_bandwidth"].is_bound_consistent is True  # type: ignore[attr-defined]
    assert extra["EXTRAPOLATED.cosmological_compute"].is_within_budget is True  # type: ignore[attr-defined]
    jacobson = extra["EXTRAPOLATED.jacobson_observer"]
    assert jacobson.is_pure_jacobson_consistent is True  # type: ignore[attr-defined]
    assert jacobson.is_extended_consistent is True  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Scenario 2 — Bekenstein violation only
# ---------------------------------------------------------------------------


def test_substrate_gate_chain_bekenstein_violation_is_named() -> None:
    """Bekenstein ceiling violated ⇒ composite inadmissible, BEKENSTEIN named,
    Arrow remains passing (single-field mutation)."""
    state = replace(_BASELINE, claimed_information_bits=1.0e60)
    inputs = _build_anchored_inputs(state)
    composite = assess_anchored_substrate_gate(inputs)

    assert composite.bekenstein_axis_holds is False
    assert composite.arrow_axis_holds is True
    assert composite.is_thermodynamically_admissible is False
    assert "BEKENSTEIN" in composite.failure_axes
    assert "ARROW" not in composite.failure_axes
    assert composite.reason is not None
    assert "INV-BEKENSTEIN-COGNITIVE" in composite.reason


# ---------------------------------------------------------------------------
# Scenario 3 — Arrow-of-Time violation only
# ---------------------------------------------------------------------------


def test_substrate_gate_chain_arrow_violation_is_named() -> None:
    """ΔS_system = -2 bits with ΔI_observer = 0 ⇒ Σ_net = -2 < 0 ⇒
    Arrow fails; composite inadmissible; ARROW named; Bekenstein still passes."""
    state = replace(
        _BASELINE,
        system_entropy_change_bits=-2.0,
        observer_information_gain_bits=0.0,
    )
    inputs = _build_anchored_inputs(state)
    composite = assess_anchored_substrate_gate(inputs)

    assert composite.bekenstein_axis_holds is True
    assert composite.arrow_axis_holds is False
    assert composite.is_thermodynamically_admissible is False
    assert "ARROW" in composite.failure_axes
    assert "BEKENSTEIN" not in composite.failure_axes
    assert composite.reason is not None
    assert "INV-ARROW-OF-TIME" in composite.reason


# ---------------------------------------------------------------------------
# Scenario 4 — both ANCHORED axes fail; deterministic ordering
# ---------------------------------------------------------------------------


def test_substrate_gate_chain_reports_multiple_anchored_failures_deterministically() -> None:
    """Both Bekenstein and Arrow violated; composite reports both failures
    in stable order BEKENSTEIN then ARROW (per module impl line ~144).
    Reason mentions both INV-* IDs."""
    state = replace(
        _BASELINE,
        claimed_information_bits=1.0e60,
        system_entropy_change_bits=-2.0,
        observer_information_gain_bits=0.0,
    )
    inputs = _build_anchored_inputs(state)
    composite = assess_anchored_substrate_gate(inputs)

    assert composite.bekenstein_axis_holds is False
    assert composite.arrow_axis_holds is False
    assert composite.is_thermodynamically_admissible is False
    # Stable ordering — module always appends BEKENSTEIN before ARROW.
    assert composite.failure_axes == ("BEKENSTEIN", "ARROW")
    assert composite.reason is not None
    assert "INV-BEKENSTEIN-COGNITIVE" in composite.reason
    assert "INV-ARROW-OF-TIME" in composite.reason


# ---------------------------------------------------------------------------
# Scenario 5 — EXTRAPOLATED/SPECULATIVE violation must not veto ANCHORED gate
# ---------------------------------------------------------------------------


def test_extrapolated_violation_does_not_veto_anchored_gate() -> None:
    """SPECULATIVE observer-bandwidth violated (Γ > Σ̇) while ANCHORED axes
    pass; composite remains admissible. Tier separation explicit:
    bandwidth result reported separately, never silently mutates the
    composite verdict."""
    state = replace(
        _BASELINE,
        decoherence_rate_hz=100.0,
        observer_bandwidth_bits_per_second=1.0,
    )
    inputs = _build_anchored_inputs(state)
    composite = assess_anchored_substrate_gate(inputs)

    # ANCHORED: still admissible.
    assert composite.bekenstein_axis_holds is True
    assert composite.arrow_axis_holds is True
    assert composite.is_thermodynamically_admissible is True
    assert composite.failure_axes == ()

    # SPECULATIVE: bandwidth axis flags violation independently.
    bandwidth_witness = assess_bandwidth_bound(
        decoherence_rate_hz(state.decoherence_rate_hz),
        observer_bandwidth_hz(state.observer_bandwidth_bits_per_second),
    )
    assert bandwidth_witness.is_bound_consistent is False
    assert bandwidth_witness.slack_hz < 0.0
    assert bandwidth_witness.reason is not None
    assert "INV-OBSERVER-BANDWIDTH" in bandwidth_witness.reason
    assert BANDWIDTH_TIER == "SPECULATIVE"


# ---------------------------------------------------------------------------
# Scenario 6 — same-state consistency across all runtime-evaluable axes
# ---------------------------------------------------------------------------


def test_all_invariants_share_consistent_substrate_semantics() -> None:
    """Every runtime-evaluable invariant module receives the same baseline
    substrate state and produces a finite, sensible witness. Tier metadata
    matches registry. Simulation-falsification is REGISTRY-ONLY (no
    state-eval mapping); exercised by ladder shape only."""

    inputs = _build_anchored_inputs(_BASELINE)
    composite = assess_anchored_substrate_gate(inputs)
    arrow_witness = assess_arrow_of_time(inputs.entropy_ledger)
    extra = _evaluate_extrapolated_axes(_BASELINE)

    # Anchored: composite admissible, sub-axes pass.
    assert composite.is_thermodynamically_admissible is True
    assert math.isfinite(composite.bekenstein_ceiling_bits)

    # Arrow witness independent of composite — same state semantics.
    assert arrow_witness.is_arrow_consistent is True
    assert arrow_witness.net_entropy_production_bits == 1.0
    assert arrow_witness.is_arrow_consistent is composite.arrow_axis_holds

    # Bekenstein direct invocation matches the gate's ceiling.
    direct_ceiling = bekenstein_cognitive_ceiling(_BASELINE.radius_m, _BASELINE.energy_J)
    assert direct_ceiling == composite.bekenstein_ceiling_bits

    # EXTRAPOLATED axes: pass at baseline; finite values.
    cosmo = extra["EXTRAPOLATED.cosmological_compute"]
    assert cosmo.is_within_budget is True  # type: ignore[attr-defined]
    assert math.isfinite(cosmo.budget.holographic_max_bits)  # type: ignore[attr-defined]
    assert math.isfinite(cosmo.margin_bits)  # type: ignore[attr-defined]

    jacobson = extra["EXTRAPOLATED.jacobson_observer"]
    assert math.isfinite(jacobson.pure_jacobson_residual_J)  # type: ignore[attr-defined]
    assert math.isfinite(jacobson.observer_extended_residual_J)  # type: ignore[attr-defined]

    # SPECULATIVE: bandwidth.
    bandwidth = extra["SPECULATIVE.observer_bandwidth"]
    assert bandwidth.is_bound_consistent is True  # type: ignore[attr-defined]
    assert math.isfinite(bandwidth.slack_hz)  # type: ignore[attr-defined]

    # Tier metadata cross-check (no module mislabels its own tier).
    assert ANCHORED_GATE_TIER == "ANCHORED"
    assert ARROW_TIER == "ANCHORED"
    assert COSMOLOGICAL_TIER == "EXTRAPOLATED"
    assert JACOBSON_TIER == "EXTRAPOLATED"
    assert BANDWIDTH_TIER == "SPECULATIVE"

    # Registry-only: simulation-falsification has no state-eval; exercised
    # by ladder shape and per-signature reasoning_tier.
    ladder: FalsificationLadder = build_canonical_ladder()
    assert len(ladder.signatures) == 6
    valid_status = {s.value for s in ObservationStatus}
    valid_reasoning = {"DERIVED", "ANALOGICAL"}
    for sig in ladder.signatures:
        assert sig.current_observation_status.value in valid_status
        assert sig.reasoning_tier in valid_reasoning
    by_tier = ladder.signatures_by_tier()
    assert sum(len(v) for v in by_tier.values()) == 6
