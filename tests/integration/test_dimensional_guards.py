# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
# no-bio-claim
"""Cross-module dimensional-guard integration test (Task 2).

Each runtime-evaluable physics entrypoint must reject invalid
dimensional inputs (NaN, Inf, negative values, malformed magnitudes)
BEFORE producing any admissibility, consistency, or budget claim.

Per-module unit tests already cover individual cases. This file is
the single integration table proving the policy holds across every
entrypoint without exception. Adds no helpers; uses real public APIs;
re-uses each module's existing ValueError contract.
"""

from __future__ import annotations

from typing import Callable

import pytest

from core.physics.anchored_substrate_gate import (
    SubstrateGateInputs,
    assess_anchored_substrate_gate,
)
from core.physics.arrow_of_time import (
    ObserverEntropyLedger,
    assess_arrow_of_time,
    landauer_floor_cost_bits,
)
from core.physics.cosmological_compute_bound import (
    CausalDiamond,
    assess_compute_claim,
    holographic_bit_capacity,
)
from core.physics.jacobson_observer_coherence import (
    ClausiusContext,
    clausius_residual,
)
from core.physics.observer_bandwidth import (
    decoherence_rate_hz,
    observer_bandwidth_hz,
)
from core.physics.thermodynamic_budget import bekenstein_cognitive_ceiling

NAN = float("nan")
POS_INF = float("inf")
NEG_INF = float("-inf")


# ---------------------------------------------------------------------------
# Bekenstein ceiling — radius_m and energy_J
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("case_name", "thunk"),
    [
        # radius_m — finite + non-negative; zero is admissible (returns 0).
        ("bekenstein_negative_radius", lambda: bekenstein_cognitive_ceiling(-1.0, 1.0)),
        ("bekenstein_nan_radius", lambda: bekenstein_cognitive_ceiling(NAN, 1.0)),
        ("bekenstein_pos_inf_radius", lambda: bekenstein_cognitive_ceiling(POS_INF, 1.0)),
        ("bekenstein_neg_inf_radius", lambda: bekenstein_cognitive_ceiling(NEG_INF, 1.0)),
        # energy_J — finite + non-negative; zero admissible (returns 0).
        ("bekenstein_negative_energy", lambda: bekenstein_cognitive_ceiling(1.0, -1.0)),
        ("bekenstein_nan_energy", lambda: bekenstein_cognitive_ceiling(1.0, NAN)),
        ("bekenstein_pos_inf_energy", lambda: bekenstein_cognitive_ceiling(1.0, POS_INF)),
        ("bekenstein_neg_inf_energy", lambda: bekenstein_cognitive_ceiling(1.0, NEG_INF)),
    ],
)
def test_bekenstein_rejects_invalid_dimensional_inputs(
    case_name: str, thunk: Callable[[], float]
) -> None:
    with pytest.raises(ValueError):
        thunk()


# ---------------------------------------------------------------------------
# Holographic bit capacity (cosmological compute) — area_m2
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("case_name", "thunk"),
    [
        ("holographic_negative_area", lambda: holographic_bit_capacity(-1.0)),
        ("holographic_nan_area", lambda: holographic_bit_capacity(NAN)),
        ("holographic_pos_inf_area", lambda: holographic_bit_capacity(POS_INF)),
        ("holographic_neg_inf_area", lambda: holographic_bit_capacity(NEG_INF)),
    ],
)
def test_holographic_capacity_rejects_invalid_area(
    case_name: str, thunk: Callable[[], float]
) -> None:
    with pytest.raises(ValueError):
        thunk()


