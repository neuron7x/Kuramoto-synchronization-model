# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Mathematical witnesses for the serotonin-homeostasis laws in the catalog.

Each binds a pytest function to a first-principles catalog law via ``@law`` and
proves it holds in the real ``SerotoninODE`` integrator, deriving every tolerance
from the law. Two previously-unwitnessed laws gain witnesses:

* ``serotonin.level_bounds``      — 5-HT level stays in [0, 1] for all t
  (INV-5HT2, universal definitional bound).
* ``serotonin.lyapunov_stability`` — V(l,d) = ½(l−target)² + λd² is
  non-increasing under zero exogenous stress (INV-5HT1, monotonic).

Nothing here is a market claim. These are control-theory facts about the code.
"""

from __future__ import annotations

import numpy as np

from core.neuro.serotonin_ode import SerotoninODE, SerotoninODEParams
from physics_contracts.law import law

# Strict definitional bound — only numerical-noise slack is permitted.
LEVEL_EPS = 1e-9
# Catalog ``serotonin.lyapunov_stability`` tolerance: V(t+1) − V(t) ≤ 1e-9.
LYAPUNOV_TOLERANCE = 1e-9


@law("serotonin.level_bounds", n_initial_conditions=5, steps_per_run=500)
def test_serotonin_level_stays_bounded() -> None:
    """INV-5HT2: the 5-HT level remains in [0, 1] under any stress trajectory.

    The integrator must keep ``level`` in its biologically-valid range for every
    step, regardless of exogenous stress (including extreme positive and negative
    drive). The witness sweeps several initial conditions and a long stochastic
    stress path, tracking the worst-case excursions below 0 and above 1.
    """
    n_initial_conditions = 5
    steps_per_run = 500
    rng = np.random.default_rng(seed=0)
    worst_low = np.inf
    worst_high = -np.inf
    for init_level in np.linspace(0.0, 1.0, n_initial_conditions):
        ode = SerotoninODE(SerotoninODEParams(), level=float(init_level))
        for _ in range(steps_per_run):
            stress = float(rng.uniform(-2.0, 3.0))
            ode.step(stress, dt=1.0)
            worst_low = min(worst_low, ode.level)
            worst_high = max(worst_high, ode.level)
    assert worst_low >= 0.0 - LEVEL_EPS, (
        "INV-5HT2 violated: observed min level = "
        f"{worst_low:.6f} must be ≥ 0 (tolerance {LEVEL_EPS:.0e}) over "
        f"steps_per_run={steps_per_run} with seed=0; 5-HT concentration cannot be negative"
    )
    assert worst_high <= 1.0 + LEVEL_EPS, (
        "INV-5HT2 violated: observed max level = "
        f"{worst_high:.6f} must be ≤ 1 (tolerance {LEVEL_EPS:.0e}) over "
        f"steps_per_run={steps_per_run} with seed=0; 5-HT level saturates at 1"
    )


@law("serotonin.lyapunov_stability", n_initial_conditions=5, steps_per_run=300)
def test_serotonin_lyapunov_is_non_increasing() -> None:
    """INV-5HT1: V is non-increasing under zero exogenous stress.

    With ``stress=0`` the serotonin ODE relaxes toward (level=target, desens=0);
    the Lyapunov function V = ½(l−target)² + λd² must not increase along the
    trajectory. The witness builds a zero-stress trajectory from several initial
    conditions and checks both the integrator's own ``verify_lyapunov`` and the
    per-step difference against the catalog's numerical slack.
    """
    n_initial_conditions = 5
    steps_per_run = 300
    worst_delta_v = -np.inf
    for init_level in np.linspace(0.0, 1.0, n_initial_conditions):
        ode = SerotoninODE(SerotoninODEParams(), level=float(init_level))
        trajectory: list[tuple[float, float]] = [(ode.level, ode.desensitization)]
        prev_v = ode._lyapunov(ode.level, ode.desensitization)
        violations = 0
        for _ in range(steps_per_run):
            level, desens = ode.step(0.0, dt=0.5)
            trajectory.append((level, desens))
            curr_v = ode._lyapunov(level, desens)
            worst_delta_v = max(worst_delta_v, curr_v - prev_v)
            if curr_v > prev_v + LYAPUNOV_TOLERANCE:
                violations += 1
            prev_v = curr_v
        assert ode.verify_lyapunov(trajectory), (
            "INV-5HT1 violated: verify_lyapunov rejected a zero-stress "
            f"trajectory with violations={violations} over steps_per_run="
            f"{steps_per_run} at init=0..1; V must decrease monotonically"
        )
    assert worst_delta_v <= LYAPUNOV_TOLERANCE, (
        "INV-5HT1 violated: observed worst ΔV = "
        f"{worst_delta_v:.3e} must be ≤ {LYAPUNOV_TOLERANCE:.0e} under zero "
        f"stress over steps_per_run={steps_per_run} with seed=0; dV/dt ≤ 0 required"
    )
