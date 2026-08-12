# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T9 — Kuramoto sub/supercritical witnesses for INV-K2 and INV-K3.

The Kuramoto mean-field transition at K = K_c = 2/(π·g(0)) is the
single most important falsification target in this stack. A working
engine must land on the two asymptotic predictions simultaneously:

* **INV-K2 — subcritical decay**: for K well below K_c, the order
  parameter settles at the finite-size noise floor, bounded by
  ε = C/√N with C ∈ [2, 3] (the tolerance comes straight out of the
  catalog's ``epsilon`` parameter for INV-K2).

* **INV-K3 — supercritical order**: for K well above K_c, the order
  parameter stabilises at R∞ > 0 and the trajectory's standard
  deviation in the late-time window is small relative to its mean,
  i.e. the system actually reached a synchronised steady state.

Both witnesses call the production ``core.kuramoto.engine.KuramotoEngine``
over a 15-second integration window (dt=0.01, steps=1500) with a seeded
Gaussian frequency distribution so the tests are deterministic across
runs and platforms. K_c is computed analytically from the Gaussian
density (never hard-coded) so the witness also traps regressions in the
critical-coupling constant.
"""

from __future__ import annotations

import math

import numpy as np

from core.kuramoto.config import KuramotoConfig
from core.kuramoto.engine import KuramotoEngine

_N_OSCILLATORS = 512
_STEPS = 1500
_DT = 0.01
_SEED = 17
_SIGMA_OMEGA = 1.0  # Gaussian ω ~ N(0, 1): g(0) = 1/√(2π), K_c = 2·√(2π)/π


def _critical_coupling_gaussian(sigma: float) -> float:
    """Analytic K_c for a Gaussian frequency distribution with std ``sigma``.

    Kuramoto (1984): K_c = 2/(π·g(0)). For g(ω) = N(0, σ²) the peak is
    g(0) = 1/(σ·√(2π)) and so K_c = 2·σ·√(2π)/π.
    """
    return 2.0 * sigma * math.sqrt(2.0 * math.pi) / math.pi


def _run_kuramoto(coupling: float, seed: int) -> np.ndarray:
    """Integrate one Kuramoto trajectory and return the R(t) array."""
    rng = np.random.default_rng(seed)
    omega = rng.normal(loc=0.0, scale=_SIGMA_OMEGA, size=_N_OSCILLATORS)
    theta0 = rng.uniform(-math.pi, math.pi, size=_N_OSCILLATORS)
    cfg = KuramotoConfig(
        N=_N_OSCILLATORS,
        K=coupling,
        omega=omega,
        theta0=theta0,
        dt=_DT,
        steps=_STEPS,
        seed=seed,
    )
    return KuramotoEngine(cfg).run().order_parameter


def test_subcritical_order_parameter_decays_below_finite_size_bound() -> None:
    """INV-K2: K ≪ K_c ⟹ R(t→∞) ≤ C/√N with C ∈ [2, 3].

    Runs the production Kuramoto engine at K = 0.3·K_c on a Gaussian
    frequency ensemble of N=512 oscillators, takes the mean over the
    last 500 steps (the trajectory tail after burn-in), and asserts it
    sits below the finite-size noise floor 3/√N documented in the
    catalog's ``epsilon`` parameter for INV-K2.
    """
    critical_coupling = _critical_coupling_gaussian(_SIGMA_OMEGA)
    coupling = 0.3 * critical_coupling
    trajectory = _run_kuramoto(coupling=coupling, seed=_SEED)

    # Take the steady-state tail — last third of the run — so the
    # measurement is an asymptotic claim, not a transient snapshot.
    tail_R = trajectory[-500:]
    r_mean = float(np.mean(tail_R))
    r_max = float(np.max(tail_R))

    # Tolerance from the law: epsilon = C/√N with C=3 (the strict end of
    # the catalog's C ∈ [2, 3] interval). Derived here, never invented.
    epsilon = 3.0 / math.sqrt(_N_OSCILLATORS)

    assert r_mean < epsilon, (
        f"INV-K2 VIOLATED: ⟨R⟩_tail={r_mean:.6f} > ε={epsilon:.6f} "
        f"at K={coupling:.4f}=0.3·K_c, K_c={critical_coupling:.4f}. "
        f"Expected subcritical R to sit at the finite-size noise floor C/√N. "
        f"Observed at N={_N_OSCILLATORS}, steps={_STEPS}, dt={_DT}, seed={_SEED}. "
        f"Physical reasoning: below K_c the Kuramoto mean-field has no "
        f"macroscopic coherent cluster; residual R is O(1/√N) noise."
    )
    assert r_max < 2.0 * epsilon, (
        f"INV-K2 VIOLATED (tail excursion): max R={r_max:.6f} > 2ε={2 * epsilon:.6f} "
        f"at K={coupling:.4f}=0.3·K_c. "
        f"Expected tail excursions bounded by 2·(C/√N) in the subcritical regime. "
        f"Observed at N={_N_OSCILLATORS}, steps={_STEPS}, seed={_SEED}. "
        f"Physical reasoning: finite-size fluctuations have bounded amplitude "
        f"around the noise floor; a tail spike to 2ε indicates a partial "
        f"coherent cluster is forming, which is impossible below K_c."
    )


def test_supercritical_order_parameter_converges_above_zero() -> None:
    """INV-K3: K ≫ K_c ⟹ R(t→∞) = R∞ > 0 with bounded tail dispersion.

    Runs the engine at K = 2.0·K_c. The late-time R must sit well
    above the finite-size noise floor and must be stable (std ≪ mean)
    to count as a genuine synchronised steady state, not a transient.
    """
    critical_coupling = _critical_coupling_gaussian(_SIGMA_OMEGA)
    coupling = 2.0 * critical_coupling
    trajectory = _run_kuramoto(coupling=coupling, seed=_SEED)

    tail_R = trajectory[-500:]
    r_mean = float(np.mean(tail_R))
    r_std = float(np.std(tail_R))

    # Theoretical lower bound: must clear the subcritical noise floor by
    # at least a factor of 5 to rule out the "edge of transition" regime.
    noise_floor_epsilon = 3.0 / math.sqrt(_N_OSCILLATORS)
    supercritical_minimum = 5.0 * noise_floor_epsilon

    assert r_mean > supercritical_minimum, (
        f"INV-K3 VIOLATED: ⟨R⟩_tail={r_mean:.6f} ≤ 5ε={supercritical_minimum:.6f} "
        f"at K={coupling:.4f}=2·K_c, K_c={critical_coupling:.4f}. "
        f"Expected R ≫ C/√N deep in the supercritical regime. "
        f"Observed at N={_N_OSCILLATORS}, steps={_STEPS}, dt={_DT}, seed={_SEED}. "
        f"Physical reasoning: above K_c a macroscopic coherent cluster forms "
        f"and R must sit far above the finite-size noise floor."
    )
    # Stability: the tail must have settled. std/mean ≤ 0.1 is the
    # canonical "reached steady state" threshold for Kuramoto R.
    rel_dispersion = r_std / r_mean
    dispersion_budget = 0.1
    assert rel_dispersion <= dispersion_budget, (
        f"INV-K3 VIOLATED (not stabilised): std/mean={rel_dispersion:.4f} > "
        f"budget={dispersion_budget}. "
        f"Expected late-time R to have settled with std/mean ≤ 0.1. "
        f"Observed at K={coupling:.4f}=2·K_c, N={_N_OSCILLATORS}, "
        f"steps={_STEPS}, seed={_SEED}. "
        f"Physical reasoning: a genuine synchronised steady state has "
        f"small fluctuations relative to its macroscopic order parameter."
    )
