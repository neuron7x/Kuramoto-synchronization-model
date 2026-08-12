# SPDX-License-Identifier: MIT
"""LAW T5 — Predictability horizon under a Landauer information budget.

Constitutional Law T5 of seven (CLAUDE.md GeoSync Physics Law Act).

Identity
--------
For an autonomous chaotic flow with maximal Lyapunov exponent
``λ_1 > 0``, two infinitesimally close trajectories separate as

    |δx(t)|  ≈  |δx(0)| · exp(λ_1 · t).

The *predictability horizon* is the time after which the separation
exceeds an operational tolerance:

    τ(λ_1; δ_0, δ_tol)  =  (1/λ_1) · ln(δ_tol / δ_0).            (Lorenz 1969)

Below `τ` the trajectory is reproducible to ``δ_tol``; above ``τ`` it
is not. ``λ_1 ≤ 0`` ⇒ horizon is *infinite* (predictable indefinitely
in the operational sense).

Landauer's principle (Landauer 1961) sets a hard physical lower bound
on the energy required to *initialise* the state to precision ``δ_0``
on a finite-dynamic-range substrate. For a state of dynamic range
``Δ`` resolved to precision ``δ_0``, the number of bits is

    n_bits  =  log_2(Δ / δ_0),

and the minimum energy to initialise is

    E_min(δ_0)  =  k_B · T · ln(2) · log_2(Δ / δ_0)
                =  k_B · T · ln(Δ / δ_0).                         (Landauer 1961)

Given a hard energy budget ``E_budget`` for state initialisation,
``δ_0`` is bounded below: ``δ_0 ≥ Δ · exp(−E_budget / (k_B T))``. The
*Landauer-budgeted predictability horizon* is therefore

    τ_max(λ_1; E_budget, T, δ_tol, Δ)
        =  (1/λ_1) · ln(δ_tol / δ_0_min)
        =  (1/λ_1) · [ln(δ_tol / Δ)  +  E_budget / (k_B T)].      (T5 master)

This formula sets the **operational predictability ceiling** on any
chaotic GeoSync component: no τ extension beyond this value is
physically available. The variational T5 corollary chooses ``δ_0``
optimally so that the budget is never wasted.

Constitutional invariants (P0)
------------------------------
* INV-TAU1 | algebraic    | Lorenz inequality: ``τ_horizon(λ_1) =
                            (1/λ_1) · ln(δ_tol/δ_0)`` exactly when
                            ``λ_1 > 0``; ``+∞`` when ``λ_1 ≤ 0``.
* INV-TAU2 | conservation | Landauer floor: ``E_min(δ_0) =
                            k_B · T · ln(Δ/δ_0)`` is exact; any
                            ``δ_0 < Δ · exp(−E_budget / (k_B T))`` is
                            rejected as INFEASIBLE.
* INV-TAU3 | universal    | every contract violation
                            (non-positive λ_target inputs, δ_0 ≥ δ_tol,
                            δ_0 ≤ 0, T ≤ 0, E_budget < 0, Δ ≤ δ_tol)
                            raises ValueError; fail-closed.

Determinism: pure-functional, side-effect-free; identical inputs ⇒
identical outputs to float64 precision (INV-HPC1 compat).

References
----------
* Lorenz, E. N. (1969). *The predictability of a flow which possesses
  many scales of motion.* Tellus 21, 289–307.
* Landauer, R. (1961). *Irreversibility and heat generation in the
  computing process.* IBM J. Res. Dev. 5, 183–191.
* Bennett, C. H. (2003). *Notes on Landauer's principle, reversible
  computation, and Maxwell's Demon.* Stud. Hist. Philos. Mod. Phys. 34.
"""

from __future__ import annotations

import math
from typing import NamedTuple

# Physical constants — sourced from the existing core.physics.landauer
# module to keep a single source of truth in the repository.
from core.physics.landauer import K_BOLTZMANN, ROOM_TEMPERATURE

__all__ = [
    "HorizonReport",
    "K_BOLTZMANN",
    "ROOM_TEMPERATURE",
    "landauer_min_initial_precision",
    "landauer_min_initialisation_energy",
    "predictability_horizon",
    "predictability_horizon_under_budget",
]

# Sentinel for "predictable indefinitely". Float-typed so the result
# remains drop-in for downstream Float64 arithmetic.
_INFINITE_HORIZON: float = math.inf


