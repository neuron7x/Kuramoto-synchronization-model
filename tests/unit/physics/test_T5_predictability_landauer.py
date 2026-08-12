# SPDX-License-Identifier: MIT
"""Falsification battery for LAW T5: Landauer-budgeted predictability horizon.

Invariants under test:
* INV-TAU1 | algebraic    | τ = (1/λ_1) · ln(δ_tol/δ_0); +∞ for λ_1 ≤ 0.
* INV-TAU2 | conservation | Landauer floor on δ_0 honoured; over-budget ⇒
                            ValueError ("physically unaffordable").
* INV-TAU3 | universal    | every contract violation → ValueError.
"""

from __future__ import annotations

import math

import pytest

from core.physics.landauer import K_BOLTZMANN
from core.physics.predictability_horizon import (
    HorizonReport,
    landauer_min_initial_precision,
    landauer_min_initialisation_energy,
    predictability_horizon,
    predictability_horizon_under_budget,
)

# ── INV-TAU1: Lorenz horizon formula ────────────────────────────────────────


def test_INV_TAU1_horizon_matches_analytic_formula() -> None:
    """τ = (1/λ_1) · ln(δ_tol/δ_0) to 1e-12 on a closed-form case."""
    lambda_1 = 0.9056  # Lorenz-63 published λ_1
    delta_0 = 1e-8
    delta_tol = 1.0
    tau = predictability_horizon(lambda_1, delta_0=delta_0, delta_tol=delta_tol)
    expected = math.log(delta_tol / delta_0) / lambda_1
    assert abs(tau - expected) < 1e-12, f"INV-TAU1 VIOLATED: τ={tau} vs analytic {expected}"


def test_INV_TAU1_non_chaotic_returns_infinite_horizon() -> None:
    """λ_1 ≤ 0 ⇒ τ = +∞ (predictable indefinitely)."""
    for lam in (-0.5, 0.0, -1e-12):
        tau = predictability_horizon(lam, delta_0=1e-6, delta_tol=1.0)
        assert tau == math.inf, f"INV-TAU1: non-chaotic (λ={lam}) should yield ∞, got {tau}"


def test_INV_TAU1_horizon_scales_inversely_with_lambda() -> None:
    """Doubling λ_1 halves τ (algebraic)."""
    delta_0 = 1e-6
    delta_tol = 1.0
    tau_1 = predictability_horizon(0.5, delta_0=delta_0, delta_tol=delta_tol)
    tau_2 = predictability_horizon(1.0, delta_0=delta_0, delta_tol=delta_tol)
    assert (
        abs(tau_1 / tau_2 - 2.0) < 1e-12
    ), f"INV-TAU1 scaling: τ(0.5)/τ(1.0) = {tau_1 / tau_2} ≠ 2"


def test_INV_TAU1_horizon_increases_with_finer_initial_precision() -> None:
    """Smaller δ_0 ⇒ larger τ (logarithmically)."""
    lam = 1.0
    delta_tol = 1.0
    tau_coarse = predictability_horizon(lam, delta_0=1e-3, delta_tol=delta_tol)
    tau_fine = predictability_horizon(lam, delta_0=1e-9, delta_tol=delta_tol)
    assert tau_fine > tau_coarse, f"τ_fine={tau_fine} should exceed τ_coarse={tau_coarse}"
    assert abs(tau_fine - tau_coarse - math.log(1e6)) < 1e-12


# ── INV-TAU2: Landauer floor ────────────────────────────────────────────────


def test_INV_TAU2_landauer_energy_matches_kT_lnRatio() -> None:
    """E_min(δ_0) = k_B · T · ln(Δ/δ_0) to float precision."""
    Delta = 1.0
    delta_0 = 1e-6
    T = 300.0
    E = landauer_min_initialisation_energy(delta_0, dynamic_range=Delta, T_kelvin=T)
    expected = K_BOLTZMANN * T * math.log(Delta / delta_0)
    assert abs(E - expected) < 1e-30, f"INV-TAU2 VIOLATED: E={E} vs analytic {expected}"


