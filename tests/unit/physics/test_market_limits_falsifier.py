# SPDX-License-Identifier: MIT
# no-bio-claim
"""Executable falsifier path for the Landauer-budgeted predictability bound.

Methodology instrument F. This module is a descriptor-only falsifier: it
asserts a *bound*, never a market prediction. The descriptor under test is
``core.physics.predictability_horizon`` and its stated budget bound INV-TAU2
(the Landauer floor on the initial-condition precision ``δ_0``):

    δ_0 ≥ Δ · exp(−E_budget / (k_B T))

A precision claim *below* this floor is physically unaffordable and must be
ruled out — the descriptor must flip to the failing verdict (``ValueError``)
on every out-of-bound input. Each node here genuinely exercises the
*violation* path: if the descriptor silently accepted a sub-floor precision
or an out-of-bound horizon request, the corresponding node would FAIL. These
are not ``assert True`` placeholders; they import the live descriptor and
drive it across the boundary.

The existing ``test_T5_predictability_landauer`` battery pins the algebraic
identities and a single floor-rejection case. This file adds an executable
falsifier *path* that sweeps the budget bound and asserts the unaffordability
verdict as a hard cap, including fail-closed and NaN propagation through the
master formula. No invariant is added and no claim tier is promoted; INV-TAU2
is the descriptor's own documented bound.
"""

from __future__ import annotations

import math

import pytest

from core.physics.landauer import K_BOLTZMANN
from core.physics.predictability_horizon import (
    HorizonReport,
    landauer_min_initial_precision,
    predictability_horizon_under_budget,
)

# Room-temperature bath; kept within the float64-representable Landauer
# regime (E ≪ 700 · k_B · T ≈ 2.9e-18 J at 300 K) so the floor does not
# underflow and the bound stays exercisable on both sides.
_T_KELVIN: float = 300.0
_DYNAMIC_RANGE: float = 1.0


def test_INV_TAU2_subfloor_precision_request_is_ruled_out() -> None:
    """INV-TAU2 falsifier: a δ_0 strictly below the Landauer floor flips the
    verdict to ValueError (physically unaffordable) — the bound is a hard cap.

    Fails if the descriptor were to silently accept a sub-floor precision.
    """
    energy_budget_J = 1e-20  # ≈ 14 bits at 300 K
    floor = landauer_min_initial_precision(
        energy_budget_J, dynamic_range=_DYNAMIC_RANGE, T_kelvin=_T_KELVIN
    )
    assert floor > 0.0, "INV-TAU2: floor underflowed; pick a smaller budget"
    with pytest.raises(ValueError, match="below the Landauer floor"):
        predictability_horizon_under_budget(
            lambda_1=1.0,
            delta_tol=0.5,
            dynamic_range=_DYNAMIC_RANGE,
            energy_budget_J=energy_budget_J,
            T_kelvin=_T_KELVIN,
            delta_0_request=floor * 0.5,
        )


@pytest.mark.parametrize("budget_fraction", [0.99, 0.50, 0.10, 1e-3])
def test_INV_TAU2_subfloor_sweep_every_point_ruled_out(budget_fraction: float) -> None:
    """INV-TAU2 falsifier sweep: across a range of sub-floor precisions the
    unaffordability verdict must hold at *every* point — a single accepted
    sub-floor claim would falsify the bound and fail this node.
    """
    energy_budget_J = 1e-19  # ≈ 35 bits at 300 K
    floor = landauer_min_initial_precision(
        energy_budget_J, dynamic_range=_DYNAMIC_RANGE, T_kelvin=_T_KELVIN
    )
    requested = floor * budget_fraction
    assert requested < floor, "INV-TAU2: sweep point must lie below the floor"
    with pytest.raises(ValueError, match="below the Landauer floor"):
        predictability_horizon_under_budget(
            lambda_1=0.9056,
            delta_tol=0.1,
            dynamic_range=_DYNAMIC_RANGE,
            energy_budget_J=energy_budget_J,
            T_kelvin=_T_KELVIN,
            delta_0_request=requested,
        )