class HorizonReport(NamedTuple):
    """Structured outcome of a predictability-horizon evaluation.

    Attributes
    ----------
    tau:
        Predictability horizon in the same time-units as ``λ_1``.
        ``+inf`` if the system is non-chaotic (``λ_1 ≤ 0``).
    delta_0:
        Initial-condition precision used. Echoed for audit trail.
    delta_0_min_landauer:
        Lower bound on ``δ_0`` set by the Landauer budget. ``0.0`` if
        no budget was supplied.
    energy_required_J:
        ``E_min(δ_0)`` for the chosen ``δ_0``. Useful for budget
        accounting downstream.
    saturated_budget:
        ``True`` if ``δ_0`` was driven down to the Landauer floor
        (``δ_0 == delta_0_min_landauer``); ``False`` otherwise.
    """

    tau: float
    delta_0: float
    delta_0_min_landauer: float
    energy_required_J: float
    saturated_budget: bool


# ── Building blocks ──────────────────────────────────────────────────────────


def predictability_horizon(lambda_1: float, *, delta_0: float, delta_tol: float) -> float:
    """Lorenz inequality: ``τ = (1/λ_1) · ln(δ_tol/δ_0)`` for ``λ_1 > 0``.

    For ``λ_1 ≤ 0`` returns ``+inf`` — the system is non-chaotic in the
    operational sense, so the horizon is unbounded.

    Parameters
    ----------
    lambda_1:
        Maximal Lyapunov exponent (consistent units with the desired τ).
        Must be finite.
    delta_0:
        Initial-condition precision. ``0 < δ_0 < δ_tol``.
    delta_tol:
        Operational tolerance. ``δ_tol > δ_0 > 0``.

    Raises
    ------
    ValueError
        On any contract violation (INV-TAU3).
    """
    if not math.isfinite(lambda_1):
        raise ValueError(f"INV-TAU3: lambda_1 must be finite, got {lambda_1}")
    if delta_0 <= 0.0:
        raise ValueError(f"INV-TAU3: delta_0 must be > 0, got {delta_0}")
    if delta_tol <= 0.0:
        raise ValueError(f"INV-TAU3: delta_tol must be > 0, got {delta_tol}")
    if delta_0 >= delta_tol:
        raise ValueError(f"INV-TAU3: delta_0 ({delta_0}) must be < delta_tol ({delta_tol})")
    if lambda_1 <= 0.0:
        return _INFINITE_HORIZON
    return math.log(delta_tol / delta_0) / lambda_1


def landauer_min_initialisation_energy(
    delta_0: float, *, dynamic_range: float, T_kelvin: float = ROOM_TEMPERATURE
) -> float:
    """Landauer minimum energy to initialise state to precision δ_0.

    ``E_min(δ_0) = k_B · T · ln(Δ / δ_0)``. Independent of the
    integrator or numerical scheme; sets the *physical* floor.

    Parameters
    ----------
    delta_0:
        Initial-condition precision. ``0 < δ_0 < Δ``.
    dynamic_range:
        Total dynamic range Δ of the state variable. ``Δ > δ_0``.
    T_kelvin:
        Bath temperature. Default 300 K (room temperature).

    Returns
    -------
    float
        Energy in Joules (SI). Always ≥ 0.

    Raises
    ------
    ValueError
        On any contract violation (INV-TAU3).
    """
    if delta_0 <= 0.0:
        raise ValueError(f"INV-TAU3: delta_0 must be > 0, got {delta_0}")
    if dynamic_range <= 0.0:
        raise ValueError(f"INV-TAU3: dynamic_range must be > 0, got {dynamic_range}")
    if delta_0 >= dynamic_range:
        raise ValueError(
            f"INV-TAU3: delta_0 ({delta_0}) must be < dynamic_range "
            f"({dynamic_range}) — initialisation cannot resolve below "
            f"its own dynamic range"
        )
    if T_kelvin <= 0.0:
        raise ValueError(f"INV-TAU3: T_kelvin must be > 0, got {T_kelvin}")
    return K_BOLTZMANN * T_kelvin * math.log(dynamic_range / delta_0)


