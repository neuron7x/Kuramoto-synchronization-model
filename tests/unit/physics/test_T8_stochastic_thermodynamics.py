# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T8 — Exact fluctuation-theorem witnesses for stochastic thermodynamics.

Three falsification tests, one per invariant, over an overdamped Langevin
ensemble in a harmonic well ``V = ½ k x²`` (Euler-Maruyama, Sekimoto work
convention ``dW = ½ x² dk``). Pure statistical mechanics; not a market
model, no financial claim.

* ``test_INV_ST1_*`` — equipartition / Boltzmann stationary: ``Var(x) = kT/k``.
* ``test_INV_ST2_*`` — Jarzynski equality ``⟨e^(−βW)⟩ = e^(−βΔF)``.
* ``test_INV_ST3_*`` — second law ``⟨W⟩ ≥ ΔF`` and dissipation monotonic
  in protocol speed.

Fixed seeds, vectorized ensembles; total runtime < ~5 s.
"""

from __future__ import annotations

import numpy as np

from core.physics.stochastic_thermodynamics import (
    delta_free_energy,
    jarzynski_average,
    stationary_samples,
    stiffness_ramp_work,
)


def test_INV_ST1_equipartition_variance_matches_boltzmann() -> None:
    """INV-ST1: stationary Var(x) = kT/k within relative tolerance 0.10.

    Relaxes a 40000-trajectory ensemble in fixed harmonic wells and checks
    the equipartition theorem (zero-mean Boltzmann Gaussian, detailed
    balance). The relative tolerance ``tol`` = 0.10 is the registered bound;
    the measured deviation is ≈0.017 for these parameters.
    """
    kT = 1.0
    tol = 0.10  # INV-ST1 registered relative tolerance (measured ≈0.017)
    seed = 7
    for stiffness in (1.0, 2.0, 4.0):
        samples = stationary_samples(seed, k=stiffness, kT=kT)
        observed_var = float(np.var(samples))
        expected_var = kT / stiffness
        rel_dev = abs(observed_var - expected_var) / expected_var
        assert rel_dev < tol, (
            f"INV-ST1 VIOLATED: Var(x)={observed_var:.4f} vs kT/k={expected_var:.4f}, "
            f"rel_dev={rel_dev:.4f} exceeds equipartition tol={tol:.2f}. "
            f"Expected Boltzmann stationary Var(x)=kT/k by equipartition. "
            f"At k={stiffness:.1f}, kT={kT:.1f}, ensemble=40000, seed={seed}."
        )


def test_INV_ST1_equipartition_is_gamma_invariant() -> None:
    """INV-ST1: stationary Var(x) = kT/k is INDEPENDENT of friction gamma.

    Fluctuation-dissipation ties the diffusion to the friction so that the
    Boltzmann stationary variance kT/k carries no gamma dependence — gamma only
    sets the relaxation timescale gamma/k, not the equilibrium spread. This
    falsifies the regression where the Euler-Maruyama noise scale was written
    sqrt(2*gamma*kT*dt) (gamma in the numerator) instead of sqrt(2*kT*dt/gamma):
    that bug leaves Var = gamma^2 * kT/k, exact only at gamma=1 (which every
    other T8 test uses, so it was masked). At gamma=4 the broken scale inflates
    the variance ~16x.
    """
    kT = 1.0
    tol = 0.10  # same registered INV-ST1 bound; measured ≈0.017 across gamma
    seed = 7
    stiffness = 2.0
    expected_var = kT / stiffness
    for gamma in (0.5, 1.0, 2.0, 4.0):
        samples = stationary_samples(seed, k=stiffness, kT=kT, gamma=gamma)
        observed_var = float(np.var(samples))
        rel_dev = abs(observed_var - expected_var) / expected_var
        assert rel_dev < tol, (
            f"INV-ST1 VIOLATED (gamma-dependence): Var(x)={observed_var:.4f} vs "
            f"kT/k={expected_var:.4f}, rel_dev={rel_dev:.4f} exceeds tol={tol:.2f}. "
            f"Stationary variance must be gamma-invariant (fluctuation-dissipation). "
            f"At gamma={gamma:.1f}, k={stiffness:.1f}, kT={kT:.1f}, seed={seed}."
        )


def test_INV_ST2_jarzynski_equality_holds_within_tolerance() -> None:
    """INV-ST2: ⟨e^(−βW)⟩ = e^(−βΔF) within relative tolerance 0.05.

    For the harmonic stiffness ramp k_i=1 → k_f=4 (kT=1) the exact target
    is e^(−βΔF) = sqrt(k_i/k_f) = 0.5. Asserts the ensemble exponential
    work average matches across four fixed seeds. The relative tolerance
    ``tol`` = 0.05 is registered; measured deviation ≤0.004.
    """
    ki, kf, kT = 1.0, 4.0, 1.0
    tol = 0.05  # INV-ST2 registered relative tolerance (measured ≤0.004)
    target = float(np.sqrt(ki / kf))  # = e^(−βΔF) for the harmonic ramp
    dF = delta_free_energy(ki, kf, kT)
    observed_target = float(np.exp(-dF / kT))
    assert abs(observed_target - target) < 1e-12, (
        f"INV-ST2 setup: got e^(−βΔF)={observed_target:.6f} must equal "
        f"sqrt(ki/kf)={target:.6f}. Expected exact analytic agreement. "
        f"ΔF=−(1/2β)·ln(ki/kf). At ki={ki:.1f}, kf={kf:.1f}, kT={kT:.1f}."
    )
    for seed in (1, 7, 42, 123):
        work = stiffness_ramp_work(seed, ki=ki, kf=kf, kT=kT)
        jar = jarzynski_average(work, kT=kT)
        rel_dev = abs(jar - target) / target
        assert rel_dev < tol, (
            f"INV-ST2 VIOLATED: ⟨e^(−βW)⟩={jar:.4f} vs target e^(−βΔF)={target:.4f}, "
            f"rel_dev={rel_dev:.4f} exceeds Jarzynski tol={tol:.2f}. "
            f"Expected ⟨e^(−βW)⟩=e^(−βΔF)=sqrt(ki/kf) (exact equality). "
            f"At ki={ki:.1f}, kf={kf:.1f}, kT={kT:.1f}, ensemble=40000, seed={seed}."
        )


def test_INV_ST3_second_law_and_dissipation_monotonic() -> None:
    """INV-ST3: ⟨W⟩ ≥ ΔF, and ⟨W⟩(τ=2.0) < ⟨W⟩(τ=0.5) (slower dissipates less).

    The mean dissipated work bounds the free-energy change from above
    (Jensen on Jarzynski), and shrinks as the protocol is slowed toward the
    quasi-static limit. Uses a fixed seed and the registered ensemble.
    """
    ki, kf, kT, seed = 1.0, 4.0, 1.0, 42
    dF = delta_free_energy(ki, kf, kT)  # = 0.693 for the reference ramp

    work_ref = stiffness_ramp_work(seed, ki=ki, kf=kf, kT=kT, tau=1.0)
    mean_work_ref = float(np.mean(work_ref))
    assert mean_work_ref >= dF, (
        f"INV-ST3 VIOLATED: ⟨W⟩={mean_work_ref:.4f} < ΔF={dF:.4f}. "
        f"Expected second law ⟨W⟩ ≥ ΔF (Jensen on Jarzynski). "
        f"ΔF=−(1/2β)·ln(ki/kf). At ki={ki:.1f}, kf={kf:.1f}, kT={kT:.1f}, "
        f"tau=1.0, ensemble=40000, seed={seed}."
    )

    work_slow = stiffness_ramp_work(seed, ki=ki, kf=kf, kT=kT, tau=2.0)
    work_fast = stiffness_ramp_work(seed, ki=ki, kf=kf, kT=kT, tau=0.5)
    mean_slow = float(np.mean(work_slow))
    mean_fast = float(np.mean(work_fast))
    assert mean_slow < mean_fast, (
        f"INV-ST3 VIOLATED: ⟨W⟩(τ=2.0)={mean_slow:.4f} ≥ ⟨W⟩(τ=0.5)={mean_fast:.4f}. "
        f"Expected dissipation monotonic in protocol speed (slower → less work). "
        f"Both bounded below by ΔF={dF:.4f}. "
        f"At ki={ki:.1f}, kf={kf:.1f}, kT={kT:.1f}, ensemble=40000, seed={seed}."
    )
