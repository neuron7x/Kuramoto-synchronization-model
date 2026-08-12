# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Mathematical witnesses for the Kuramoto phase-transition laws in the catalog.

Each binds a pytest function to a first-principles catalog law via ``@law`` and
proves it holds in the real Kuramoto stack. Two previously-unwitnessed laws gain
witnesses:

* ``kuramoto.order_parameter_bounds`` — the order parameter r = |⟨e^{iθ}⟩| is
  bounded in [0, 1] for every phase configuration, with the extremes attained
  exactly (identical phases ⇒ r = 1; this is the definitional modulus bound)
  (INV-K1). Witnessed on ``core.kuramoto.metrics.order_parameter``.
* ``kuramoto.critical_scaling`` — near the synchronisation transition the
  steady-state order parameter follows mean-field critical scaling with exponent
  β = 1/2: R_∞ = √((K − K_c)/K), so R_∞² · K = K − K_c exactly and the log–log
  slope of R_∞ versus the reduced coupling ε = (K − K_c)/K is 1/2 (INV-OA2).
  Witnessed on the exact Ott–Antonsen reduction ``OttAntonsenEngine.R_steady``.

Honest boundary on the exponent: a naïve finite-N simulation does NOT recover
β = 1/2 near K_c — the finite-size incoherent floor R ~ O(1/√N) dominates the
true critical signal, so the measured slope drifts toward 1. The exponent is a
thermodynamic-limit statement; the exact Ott–Antonsen mean-field reduction IS
that limit, which is why the witness reads β off the reduction rather than off a
noisy finite ensemble. Nothing here is a market claim — these are synchronisation
contract facts about the code.
"""

from __future__ import annotations

import numpy as np

from core.kuramoto.metrics import order_parameter
from core.kuramoto.ott_antonsen import OttAntonsenEngine
from physics_contracts.law import law

# Modulus bound is strict; only float round-off in the mean is tolerated.
ORDER_EPS = 1e-12
# Identical-phase order parameter must equal 1 to float precision.
COHERENT_EPS = 1e-12
# Exact Ott–Antonsen steady-state identity R² · K = (K − K_c) — machine precision.
IDENTITY_EPS = 1e-12
# Mean-field critical exponent and its allowed fit slack (catalog: 0.5 ± 0.05).
BETA = 0.5
BETA_SLACK = 0.05


@law("kuramoto.order_parameter_bounds", n_configs=80, max_oscillators=512)
def test_order_parameter_is_bounded_in_unit_interval() -> None:
    """INV-K1: r = |⟨e^{iθ}⟩| ∈ [0, 1] for every phase configuration.

    Fuzzes random phase matrices across a range of oscillator counts and seeds and
    requires every order-parameter value to lie in the closed unit interval. The
    coherent extreme (identical phases) must hit the upper bound exactly, proving
    the bound is tight and not merely never-approached.
    """
    n_configs = 80
    max_oscillators = 512
    worst_low = 1.0
    worst_high = 0.0
    for seed in range(n_configs):
        rng = np.random.default_rng(seed=seed)
        n_osc = int(rng.integers(2, max_oscillators + 1))
        theta = rng.uniform(-np.pi, np.pi, size=(5, n_osc))
        r = order_parameter(theta, axis=1)
        worst_low = min(worst_low, float(r.min()))
        worst_high = max(worst_high, float(r.max()))
    coherent = float(order_parameter(np.full((1, max_oscillators), 0.7), axis=1)[0])

    assert worst_low >= 0.0 - ORDER_EPS, (
        "INV-K1 violated: observed min r = "
        f"{worst_low:.6e} must be ≥ 0 (tolerance {ORDER_EPS:.0e}) "
        f"with n_configs={n_configs}; the order parameter is bounded below by 0"
    )
    assert worst_high <= 1.0 + ORDER_EPS, (
        "INV-K1 violated: observed max r = "
        f"{worst_high:.6f} must be ≤ 1 (tolerance {ORDER_EPS:.0e}) "
        f"with n_configs={n_configs}; the order parameter is bounded above by 1"
    )
    assert abs(coherent - 1.0) <= COHERENT_EPS, (
        "INV-K1 violated: observed identical-phase r = "
        f"{coherent:.12f} must equal 1 (tolerance {COHERENT_EPS:.0e}) "
        f"with max_oscillators={max_oscillators}; the upper bound must be attained exactly"
    )


@law("kuramoto.critical_scaling", n_points=200, k_window_top=1.3)
def test_critical_scaling_exponent_is_one_half() -> None:
    """INV-OA2: R_∞ = √((K − K_c)/K) ⇒ exact identity and β = 1/2.

    Uses the exact Ott–Antonsen steady state. First checks the algebraic identity
    R_∞² · K = (K − K_c) to machine precision over the window K ∈ (K_c, 1.3·K_c]
    (the strongest form of mean-field scaling). Then fits the log–log slope of R_∞
    versus the reduced coupling ε = (K − K_c)/K and requires it to equal the
    mean-field exponent β = 1/2 within the catalog slack.
    """
    n_points = 200
    k_window_top = 1.3
    delta = 0.5
    reference = OttAntonsenEngine(K=2.0, delta=delta, omega0=0.0)
    k_c = reference.K_c
    couplings = np.linspace(k_c * (1.0 + 1e-5), k_c * k_window_top, n_points)
    r_values = []
    worst_identity = 0.0
    for coupling in couplings:
        r_inf = OttAntonsenEngine(K=float(coupling), delta=delta, omega0=0.0).R_steady
        worst_identity = max(worst_identity, abs(r_inf**2 * coupling - (coupling - k_c)))
        r_values.append(r_inf)
    r_inf_arr = np.array(r_values)
    reduced = (couplings - k_c) / couplings
    slope = float(np.polyfit(np.log(reduced), np.log(r_inf_arr), 1)[0])
    min_increment = float(np.diff(r_inf_arr).min())

    assert worst_identity <= IDENTITY_EPS, (
        "INV-OA2 violated: observed worst |R²·K − (K − K_c)| = "
        f"{worst_identity:.2e} must be ≤ {IDENTITY_EPS:.0e} over n_points={n_points} "
        f"with K_c={k_c:.4f}; the exact mean-field steady state must hold to float precision"
    )
    assert min_increment > 0.0, (
        "INV-OA2 violated: observed min ΔR_∞ between adjacent couplings = "
        f"{min_increment:.2e} must be > 0 over n_points={n_points} "
        f"with K_c={k_c:.4f}; supercritical order must grow strictly monotonically in coupling"
    )
    assert abs(slope - BETA) <= BETA_SLACK, (
        "INV-OA2 violated: observed log–log slope β = "
        f"{slope:.6f} must be {BETA} ± {BETA_SLACK} over n_points={n_points} "
        f"with K_c={k_c:.4f}; mean-field critical scaling fixes the exponent at 1/2"
    )