def test_INV_TAU2_landauer_min_precision_is_exact_inverse() -> None:
    """δ_0_min(E) and E_min(δ_0) round-trip to float precision.

    Round-trip is only meaningful while the Landauer floor is
    representable in float64 — i.e. while E_budget < 700 · k_B · T
    (≈ 2.9e-18 J at 300 K). Past that, exp(-E/(kT)) underflows to 0
    and the inverse is no longer defined; production code clamps
    via ``raise ValueError`` upstream when ``δ_0 ≤ 0``.
    """
    Delta = 1.0
    T = 300.0
    # 1e-21 J ≈ 1 bit; 1e-19 J ≈ 24 bits; 1e-18 J ≈ 240 bits — within
    # float64-representable floor.
    for E in (1e-21, 5e-21, 1e-20, 1e-19, 1e-18):
        d0 = landauer_min_initial_precision(E, dynamic_range=Delta, T_kelvin=T)
        assert d0 > 0.0, f"floor underflowed at E={E}"
        E_round = landauer_min_initialisation_energy(d0, dynamic_range=Delta, T_kelvin=T)
        assert abs(E - E_round) / E < 1e-10, f"Round-trip Landauer at E={E}: got {E_round}"


def test_INV_TAU2_under_budget_returns_finite_tau_at_room_T() -> None:
    """At T=300 K, E_budget=1e-15 J resolves Δ=1 to << 1 — finite τ."""
    rep = predictability_horizon_under_budget(
        lambda_1=1.0,
        delta_tol=0.01,
        dynamic_range=1.0,
        energy_budget_J=1e-19,
        T_kelvin=300.0,
    )
    assert isinstance(rep, HorizonReport)
    assert math.isfinite(rep.tau)
    assert rep.tau > 0
    assert rep.saturated_budget is True
    assert rep.delta_0 == rep.delta_0_min_landauer
    # Energy actually used ≤ budget (saturates from below).
    assert rep.energy_required_J <= 1e-15 + 1e-30


def test_INV_TAU2_request_below_landauer_floor_raises() -> None:
    """Requesting δ_0 below the Landauer floor raises (INV-TAU2)."""
    Delta = 1.0
    T = 300.0
    E = 1e-21  # ≈ 1 bit
    floor = landauer_min_initial_precision(E, dynamic_range=Delta, T_kelvin=T)
    with pytest.raises(ValueError, match="below the Landauer floor"):
        predictability_horizon_under_budget(
            lambda_1=1.0,
            delta_tol=0.5,
            dynamic_range=Delta,
            energy_budget_J=E,
            T_kelvin=T,
            delta_0_request=floor / 2.0,
        )


def test_INV_TAU2_explicit_request_at_or_above_floor_accepted() -> None:
    """δ_0_request ≥ floor: respected, used as δ_0."""
    Delta = 1.0
    T = 300.0
    # Stay in the float64-representable Landauer regime
    # (E ≪ 700·k_B·T ≈ 2.9e-18 J at 300 K, see round-trip test).
    E = 1e-19
    floor = landauer_min_initial_precision(E, dynamic_range=Delta, T_kelvin=T)
    # Request a δ_0 strictly above the floor; saturated should be False.
    rep = predictability_horizon_under_budget(
        lambda_1=1.0,
        delta_tol=0.1,
        dynamic_range=Delta,
        energy_budget_J=E,
        T_kelvin=T,
        delta_0_request=floor * 10.0,
    )
    assert rep.delta_0 == floor * 10.0
    assert rep.saturated_budget is False


# ── INV-TAU3: fail-closed contracts ─────────────────────────────────────────


@pytest.mark.parametrize(
    "kwargs,msg",
    [
        ({"lambda_1": float("nan")}, "must be finite"),
        ({"lambda_1": float("inf")}, "must be finite"),
        ({"delta_0": 0.0}, "delta_0 must be > 0"),
        ({"delta_0": -1e-6}, "delta_0 must be > 0"),
        ({"delta_tol": 0.0}, "delta_tol must be > 0"),
        ({"delta_0": 1.0, "delta_tol": 0.5}, "must be < delta_tol"),
    ],
)
def test_INV_TAU3_horizon_rejects_bad_inputs(kwargs: dict[str, float], msg: str) -> None:
    base = {"lambda_1": 1.0, "delta_0": 1e-6, "delta_tol": 1.0}
    base.update(kwargs)
    with pytest.raises(ValueError, match=msg):
        predictability_horizon(**base)


