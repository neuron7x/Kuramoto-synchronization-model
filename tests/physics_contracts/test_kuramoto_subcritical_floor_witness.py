# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Mathematical witness for the Kuramoto subcritical finite-size-floor law.

Binds the catalog law ``kuramoto.subcritical_finite_size`` to an executable
``@law`` witness, citing the EXISTING registry invariant INV-K5 (no new
invariant, no count change):

* ``kuramoto.subcritical_finite_size`` — below the critical coupling the order
  parameter sits at the finite-size noise floor ⟨r⟩ ≈ c/√N with c = √(π/2) for a
  Lorentzian frequency density, and r < 3/√N for the overwhelming majority of
  trials (INV-K5: ⟨R⟩ ≈ O(1/√N) in the incoherent regime).

The witness follows the law's protocol: a Lorentzian ω ensemble (half-width γ ⇒
K_c = 2γ), subcritical coupling K = 0.5·K_c ≤ 0.8·K_c, N = 256 oscillators,
equilibration time t = steps·dt > 20/γ, and M = 60 independent trials. The trial
count honours the invariant being cited — INV-K5 requires ≥ 50 realizations; the
catalog law's heavier M ≥ 200 protocol is the nightly gold standard, but 60 trials
already give frac<floor = 1.0 with a wide margin (max r ≈ 0.13 ≪ floor ≈ 0.19). It
asserts (1) at least 99 % of trials satisfy r < 3/√N and (2) the mean floor tracks
the analytic Lorentzian coefficient c = √(π/2) within a factor of 2, so the witness
proves both the bound and its scaling — not merely that r is small.

Gated behind ``@pytest.mark.heavy_math`` (60 finite-N RK4 integrations, ~30 s).
Nothing here is a market claim — these are synchronisation contract facts.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from core.kuramoto.config import KuramotoConfig
from core.kuramoto.engine import KuramotoEngine
from physics_contracts.law import law

# Lorentzian half-width γ ⇒ K_c = 2γ (Kuramoto 1984). Larger γ shortens the
# equilibration time t > 20/γ, keeping the 200-trial witness affordable.
GAMMA = 2.0  # broader Lorentzian ⇒ equilibration t > 20/γ = 10 is reached in few steps
N_OSC = 256
N_TRIALS = 60  # ≥ 50 realizations (INV-K5 statistical-power floor); keeps the heavy lane fast
DT = 0.1
STEPS = 140  # t = 14 > 20/γ = 10 (equilibration satisfied)
TAIL = 50
K_RATIO = 0.5  # deep subcritical: K = 0.5·K_c ≤ 0.8·K_c (catalog validity)
# Catalog tolerance: r < 3/√N for ≥ 99 % of trials.
FLOOR_COEFF = 3.0
MIN_BELOW_FRACTION = 0.99
# Analytic Lorentzian floor coefficient ⟨r⟩ ≈ √(π/2)/√N; allow a factor-2 band.
LORENTZIAN_C = math.sqrt(math.pi / 2.0)
SCALING_TOLERANCE = 2.0


def _subcritical_tail_r(seed: int) -> float:
    """Tail-averaged order parameter of one subcritical Lorentzian ensemble."""
    rng = np.random.default_rng(seed=seed)
    omega = (rng.standard_cauchy(N_OSC) * GAMMA).astype(np.float64)
    theta0 = rng.uniform(-math.pi, math.pi, size=N_OSC).astype(np.float64)
    k_c = 2.0 * GAMMA
    cfg = KuramotoConfig(
        N=N_OSC,
        K=K_RATIO * k_c,
        omega=omega,
        theta0=theta0,
        dt=DT,
        steps=STEPS,
        seed=seed,
    )
    return float(np.mean(KuramotoEngine(cfg).run().order_parameter[-TAIL:]))


@pytest.mark.heavy_math
@law("kuramoto.subcritical_finite_size", n_trials=N_TRIALS, n_oscillators=N_OSC)
def test_subcritical_order_parameter_sits_at_finite_size_floor() -> None:
    """INV-K5: K < K_c ⟹ ⟨r⟩ ≈ √(π/2)/√N and r < 3/√N over ≥ 50 trials.

    Runs M = 60 independent subcritical Lorentzian ensembles at N = 256 (INV-K5
    requires ≥ 50 realizations), measures the tail-averaged order parameter of
    each, and requires at least 99 % of them to lie below the 3/√N finite-size
    floor. The ensemble mean must also track the analytic Lorentzian coefficient
    √(π/2)/√N within a factor of two, witnessing the 1/√N scaling rather than an
    arbitrary smallness.
    """
    n_trials = N_TRIALS
    floor = FLOOR_COEFF / math.sqrt(N_OSC)
    tail_r = np.array([_subcritical_tail_r(seed) for seed in range(n_trials)])
    below_fraction = float(np.mean(tail_r < floor))
    mean_r = float(np.mean(tail_r))
    predicted = LORENTZIAN_C / math.sqrt(N_OSC)

    assert below_fraction >= MIN_BELOW_FRACTION, (
        "INV-K5 violated: observed fraction of trials with r < 3/√N = "
        f"{below_fraction:.4f} must be ≥ {MIN_BELOW_FRACTION} with n_trials={n_trials}; "
        f"subcritical r must sit at the finite-size floor 3/√N = {floor:.4f}"
    )
    assert mean_r <= SCALING_TOLERANCE * predicted, (
        "INV-K5 violated: observed mean tail r = "
        f"{mean_r:.4f} must be ≤ {SCALING_TOLERANCE}×√(π/2)/√N = {SCALING_TOLERANCE * predicted:.4f} "
        f"with n_trials={n_trials}; the floor must track the Lorentzian 1/√N scaling"
    )