# ---------------------------------------------------------------------------
# Cosmological compute claim — claimed_bits + diamond area
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("case_name", "thunk"),
    [
        # Negative or non-finite claimed_bits.
        (
            "compute_claim_negative_bits",
            lambda: assess_compute_claim(CausalDiamond(horizon_area_m2=1.0), -1.0),
        ),
        (
            "compute_claim_nan_bits",
            lambda: assess_compute_claim(CausalDiamond(horizon_area_m2=1.0), NAN),
        ),
        (
            "compute_claim_pos_inf_bits",
            lambda: assess_compute_claim(CausalDiamond(horizon_area_m2=1.0), POS_INF),
        ),
        # Diamond area is validated by holographic helper.
        (
            "compute_claim_negative_area",
            lambda: assess_compute_claim(CausalDiamond(horizon_area_m2=-1.0), 0.0),
        ),
        (
            "compute_claim_nan_area",
            lambda: assess_compute_claim(CausalDiamond(horizon_area_m2=NAN), 0.0),
        ),
    ],
)
def test_compute_claim_rejects_invalid_inputs(case_name: str, thunk: Callable[[], object]) -> None:
    with pytest.raises(ValueError):
        thunk()


# ---------------------------------------------------------------------------
# Observer bandwidth — Γ and Σ̇ constructors
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("case_name", "thunk"),
    [
        ("decoherence_negative_rate", lambda: decoherence_rate_hz(-1.0)),
        ("decoherence_nan_rate", lambda: decoherence_rate_hz(NAN)),
        ("decoherence_pos_inf_rate", lambda: decoherence_rate_hz(POS_INF)),
        ("bandwidth_negative_bps", lambda: observer_bandwidth_hz(-1.0)),
        ("bandwidth_nan_bps", lambda: observer_bandwidth_hz(NAN)),
        ("bandwidth_pos_inf_bps", lambda: observer_bandwidth_hz(POS_INF)),
    ],
)
def test_observer_bandwidth_rejects_invalid_inputs(
    case_name: str, thunk: Callable[[], object]
) -> None:
    with pytest.raises(ValueError):
        thunk()


# ---------------------------------------------------------------------------
# Arrow of time — ledger inputs (via Landauer helper + assessor)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("case_name", "thunk"),
    [
        # Landauer floor — non-negative info gain only.
        ("landauer_negative_info_gain", lambda: landauer_floor_cost_bits(-1.0)),
        ("landauer_nan_info_gain", lambda: landauer_floor_cost_bits(NAN)),
        ("landauer_pos_inf_info_gain", lambda: landauer_floor_cost_bits(POS_INF)),
        # System entropy change — finite required.
        (
            "arrow_nan_system_entropy",
            lambda: assess_arrow_of_time(
                ObserverEntropyLedger(
                    system_entropy_change_bits=NAN,
                    observer_information_gain_bits=0.0,
                )
            ),
        ),
        (
            "arrow_pos_inf_system_entropy",
            lambda: assess_arrow_of_time(
                ObserverEntropyLedger(
                    system_entropy_change_bits=POS_INF,
                    observer_information_gain_bits=0.0,
                )
            ),
        ),
        (
            "arrow_neg_inf_system_entropy",
            lambda: assess_arrow_of_time(
                ObserverEntropyLedger(
                    system_entropy_change_bits=NEG_INF,
                    observer_information_gain_bits=0.0,
                )
            ),
        ),
    ],
)
def test_arrow_of_time_rejects_invalid_inputs(case_name: str, thunk: Callable[[], object]) -> None:
    with pytest.raises(ValueError):
        thunk()


