# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Witnesses for ecs_lyapunov_descent (thermodynamic free-energy stability law).

Binds the falsification-catalog law ``ecs_lyapunov_descent`` to the REAL
``core.neuro.ecs_lyapunov.ECSLyapunovRegulator`` (the "Sustainer / ECS Lyapunov"
maintenance layer, dF/dt <= 0). The regulator integrates a homeostatic free-energy
ODE with RK4 and carries a Lyapunov function

    V = 0.5 * FE^2 + lambda * CF^2 + mu * SI^2  >= 0

with a post-hoc descent correction: if an RK4 step would raise V while
``V_before > 1e-12`` (the operating set, away from the V=0 floor), the update is
scaled back until ``V_after <= V_before``.

* Positive witness: from seeded initial states inside the operating set, V is
  monotone non-increasing along autonomous trajectories across all seeds; the
  worst per-step increment stays at/below tolerance.
* Negative control: a real energy injection that WOULD drive V up under the
  uncorrected RK4 dynamics is detected and rejected — the corrected step fails
  closed to descent (V_after <= V_before, stable=True). Remove the corrector and
  this control fails. Nothing here is a market claim.
"""

from __future__ import annotations

import numpy as np

from core.neuro.ecs_lyapunov import ECSLyapunovRegulator
from core.neuro.signal_bus import NeuroSignalBus

# Below this Lyapunov value the descent guarantee is suspended by physics: V >= 0
# cannot fall below zero, so a stress injection from the origin necessarily raises
# V. The operating set is V_before > V_FLOOR; the witness lives strictly inside it.
V_FLOOR = 1e-12
# Worst admissible per-step increment. The corrector's worst case is alpha = 0
# (no move) => dV = 0 exactly; 1e-9 leaves margin for float round-off in V.
DESCENT_TOL = 1e-9
N_SEEDS = 12
N_STEPS = 150
DT = 0.5


def _lyapunov(regulator: ECSLyapunovRegulator) -> float:
    return regulator._lyapunov(
        regulator.free_energy,
        regulator.compensatory_factor,
        regulator.stress_integral,
    )


def _seed_in_operating_set(seed: int) -> ECSLyapunovRegulator:
    """Place the regulator at a seeded state well inside the operating set (V >> floor)."""
    rng = np.random.default_rng(seed)
    regulator = ECSLyapunovRegulator(NeuroSignalBus())
    regulator.free_energy = float(rng.uniform(0.5, 2.0)) * float(rng.choice([-1.0, 1.0]))
    regulator.compensatory_factor = float(rng.uniform(0.2, 1.0)) * float(rng.choice([-1.0, 1.0]))
    regulator.stress_integral = float(rng.uniform(0.2, 1.0)) * float(rng.choice([-1.0, 1.0]))
    return regulator


def test_ecs_lyapunov_monotone_descent_across_seeds() -> None:
    """Positive witness: V(t+1) <= V(t) every step, every seed, inside the operating set.

    Drives the real ECS regulator autonomously (stress = 0) from seeded initial
    states. The Lyapunov function V = 0.5*FE^2 + lambda*CF^2 + mu*SI^2 must be a
    descent functional: no step raises V beyond DESCENT_TOL, and the guarantee is
    actually exercised (min V_before stays far above the floor, so the check is
    non-vacuous).
    """
    worst_increment = -np.inf
    min_v_before = np.inf
    steps_checked = 0
    for seed in range(N_SEEDS):
        regulator = _seed_in_operating_set(seed)
        for _ in range(N_STEPS):
            v_before = _lyapunov(regulator)
            result = regulator.step(stress=0.0, dt=DT)
            v_after = float(result["lyapunov_V"])
            assert v_before > V_FLOOR, (
                f"ECS-LYAPUNOV-DESCENT precondition: V_before={v_before:.3e} fell to the "
                f"floor V_FLOOR={V_FLOOR:.0e}; the operating-set witness must stay strictly "
                f"above the V=0 floor. seed={seed}, steps_checked={steps_checked}, tol={DESCENT_TOL:.0e}"
            )
            worst_increment = max(worst_increment, v_after - v_before)
            min_v_before = min(min_v_before, v_before)
            steps_checked += 1
    assert worst_increment <= DESCENT_TOL, (
        f"ECS-LYAPUNOV-DESCENT VIOLATED: worst V(t+1)-V(t)={worst_increment:.3e} "
        f"exceeds tol={DESCENT_TOL:.0e}; V=0.5*FE^2+lambda*CF^2+mu*SI^2 must be a "
        f"descent functional (dV/dt<=0) along trajectories. "
        f"n_seeds={N_SEEDS}, steps_checked={steps_checked}, min_V_before={min_v_before:.3e}"
    )
    assert steps_checked >= N_SEEDS * N_STEPS, (
        f"ECS-LYAPUNOV-DESCENT vacuity guard: steps_checked={steps_checked} below "
        f"the expected {N_SEEDS * N_STEPS}; the descent guarantee must be exercised, "
        f"not skipped. n_seeds={N_SEEDS}, n_steps={N_STEPS}, tol={DESCENT_TOL:.0e}, "
        f"min_V_before={min_v_before:.3e}"
    )


def test_ecs_lyapunov_energy_injection_is_rejected() -> None:
    """Negative control: a planted energy injection is caught and forced into descent.

    From a small-but-above-floor state, the UNCORRECTED RK4 step under a large
    stress injection would raise V by orders of magnitude (a real violation). The
    regulator's corrected ``step`` must detect this and fail closed to descent:
    V_after <= V_before with stable=True. Disable the corrector and this control
    fails — so it is discriminating, not vacuous.
    """
    regulator = ECSLyapunovRegulator(NeuroSignalBus())
    regulator.free_energy = 1e-3
    regulator.compensatory_factor = 0.0
    regulator.stress_integral = 0.0
    injection = 5.0

    v_before = _lyapunov(regulator)
    assert v_before > V_FLOOR, (
        f"ECS-LYAPUNOV-DESCENT control setup: V_before={v_before:.3e} must exceed "
        f"V_FLOOR={V_FLOOR:.0e} so the corrector is in scope. injection={injection}, dt={DT}"
    )

    # Uncorrected RK4 (the dynamics WITHOUT the Lyapunov correction) — planted rise.
    raw_fe, raw_cf, raw_si = regulator._rk4_step(
        regulator.free_energy,
        regulator.compensatory_factor,
        regulator.stress_integral,
        injection,
        DT,
    )
    v_raw = regulator._lyapunov(raw_fe, raw_cf, raw_si)
    assert v_raw > v_before, (
        f"ECS-LYAPUNOV-DESCENT control invalid: uncorrected RK4 V_raw={v_raw:.3e} did "
        f"not exceed V_before={v_before:.3e}; the energy injection must actually push V "
        f"up for the corrector to have something to reject. injection={injection}, dt={DT}"
    )

    # Corrected step must catch the injection and fail closed to descent.
    result = regulator.step(stress=injection, dt=DT)
    v_after = float(result["lyapunov_V"])
    assert v_after <= v_before, (
        f"ECS-LYAPUNOV-DESCENT VIOLATED: corrected step V_after={v_after:.3e} exceeds "
        f"V_before={v_before:.3e} despite the correction; uncorrected would have hit "
        f"V_raw={v_raw:.3e}. The regulator must fail closed to dV/dt<=0. "
        f"injection={injection}, dt={DT}, stable={result['stable']}"
    )
    assert bool(result["stable"]) is True, (
        f"ECS-LYAPUNOV-DESCENT VIOLATED: regulator reported stable={result['stable']} "
        f"after catching an injection (V_before={v_before:.3e}, V_after={v_after:.3e}, "
        f"V_raw={v_raw:.3e}); a caught violation must be flagged stable. "
        f"injection={injection}, dt={DT}"
    )