def test_INV_TAU2_at_floor_is_admissible_boundary() -> None:
    """INV-TAU2 boundary: a request exactly at the Landauer floor is the
    tightest affordable precision and must be accepted (saturated budget).

    This pins the *other* side of the cap: the bound is δ_0 ≥ floor, not
    δ_0 > floor. A descriptor that rejected the exact floor would over-
    constrain and fail this node.
    """
    energy_budget_J = 1e-19
    floor = landauer_min_initial_precision(
        energy_budget_J, dynamic_range=_DYNAMIC_RANGE, T_kelvin=_T_KELVIN
    )
    report = predictability_horizon_under_budget(
        lambda_1=1.0,
        delta_tol=0.1,
        dynamic_range=_DYNAMIC_RANGE,
        energy_budget_J=energy_budget_J,
        T_kelvin=_T_KELVIN,
        delta_0_request=floor,
    )
    assert isinstance(report, HorizonReport)
    assert report.delta_0 == floor, "INV-TAU2: at-floor request must be used verbatim"
    assert report.saturated_budget is True
    assert math.isfinite(report.tau)


def test_INV_TAU2_zero_budget_floor_exceeds_tolerance_is_ruled_out() -> None:
    """INV-TAU2 falsifier: E_budget = 0 drives the floor to the full dynamic
    range (δ_0_min = Δ), which cannot resolve below δ_tol — INFEASIBLE.

    Verifies the budget bound also rules out the degenerate zero-budget claim;
    fails if the descriptor returned a horizon for an unresolvable budget.
    """
    with pytest.raises(ValueError, match="budget too small or delta_tol"):
        predictability_horizon_under_budget(
            lambda_1=1.0,
            delta_tol=0.5,
            dynamic_range=_DYNAMIC_RANGE,
            energy_budget_J=0.0,
            T_kelvin=_T_KELVIN,
        )


def test_INV_TAU3_nan_lambda_fails_closed_through_master_formula() -> None:
    """INV-TAU3 fail-closed: a non-finite Lyapunov exponent must propagate to
    a ValueError through the master formula — no NaN horizon escapes.

    Fails if a NaN λ_1 yielded a NaN ``tau`` instead of a hard rejection.
    """
    for bad_lambda in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError, match="must be finite"):
            predictability_horizon_under_budget(
                lambda_1=bad_lambda,
                delta_tol=0.1,
                dynamic_range=_DYNAMIC_RANGE,
                energy_budget_J=1e-19,
                T_kelvin=_T_KELVIN,
            )


def test_INV_TAU3_negative_budget_fails_closed() -> None:
    """INV-TAU3 fail-closed: a negative energy budget is non-physical and must
    raise — the bound never silently clamps a negative budget to zero.
    """
    with pytest.raises(ValueError, match="energy_budget_J must be"):
        predictability_horizon_under_budget(
            lambda_1=1.0,
            delta_tol=0.1,
            dynamic_range=_DYNAMIC_RANGE,
            energy_budget_J=-1e-19,
            T_kelvin=_T_KELVIN,
        )


def test_INV_TAU2_floor_is_monotone_decreasing_in_budget() -> None:
    """INV-TAU2 consistency: a larger budget buys a strictly tighter (smaller)
    affordable floor. A descriptor whose floor failed to shrink with budget
    would let an under-budget claim masquerade as affordable — this node
    would then fail.
    """
    floor_small = landauer_min_initial_precision(
        1e-20, dynamic_range=_DYNAMIC_RANGE, T_kelvin=_T_KELVIN
    )
    floor_large = landauer_min_initial_precision(
        1e-19, dynamic_range=_DYNAMIC_RANGE, T_kelvin=_T_KELVIN
    )
    assert floor_large < floor_small, "INV-TAU2: larger budget must lower the floor"
    # Cross-check against the closed form δ_0_min = Δ · exp(−E/(k_B T)).
    expected_large = _DYNAMIC_RANGE * math.exp(-1e-19 / (K_BOLTZMANN * _T_KELVIN))
    assert math.isclose(floor_large, expected_large, rel_tol=1e-12)