# ---------------------------------------------------------------------------
# Jacobson observer-coherence — Clausius context fields
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("case_name", "thunk"),
    [
        # Non-finite heat flow.
        (
            "jacobson_nan_heat_flow",
            lambda: clausius_residual(
                ClausiusContext(
                    heat_flow_J=NAN,
                    unruh_temperature_K=2.0,
                    entropy_change_J_per_K=5.0,
                )
            ),
        ),
        (
            "jacobson_pos_inf_heat_flow",
            lambda: clausius_residual(
                ClausiusContext(
                    heat_flow_J=POS_INF,
                    unruh_temperature_K=2.0,
                    entropy_change_J_per_K=5.0,
                )
            ),
        ),
        # Negative Unruh temperature unphysical.
        (
            "jacobson_negative_unruh_temperature",
            lambda: clausius_residual(
                ClausiusContext(
                    heat_flow_J=10.0,
                    unruh_temperature_K=-1.0,
                    entropy_change_J_per_K=5.0,
                )
            ),
        ),
        (
            "jacobson_nan_unruh_temperature",
            lambda: clausius_residual(
                ClausiusContext(
                    heat_flow_J=10.0,
                    unruh_temperature_K=NAN,
                    entropy_change_J_per_K=5.0,
                )
            ),
        ),
        # Non-finite entropy change.
        (
            "jacobson_nan_entropy_change",
            lambda: clausius_residual(
                ClausiusContext(
                    heat_flow_J=10.0,
                    unruh_temperature_K=2.0,
                    entropy_change_J_per_K=NAN,
                )
            ),
        ),
        # Non-finite observer-coherence correction.
        (
            "jacobson_nan_observer_correction",
            lambda: clausius_residual(
                ClausiusContext(
                    heat_flow_J=10.0,
                    unruh_temperature_K=2.0,
                    entropy_change_J_per_K=5.0,
                    observer_coherence_correction_J=NAN,
                )
            ),
        ),
    ],
)
def test_jacobson_rejects_invalid_inputs(case_name: str, thunk: Callable[[], object]) -> None:
    with pytest.raises(ValueError):
        thunk()


# ---------------------------------------------------------------------------
# Anchored substrate gate — inputs validation pre-state-mutation
# ---------------------------------------------------------------------------


def _ledger(dS: float = 0.0, dI: float = 0.0) -> ObserverEntropyLedger:
    return ObserverEntropyLedger(
        system_entropy_change_bits=dS,
        observer_information_gain_bits=dI,
    )


@pytest.mark.parametrize(
    ("case_name", "thunk"),
    [
        # Negative claimed_bits.
        (
            "gate_negative_claimed_bits",
            lambda: assess_anchored_substrate_gate(
                SubstrateGateInputs(
                    radius_m=1.0,
                    energy_J=1.0,
                    observed_information_bits=-1.0,
                    entropy_ledger=_ledger(),
                )
            ),
        ),
        # Non-finite claimed_bits.
        (
            "gate_nan_claimed_bits",
            lambda: assess_anchored_substrate_gate(
                SubstrateGateInputs(
                    radius_m=1.0,
                    energy_J=1.0,
                    observed_information_bits=NAN,
                    entropy_ledger=_ledger(),
                )
            ),
        ),
        (
            "gate_pos_inf_claimed_bits",
            lambda: assess_anchored_substrate_gate(
                SubstrateGateInputs(
                    radius_m=1.0,
                    energy_J=1.0,
                    observed_information_bits=POS_INF,
                    entropy_ledger=_ledger(),
                )
            ),
        ),
        # Invalid radius/energy delegated to bekenstein helper.
        (
            "gate_negative_radius",
            lambda: assess_anchored_substrate_gate(
                SubstrateGateInputs(
                    radius_m=-1.0,
                    energy_J=1.0,
                    observed_information_bits=0.0,
                    entropy_ledger=_ledger(),
                )
            ),
        ),
        (
            "gate_nan_energy",
            lambda: assess_anchored_substrate_gate(
                SubstrateGateInputs(
                    radius_m=1.0,
                    energy_J=NAN,
                    observed_information_bits=0.0,
                    entropy_ledger=_ledger(),
                )
            ),
        ),
        # Invalid ledger entries delegated to arrow assessor.
        (
            "gate_nan_system_entropy",
            lambda: assess_anchored_substrate_gate(
                SubstrateGateInputs(
                    radius_m=1.0,
                    energy_J=1.0,
                    observed_information_bits=0.0,
                    entropy_ledger=_ledger(dS=NAN),
                )
            ),
        ),
    ],
)
def test_anchored_gate_rejects_invalid_inputs_before_state_claim(
    case_name: str, thunk: Callable[[], object]
) -> None:
    """The gate must raise ValueError BEFORE producing any
    admissibility claim — invalid dimension cannot mutate state into
    a witness object."""
    with pytest.raises(ValueError):
        thunk()
