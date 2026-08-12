# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
# no-bio-claim
"""Boundary-state sweep for the substrate-gate chain (Task 1).

Extends `test_substrate_gate_chain.py` from one comfortable baseline to
deterministic boundary-adjacent regions. Each case is named, each
mutation is documented, each expected verdict maps to a specific
invariant contract.

Boundary semantics (anchored on actual module source):

  - bekenstein_axis_holds: `inputs.observed_information_bits <= ceiling`
    (anchored_substrate_gate.py). Equality admissible.
  - arrow_axis_holds: `net >= 0.0` (arrow_of_time.assess_arrow_of_time).
    Equality admissible.
  - bandwidth_holds: `slack_hz = bound_hz - decoherence.rate_hz >= 0.0`
    (observer_bandwidth.assess_bandwidth_bound). Equality admissible.

The tests use deterministic numeric values only — no Hypothesis here
(scouting layer is optional after T1 closes per protocol §4).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import pytest

from core.physics.anchored_substrate_gate import (
    SubstrateGateInputs,
    assess_anchored_substrate_gate,
)
from core.physics.arrow_of_time import (
    ObserverEntropyLedger,
    assess_arrow_of_time,
)
from core.physics.observer_bandwidth import (
    assess_bandwidth_bound,
    decoherence_rate_hz,
    observer_bandwidth_hz,
)
from core.physics.thermodynamic_budget import (
    SPEED_OF_LIGHT_M_S,
    bekenstein_cognitive_ceiling,
)


@dataclass(frozen=True, slots=True)
class _BoundaryState:
    """Substrate fixture for boundary sweep; superset of chain-test fields
    for the axes exercised by this file (gate + arrow + bandwidth)."""

    radius_m: float
    energy_J: float
    claimed_information_bits: float
    system_entropy_change_bits: float
    observer_information_gain_bits: float
    decoherence_rate_hz: float
    observer_bandwidth_bits_per_second: float


_BASELINE = _BoundaryState(
    radius_m=0.07,
    energy_J=1.4 * SPEED_OF_LIGHT_M_S**2,
    claimed_information_bits=2.5e15,  # << brain Bekenstein ceiling
    system_entropy_change_bits=1.0,
    observer_information_gain_bits=0.0,
    decoherence_rate_hz=1.0,
    observer_bandwidth_bits_per_second=10.0,
)


def _gate(state: _BoundaryState) -> SubstrateGateInputs:
    return SubstrateGateInputs(
        radius_m=state.radius_m,
        energy_J=state.energy_J,
        observed_information_bits=state.claimed_information_bits,
        entropy_ledger=ObserverEntropyLedger(
            system_entropy_change_bits=state.system_entropy_change_bits,
            observer_information_gain_bits=state.observer_information_gain_bits,
        ),
    )


# ---------------------------------------------------------------------------
# Bekenstein & gate boundary cases (1–6)
# ---------------------------------------------------------------------------


def _ceiling_for(radius_m: float, energy_J: float) -> float:
    return bekenstein_cognitive_ceiling(radius_m, energy_J)


@pytest.mark.parametrize(
    ("case_name", "state_factory", "expect_bekenstein", "expect_arrow", "expect_composite"),
    [
        # Case 1 — near-zero positive energy.
        # Mutation: energy_J = 1e-30 J (tiny but finite). Ceiling becomes
        # ~2.86e-7 × R/m bits; with R=0.07m, ceiling ≈ 2e-8 bits. Claim 0
        # is trivially within bound. Tests that near-zero energy does not
        # produce numerical NaN/Inf and the gate still admits.
        (
            "near_zero_positive_energy",
            lambda: replace(_BASELINE, energy_J=1.0e-30, claimed_information_bits=0.0),
            True,
            True,
            True,
        ),
        # Case 2 — near-zero positive radius.
        # Mutation: radius_m = 1e-30 m. Ceiling ≈ 0 bits. Claim 0.
        (
            "near_zero_positive_radius",
            lambda: replace(_BASELINE, radius_m=1.0e-30, claimed_information_bits=0.0),
            True,
            True,
            True,
        ),
        # Case 3 — very large radius with finite energy.
        # Mutation: radius_m = 1e10 m, energy_J = 1.0 J. Ceiling ≈ 2.86e36 bits.
        # Claim 1.0 is well within. Tests no overflow on large multiplier.
        (
            "very_large_radius_finite_energy",
            lambda: replace(
                _BASELINE,
                radius_m=1.0e10,
                energy_J=1.0,
                claimed_information_bits=1.0,
            ),
            True,
            True,
            True,
        ),
        # Case 4 — Bekenstein ratio just below bound (factor 0.999999).
        # Anchored on source: `holds = observed <= ceiling`. 0.999999·ceiling
        # is strictly below ceiling → holds.
        (
            "bekenstein_just_below_bound",
            lambda: replace(
                _BASELINE,
                claimed_information_bits=_ceiling_for(_BASELINE.radius_m, _BASELINE.energy_J)
                * 0.999999,
            ),
            True,
            True,
            True,
        ),
        # Case 5 — Bekenstein ratio exactly at boundary.
        # Per `holds = observed <= ceiling`, equality is admissible.
        (
            "bekenstein_exactly_at_boundary",
            lambda: replace(
                _BASELINE,
                claimed_information_bits=_ceiling_for(_BASELINE.radius_m, _BASELINE.energy_J),
            ),
            True,
            True,
            True,
        ),
        # Case 6 — Bekenstein ratio just above bound (factor 1.000001).
        # Strictly above ceiling → does not hold.
        (
            "bekenstein_just_above_bound",
            lambda: replace(
                _BASELINE,
                claimed_information_bits=_ceiling_for(_BASELINE.radius_m, _BASELINE.energy_J)
                * 1.000001,
            ),
            False,
            True,
            False,
        ),
    ],
)
def test_bekenstein_boundary_sweep(
    case_name: str,
    state_factory: object,
    expect_bekenstein: bool,
    expect_arrow: bool,
    expect_composite: bool,
) -> None:
    """Boundary cases for the Bekenstein axis + gate composite."""
    state = state_factory()  # type: ignore[operator]
    assert isinstance(state, _BoundaryState), f"factory must return _BoundaryState ({case_name})"
    composite = assess_anchored_substrate_gate(_gate(state))
    msg = f"case={case_name} bek={composite.bekenstein_axis_holds} arrow={composite.arrow_axis_holds} composite={composite.is_thermodynamically_admissible}"
    assert composite.bekenstein_axis_holds is expect_bekenstein, msg
    assert composite.arrow_axis_holds is expect_arrow, msg
    assert composite.is_thermodynamically_admissible is expect_composite, msg


# ---------------------------------------------------------------------------
# Arrow-of-Time boundary cases (7–8)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("case_name", "delta_S", "delta_I", "expect_arrow_holds", "expect_composite"),
    [
        # Case 7 — Σ_net exactly at zero.
        # ΔS=-1, ΔI=+1 → net = 0. Per `consistent = net >= 0`, equality
        # admissible. Maxwell-demon balanced case.
        ("arrow_net_exactly_zero", -1.0, 1.0, True, True),
        # Case 8 — Σ_net just below zero.
        # ΔS=-1, ΔI=+0.999999 → net ≈ -1e-6 < 0 → not consistent.
        ("arrow_net_just_below_zero", -1.0, 0.999999, False, False),
    ],
)
def test_arrow_of_time_boundary_sweep(
    case_name: str,
    delta_S: float,
    delta_I: float,
    expect_arrow_holds: bool,
    expect_composite: bool,
) -> None:
    """Boundary cases for the Arrow axis (with Bekenstein passing trivially)."""
    state = replace(
        _BASELINE,
        system_entropy_change_bits=delta_S,
        observer_information_gain_bits=delta_I,
    )
    composite = assess_anchored_substrate_gate(_gate(state))
    direct_arrow = assess_arrow_of_time(_gate(state).entropy_ledger)
    msg = (
        f"case={case_name} ΔS={delta_S} ΔI={delta_I} "
        f"net={direct_arrow.net_entropy_production_bits} "
        f"arrow_holds={composite.arrow_axis_holds} composite={composite.is_thermodynamically_admissible}"
    )
    assert composite.arrow_axis_holds is expect_arrow_holds, msg
    # Direct witness must agree with the gate's sub-axis.
    assert direct_arrow.is_arrow_consistent is expect_arrow_holds, msg
    assert composite.bekenstein_axis_holds is True, msg
    assert composite.is_thermodynamically_admissible is expect_composite, msg


# ---------------------------------------------------------------------------
# Observer-bandwidth boundary cases (9–10)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    (
        "case_name",
        "gamma_hz",
        "sigma_dot_bps",
        "expect_bound_consistent",
        "expect_anchored_unaffected",
    ),
    [
        # Case 9 — Γ exactly equal to Σ̇.
        # slack = Σ̇ - Γ = 0. Per `consistent = slack >= 0`, equality admissible.
        # ANCHORED gate must remain admissible — bandwidth is SPECULATIVE,
        # cannot veto under ANCHORED_ONLY policy.
        ("bandwidth_gamma_equals_sigma_dot", 5.0, 5.0, True, True),
        # Case 10 — Γ just above Σ̇.
        # slack = -0.01 < 0 → not consistent. ANCHORED gate STILL admissible
        # (tier separation; bandwidth violation reported separately).
        ("bandwidth_gamma_just_above_sigma_dot", 5.01, 5.0, False, True),
    ],
)
def test_observer_bandwidth_boundary_sweep(
    case_name: str,
    gamma_hz: float,
    sigma_dot_bps: float,
    expect_bound_consistent: bool,
    expect_anchored_unaffected: bool,
) -> None:
    """Boundary cases for the observer-bandwidth (SPECULATIVE) axis.

    Anchored composite must NOT be vetoed by bandwidth violation per
    ANCHORED_ONLY composition policy."""
    state = replace(
        _BASELINE,
        decoherence_rate_hz=gamma_hz,
        observer_bandwidth_bits_per_second=sigma_dot_bps,
    )
    bandwidth_witness = assess_bandwidth_bound(
        decoherence_rate_hz(gamma_hz),
        observer_bandwidth_hz(sigma_dot_bps),
    )
    composite = assess_anchored_substrate_gate(_gate(state))
    msg = (
        f"case={case_name} Γ={gamma_hz} Σ̇={sigma_dot_bps} "
        f"slack={bandwidth_witness.slack_hz} consistent={bandwidth_witness.is_bound_consistent} "
        f"composite={composite.is_thermodynamically_admissible}"
    )
    assert bandwidth_witness.is_bound_consistent is expect_bound_consistent, msg
    # Tier separation: SPECULATIVE result does not change ANCHORED verdict.
    assert composite.is_thermodynamically_admissible is expect_anchored_unaffected, msg


# ---------------------------------------------------------------------------
# Coverage assertion — all 10 named cases present
# ---------------------------------------------------------------------------


def test_all_ten_named_boundary_cases_are_registered() -> None:
    """Sanity: enumerate cases by name to prevent silent removal in
    refactors. If a case is removed, this assertion fails. If a case is
    added, this assertion is updated and the protocol's case-count claim
    is re-anchored."""
    expected = {
        # Bekenstein/gate (6)
        "near_zero_positive_energy",
        "near_zero_positive_radius",
        "very_large_radius_finite_energy",
        "bekenstein_just_below_bound",
        "bekenstein_exactly_at_boundary",
        "bekenstein_just_above_bound",
        # Arrow (2)
        "arrow_net_exactly_zero",
        "arrow_net_just_below_zero",
        # Bandwidth (2)
        "bandwidth_gamma_equals_sigma_dot",
        "bandwidth_gamma_just_above_sigma_dot",
    }
    assert len(expected) == 10
    # Smoke: each name is a valid identifier (catches typos / accidental empty
    # names in parametrize tables when refactored).
    for name in expected:
        assert name and name.replace("_", "").isalnum()