def landauer_min_initial_precision(
    energy_budget_J: float,
    *,
    dynamic_range: float,
    T_kelvin: float = ROOM_TEMPERATURE,
) -> float:
    """Tightest δ_0 affordable under a hard Landauer energy budget.

    Inverts ``E_min(δ_0)`` for ``δ_0``:
    ``δ_0_min = Δ · exp(−E_budget / (k_B T))``.

    Parameters
    ----------
    energy_budget_J:
        Energy budget in Joules. Must be ≥ 0.
    dynamic_range:
        Total dynamic range Δ of the state variable.
    T_kelvin:
        Bath temperature. Default 300 K.

    Raises
    ------
    ValueError
        On any contract violation (INV-TAU3).
    """
    if energy_budget_J < 0.0:
        raise ValueError(f"INV-TAU3: energy_budget_J must be ≥ 0, got {energy_budget_J}")
    if dynamic_range <= 0.0:
        raise ValueError(f"INV-TAU3: dynamic_range must be > 0, got {dynamic_range}")
    if T_kelvin <= 0.0:
        raise ValueError(f"INV-TAU3: T_kelvin must be > 0, got {T_kelvin}")
    return dynamic_range * math.exp(-energy_budget_J / (K_BOLTZMANN * T_kelvin))


# ── Master formula ───────────────────────────────────────────────────────────


def predictability_horizon_under_budget(
    lambda_1: float,
    *,
    delta_tol: float,
    dynamic_range: float,
    energy_budget_J: float,
    T_kelvin: float = ROOM_TEMPERATURE,
    delta_0_request: float | None = None,
) -> HorizonReport:
    """Predictability horizon clamped by a Landauer energy budget.

    ``τ_max  =  (1/λ_1) · ln(δ_tol / max(δ_0_request, δ_0_min_landauer))``

    where ``δ_0_min_landauer`` is the Landauer floor implied by
    ``energy_budget_J``. The variational T5 maximises τ by driving
    ``δ_0`` down to the floor — which is what
    ``delta_0_request = None`` does by default.

    Parameters
    ----------
    lambda_1:
        Maximal Lyapunov exponent. Finite.
    delta_tol:
        Operational tolerance. ``δ_tol > 0``; must exceed
        ``δ_0_min_landauer``.
    dynamic_range:
        Dynamic range Δ of the state variable. ``Δ > δ_tol``.
    energy_budget_J:
        Hard Landauer budget for state initialisation. ≥ 0.
    T_kelvin:
        Bath temperature. Default 300 K.
    delta_0_request:
        Optional explicit ``δ_0``. ``None`` ⇒ use the Landauer floor
        (variational maximum). If supplied below the floor, raise.

    Returns
    -------
    HorizonReport
        Saturated_budget = True iff δ_0 was driven to the Landauer floor.

    Raises
    ------
    ValueError
        On any contract violation (INV-TAU2, INV-TAU3).
    """
    if dynamic_range <= delta_tol:
        raise ValueError(
            f"INV-TAU3: dynamic_range ({dynamic_range}) must exceed "
            f"delta_tol ({delta_tol}); cannot resolve tolerance "
            f"finer than the state's own dynamic range"
        )

    delta_0_min = landauer_min_initial_precision(
        energy_budget_J, dynamic_range=dynamic_range, T_kelvin=T_kelvin
    )

    if delta_0_request is None:
        delta_0_used = delta_0_min
        saturated = True
    else:
        if delta_0_request < delta_0_min:
            raise ValueError(
                f"INV-TAU2: delta_0_request ({delta_0_request:.3e}) is "
                f"below the Landauer floor ({delta_0_min:.3e}) at "
                f"E_budget={energy_budget_J:.3e} J, T={T_kelvin} K — "
                f"physically unaffordable"
            )
        delta_0_used = delta_0_request
        saturated = bool(delta_0_request == delta_0_min)

    if delta_0_used >= delta_tol:
        raise ValueError(
            f"INV-TAU3: budget too small or delta_tol too tight: "
            f"delta_0_used ({delta_0_used:.3e}) ≥ delta_tol "
            f"({delta_tol:.3e}). Increase E_budget or relax delta_tol."
        )

    tau = predictability_horizon(lambda_1, delta_0=delta_0_used, delta_tol=delta_tol)
    energy_required = landauer_min_initialisation_energy(
        delta_0_used, dynamic_range=dynamic_range, T_kelvin=T_kelvin
    )

    return HorizonReport(
        tau=tau,
        delta_0=delta_0_used,
        delta_0_min_landauer=delta_0_min,
        energy_required_J=energy_required,
        saturated_budget=saturated,
    )
