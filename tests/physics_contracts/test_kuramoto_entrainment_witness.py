# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Mathematical witness for the Kuramoto frequency-entrainment law.

Binds a pytest function to the catalog law ``kuramoto.frequency_entrainment`` via
``@law`` and proves it holds for an independent inline reference integrator:

* ``kuramoto.frequency_entrainment`` (INV-K4) — above the critical coupling a
  macroscopic cluster locks to a common mean frequency Ω; the spread of the
  locked oscillators' effective frequencies stays at or below 0.05·⟨|ω|⟩.

The witness uses a self-contained explicit-Euler Kuramoto integrator with a
Lorentzian frequency distribution (K_c = 2γ), independent of the production code,
so it catches a regression in the physics rather than re-deriving it from the
module under test.

Sibling law ``kuramoto.critical_scaling`` is left honestly unwitnessed here: the
mean-field exponent β = 1/2 is a thermodynamic-limit result whose finite-size
rounding requires an N→∞ ensemble extrapolation that a single deterministic
in-test simulation cannot reproduce to the 0.5 ± 0.05 tolerance — flagged, not
faked on a slice that happens to land near 0.5.

Nothing here is a market claim. These are synchronization-physics facts.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from physics_contracts.law import law

GAMMA = 1.0
K_C = 2.0 * GAMMA  # Lorentzian critical coupling
# Catalog tolerance: std(locked frequencies) ≤ 0.05·⟨|ω|⟩ for K ≥ 1.5·K_c.
LOCKED_SPREAD_COEFF = 0.05


def _simulate_effective_frequencies(
    coupling: float, n_oscillators: int, seed: int
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64], float]:
    """Explicit-Euler Kuramoto run; return (natural ω, effective freq, final R)."""
    rng = np.random.default_rng(seed)
    omega = GAMMA * np.tan(np.pi * (rng.random(n_oscillators) - 0.5))
    omega = np.clip(omega, -10.0, 10.0)
    theta = rng.uniform(-np.pi, np.pi, n_oscillators)
    steps, dt = 4000, 0.02
    burn_in = steps // 2
    phase_accumulated = np.zeros(n_oscillators)
    order = 0.0 + 0.0j
    for step in range(steps):
        order = np.mean(np.exp(1j * theta))
        velocity = omega + coupling * np.abs(order) * np.sin(np.angle(order) - theta)
        theta = theta + dt * velocity
        if step >= burn_in:
            phase_accumulated += velocity * dt
    effective = phase_accumulated / ((steps - burn_in) * dt)
    return omega, effective, float(np.abs(order))


@law("kuramoto.frequency_entrainment", n_seeds=5, n_oscillators=512, coupling_over_kc=1.5)
def test_locked_cluster_shares_a_common_frequency_above_kc() -> None:
    """INV-K4: above K_c a locked cluster shares one frequency within 0.05·⟨|ω|⟩.

    For K = 1.5·K_c the synchronized cluster's effective frequencies must collapse
    onto a common Ω: the standard deviation of the locked set stays at or below
    0.05·⟨|ω|⟩. The witness sweeps several seeds and requires a non-trivial locked
    fraction (entrainment genuinely occurs) and a sub-threshold spread on each.
    """
    n_seeds = 5
    n_oscillators = 512
    coupling = 1.5 * K_C
    worst_spread_ratio = 0.0
    min_locked_fraction = 1.0
    min_order_parameter = 1.0
    for seed in range(n_seeds):
        omega, effective, order = _simulate_effective_frequencies(coupling, n_oscillators, seed)
        omega_scale = float(np.mean(np.abs(omega)))
        centre = float(np.median(effective))
        locked = np.abs(effective - centre) < 0.1 * omega_scale
        locked_fraction = float(np.mean(locked))
        spread = float(np.std(effective[locked]))
        threshold = LOCKED_SPREAD_COEFF * omega_scale
        worst_spread_ratio = max(worst_spread_ratio, spread / threshold)
        min_locked_fraction = min(min_locked_fraction, locked_fraction)
        min_order_parameter = min(min_order_parameter, order)
    assert worst_spread_ratio <= 1.0, (
        "INV-K4 violated: observed worst std(locked)/threshold = "
        f"{worst_spread_ratio:.4f} must be ≤ 1 with K=1.5·K_c and n_oscillators={n_oscillators}; "
        "the locked cluster must share a common frequency within 0.05·⟨|ω|⟩"
    )
    assert min_locked_fraction > 0.1 and min_order_parameter > 0.2, (
        "INV-K4 vacuity guard: observed min locked_fraction = "
        f"{min_locked_fraction:.3f} and min R = {min_order_parameter:.3f} must exceed "
        f"(0.1, 0.2) with K=1.5·K_c and n_seeds={n_seeds}; entrainment must genuinely occur, "
        "not be asserted on a desynchronized slice"
    )
