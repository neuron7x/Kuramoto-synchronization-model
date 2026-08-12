# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Witnesses for the serotonin neuromodulation falsification laws.

Binds two blocking laws in physics_contracts/falsification_catalog.yaml to the
REAL serotonin ODE (core/neuro/serotonin_ode.py — no reimplementation):

  * serotonin_level_bounds      (INV-5HT2): level(t) in [0, 1], guard-enforced.
  * serotonin_lyapunov_stability(INV-5HT1): V non-increasing under zero stress.

Each law carries a positive witness AND a discriminating negative control.
"""

from __future__ import annotations

import numpy as np

from core.neuro.serotonin_ode import SerotoninODE, SerotoninODEParams


def _unclamped_rk4_level(ode: SerotoninODE, stress: float, dt: float) -> float:
    """Replay one RK4 level step WITHOUT the step() [0,1] clamp.

    Reuses the ODE's own ``_derivatives`` so the dynamics are identical to
    ``step``; only the boundary guard is omitted. This isolates whether the
    [0,1] bound is enforced by the guard or merely incidental.
    """
    y1, y2 = ode.level, ode.desensitization
    k1a, k1b = ode._derivatives(y1, y2, stress)
    k2a, k2b = ode._derivatives(y1 + 0.5 * dt * k1a, y2 + 0.5 * dt * k1b, stress)
    k3a, k3b = ode._derivatives(y1 + 0.5 * dt * k2a, y2 + 0.5 * dt * k2b, stress)
    k4a, k4b = ode._derivatives(y1 + dt * k3a, y2 + dt * k3b, stress)
    return y1 + (dt / 6.0) * (k1a + 2 * k2a + 2 * k3a + k4a)


# ── Law: serotonin_level_bounds (INV-5HT2) ───────────────────────────


def test_level_stays_in_unit_interval() -> None:
    """Positive witness: level(t) in [0,1] over seeded zero-and-stress trajectories."""
    params = SerotoninODEParams()
    rng = np.random.default_rng(20260627)
    lo, hi = 1.0, 0.0
    for _ in range(40):
        level0 = float(rng.uniform(0.0, 1.0))
        ode = SerotoninODE(params, level=level0, desensitization=float(rng.uniform(0.0, 1.0)))
        # Mix quiescent and stressed regimes so the bound is exercised both ways.
        for step_idx in range(1000):
            stress = 5.0 if step_idx % 3 == 0 else 0.0
            level, _ = ode.step(stress=stress, dt=0.1)
            lo, hi = min(lo, level), max(hi, level)
            assert 0.0 <= level <= 1.0, (
                f"INV-5HT2 VIOLATED: level={level:.6f} left [0,1] "
                f"expected 0<=level<=1 for all t. "
                f"5-HT concentration is a bounded biological quantity. "
                f"At seed-start level0={level0:.4f}, stress={stress}, step={step_idx}"
            )
    assert 0.0 <= lo <= hi <= 1.0, (
        f"INV-5HT2 VIOLATED: observed level range [{lo:.6f}, {hi:.6f}] left [0,1] "
        f"expected the full trajectory envelope inside the unit interval. "
        f"5-HT concentration is a bounded biological quantity. "
        f"realizations=40, steps=1000, dt=0.1"
    )


def test_unclamped_dynamics_would_leave_unit_interval() -> None:
    """Negative control: the guard is load-bearing, not incidental.

    Under extreme stress the raw (unclamped) RK4 update pushes level above 1,
    yet the guarded ``step`` returns a value inside [0,1]. If the clamp were
    removed the positive witness above would fail — this test proves the bound
    is *enforced*, and that an out-of-range dynamic is genuinely produced.
    """
    params = SerotoninODEParams()
    ode = SerotoninODE(params, level=0.9, desensitization=0.0)
    raw_level = _unclamped_rk4_level(ode, stress=5.0, dt=1.0)
    guarded_level, _ = ode.step(stress=5.0, dt=1.0)
    assert raw_level > 1.0, (
        f"INV-5HT2 CONTROL DEGENERATE: raw unclamped level={raw_level:.6f} did not exceed 1 "
        f"expected the bare dynamics to leave [0,1] so the guard is testable. "
        f"5-HT concentration bound must be enforced, not incidental. "
        f"At level0=0.9, stress=5.0, dt=1.0"
    )
    assert 0.0 <= guarded_level <= 1.0, (
        f"INV-5HT2 VIOLATED: guarded level={guarded_level:.6f} left [0,1] under extreme stress "
        f"expected the step() clamp to enforce 0<=level<=1. "
        f"5-HT concentration is a bounded biological quantity. "
        f"At level0=0.9, stress=5.0, dt=1.0, raw={raw_level:.4f}"
    )


# ── Law: serotonin_lyapunov_stability (INV-5HT1) ─────────────────────


def test_lyapunov_nonincreasing_zero_stress() -> None:
    """Positive witness: V is non-increasing under zero stress from perturbed states."""
    params = SerotoninODEParams()
    rng = np.random.default_rng(552026)
    tol = 1e-9
    worst_increment = -np.inf
    for _ in range(40):
        ode = SerotoninODE(
            params,
            level=float(rng.uniform(0.0, 1.0)),
            desensitization=float(rng.uniform(0.0, 1.0)),
        )
        trajectory: list[tuple[float, float]] = [(ode.level, ode.desensitization)]
        v_start = ode._lyapunov(ode.level, ode.desensitization)
        prev_v = v_start
        for _ in range(2000):
            ode.step(stress=0.0, dt=0.05)
            trajectory.append((ode.level, ode.desensitization))
            curr_v = ode._lyapunov(ode.level, ode.desensitization)
            worst_increment = max(worst_increment, curr_v - prev_v)
            prev_v = curr_v
        v_end = ode._lyapunov(ode.level, ode.desensitization)
        assert ode.verify_lyapunov(trajectory), (
            f"INV-5HT1 VIOLATED: verify_lyapunov flagged a V increase under zero stress "
            f"expected V(l,d)=0.5*(l-target)^2+lambda*d^2 monotone non-increasing. "
            f"Zero-input serotonin ODE must be Lyapunov-stable about (target,0). "
            f"final state=({ode.level:.4f},{ode.desensitization:.4f}), steps=2000"
        )
        # Descent toward the set-point: energy strictly decreases under zero input.
        # (Finite-time level need not equal target while desens>0 offsets the
        # level equilibrium to baseline - delta*desens/(alpha+gamma); the genuine
        # invariant is V descent, not level==target at a finite horizon.)
        assert v_end <= v_start + tol, (
            f"INV-5HT1 VIOLATED: V rose from {v_start:.6f} to {v_end:.6f} under zero stress "
            f"expected net Lyapunov descent toward (target, desens->0). "
            f"V(l,d)=0.5*(l-target)^2+lambda*d^2 is the serotonin energy. "
            f"final state=({ode.level:.4f},{ode.desensitization:.4f}), steps=2000"
        )
    assert worst_increment <= tol, (
        f"INV-5HT1 VIOLATED: worst V increment={worst_increment:.3e} > tol={tol:.1e} "
        f"expected dV/dt<=0 (non-increasing) under zero stress. "
        f"V(l,d)=0.5*(l-target)^2+lambda*d^2 is the serotonin Lyapunov certificate. "
        f"seeds=40, steps=2000, dt=0.05"
    )


def test_driving_stress_violates_lyapunov_descent() -> None:
    """Negative control: a non-zero drive that raises V is detected.

    Starting exactly at the set-point (level=target, desens=0) where V=0, a
    sustained stress drives level away from target, so V *increases* and
    ``verify_lyapunov`` must return False. A descent check that passed here
    would be vacuous.
    """
    params = SerotoninODEParams()
    ode = SerotoninODE(params, level=params.target, desensitization=0.0)
    trajectory: list[tuple[float, float]] = [(ode.level, ode.desensitization)]
    v_start = ode._lyapunov(ode.level, ode.desensitization)
    worst_increment = -np.inf
    prev_v = v_start
    for _ in range(200):
        ode.step(stress=1.0, dt=0.1)
        trajectory.append((ode.level, ode.desensitization))
        curr_v = ode._lyapunov(ode.level, ode.desensitization)
        worst_increment = max(worst_increment, curr_v - prev_v)
        prev_v = curr_v
    v_end = ode._lyapunov(ode.level, ode.desensitization)
    assert not ode.verify_lyapunov(trajectory), (
        f"INV-5HT1 CONTROL FAILED: verify_lyapunov accepted a V-raising drive "
        f"expected a non-zero stress that pushes level off target to break descent. "
        f"V(l,d)=0.5*(l-target)^2+lambda*d^2 must rise under exogenous drive. "
        f"V0={v_start:.5f}, Vend={v_end:.5f}, worst_increment={worst_increment:.3e}"
    )
    assert v_end > v_start and worst_increment > 1e-9, (
        f"INV-5HT1 CONTROL DEGENERATE: V did not rise (V0={v_start:.5f}, Vend={v_end:.5f}, "
        f"worst_increment={worst_increment:.3e}) "
        f"expected the driving stress to genuinely increase the Lyapunov energy. "
        f"Negative control must exhibit the violation it guards against. "
        f"stress=1.0, steps=200, dt=0.1"
    )