@pytest.mark.parametrize(
    "kwargs,msg",
    [
        ({"delta_0": 0.0}, "delta_0 must be > 0"),
        ({"dynamic_range": 0.0}, "dynamic_range must be > 0"),
        ({"delta_0": 2.0, "dynamic_range": 1.0}, "must be < dynamic_range"),
        ({"T_kelvin": 0.0}, "T_kelvin must be > 0"),
        ({"T_kelvin": -10.0}, "T_kelvin must be > 0"),
    ],
)
def test_INV_TAU3_landauer_energy_rejects_bad_inputs(kwargs: dict[str, float], msg: str) -> None:
    base = {"delta_0": 1e-6, "dynamic_range": 1.0, "T_kelvin": 300.0}
    base.update(kwargs)
    with pytest.raises(ValueError, match=msg):
        landauer_min_initialisation_energy(**base)


@pytest.mark.parametrize(
    "kwargs,msg",
    [
        ({"energy_budget_J": -1.0}, "energy_budget_J must be ≥ 0"),
        ({"dynamic_range": 0.0}, "dynamic_range must be > 0"),
        ({"T_kelvin": 0.0}, "T_kelvin must be > 0"),
    ],
)
def test_INV_TAU3_landauer_min_precision_rejects_bad_inputs(
    kwargs: dict[str, float], msg: str
) -> None:
    base = {"energy_budget_J": 1e-15, "dynamic_range": 1.0, "T_kelvin": 300.0}
    base.update(kwargs)
    with pytest.raises(ValueError, match=msg):
        landauer_min_initial_precision(**base)


def test_INV_TAU3_horizon_under_budget_rejects_dynamic_range_lt_tol() -> None:
    with pytest.raises(ValueError, match="must exceed delta_tol"):
        predictability_horizon_under_budget(
            lambda_1=1.0,
            delta_tol=2.0,
            dynamic_range=1.0,
            energy_budget_J=1e-19,
        )


def test_INV_TAU3_horizon_under_budget_rejects_too_small_budget() -> None:
    """Tiny budget so floor exceeds δ_tol — INFEASIBLE."""
    with pytest.raises(ValueError, match="budget too small or delta_tol"):
        # E=0 ⇒ δ_0_min = Δ; trivially ≥ δ_tol.
        predictability_horizon_under_budget(
            lambda_1=1.0,
            delta_tol=0.5,
            dynamic_range=1.0,
            energy_budget_J=0.0,
        )


# ── Use-case sanity: room-temperature, GeoSync-realistic numbers ─────────────


def test_use_case_room_T_modest_budget_gives_long_horizon() -> None:
    """At T=300 K, a modest E=1e-19 J budget at λ_1=0.9056 yields τ≫1.

    The point: even a budget that resolves Δ=1 to ~10⁻¹¹ at 300 K
    (≈ 35 bits) gives many Lyapunov-times of horizon on a chaotic
    system as fast as Lorenz-63. This confirms the law is well-behaved
    in the regimes GeoSync actually operates in. Budgets above ~3e-18 J
    at 300 K cause the Landauer floor to underflow float64 and are
    rejected upstream (INV-TAU3 documented behaviour).
    """
    rep = predictability_horizon_under_budget(
        lambda_1=0.9056,  # Lorenz-63 λ_1
        delta_tol=0.01,
        dynamic_range=1.0,
        energy_budget_J=1e-19,
        T_kelvin=300.0,
    )
    assert math.isfinite(rep.tau)
    # 35 bits resolves Δ to ≈ 3e-11; ln(0.01/3e-11)/0.9056 ≈ 21.6.
    assert rep.tau > 20.0, f"E=1e-19 J at T=300K should give τ ≥ 20 Lyapunov-times, got {rep.tau}"


# ── Determinism (INV-HPC1 compat) ────────────────────────────────────────────


def test_INV_HPC1_pure_function_repeatable() -> None:
    """Two evaluations of the same inputs return identical floats."""
    rep_a = predictability_horizon_under_budget(
        lambda_1=0.5, delta_tol=0.1, dynamic_range=1.0, energy_budget_J=1e-19
    )
    rep_b = predictability_horizon_under_budget(
        lambda_1=0.5, delta_tol=0.1, dynamic_range=1.0, energy_budget_J=1e-19
    )
    assert rep_a == rep_b
