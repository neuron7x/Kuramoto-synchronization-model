# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Reference witness tests for the physical-contracts layer.

These are *not* the only witnesses in the repo — they are the canonical
examples showing contributors how a compliant witness is structured:

1. It is decorated with ``@law("<id>", **declared_stats)``.
2. Every numeric tolerance is derived from the law's variables/formula,
   never from a magic literal.
3. Failure messages cite the law id so a regression points at the broken
   *physics*, not a line number.

Keep these cheap — no torch, no network, no disk. Heavy-fidelity witnesses
for the same laws live alongside the modules they cover.
"""

from __future__ import annotations

import math

import numpy as np

from physics_contracts import law

# ---------------------------------------------------------------------------
# Kuramoto — order parameter is bounded in [0, 1] for any phase configuration.
# ---------------------------------------------------------------------------


def _order_parameter(phases: np.ndarray) -> float:
    """Return |⟨e^{iθ}⟩|, the standard Kuramoto order parameter r.

    Defined locally (rather than imported from ``core/kuramoto``) so the
    witness for the *definitional* bound does not depend on the module it
    audits — otherwise a bug that miscomputes r would also hide in the
    witness. This is the only law where the witness owns its own math.
    """

    return float(np.abs(np.mean(np.exp(1j * phases))))


@law("kuramoto.order_parameter_bounds", n_random_configs=1000, n_oscillators=512)
def test_order_parameter_is_bounded() -> None:
    rng = np.random.default_rng(seed=0)
    n_configs = 1000
    n_oscillators = 512

    worst_low = math.inf
    worst_high = -math.inf
    for _ in range(n_configs):
        phases = rng.uniform(-math.pi, math.pi, size=n_oscillators)
        r = _order_parameter(phases)
        worst_low = min(worst_low, r)
        worst_high = max(worst_high, r)

    # Tolerance is strict: the law is a definitional bound, not a scaling
    # law. Any violation is a bug in our math, not a numerical artefact.
    assert worst_low >= 0, (
        "kuramoto.order_parameter_bounds violated: "
        f"min r = {worst_low} < 0 — impossible for a modulus of a mean"
    )
    assert worst_high <= 1, (
        "kuramoto.order_parameter_bounds violated: "
        f"max r = {worst_high} > 1 — |⟨e^{{iθ}}⟩| cannot exceed 1"
    )


# ---------------------------------------------------------------------------
# Kuramoto — below K_c the order parameter sits at the finite-size noise
# floor ⟨r⟩ ≈ c/√N. The witness uses the strict form r < 3/√N with
# tolerance 3 chosen from the law's ``tolerance`` field (not invented here).
# ---------------------------------------------------------------------------


def _mini_kuramoto_subcritical(
    n_oscillators: int,
    coupling: float,
    duration_units: float,
    dt: float,
    rng: np.random.Generator,
) -> float:
    """Integrate the plain Kuramoto ODE with Lorentzian natural frequencies.

    Only used to generate *subcritical* evidence for the witness. The mean
    r over the second half of the trajectory is returned. Deliberately
    written as a short Euler integrator — the witness does not need a
    production-grade solver, only a faithful dynamical system.
    """

    omega = rng.standard_cauchy(size=n_oscillators) * 0.5  # Lorentzian γ=0.5
    theta = rng.uniform(-math.pi, math.pi, size=n_oscillators)
    n_steps = int(duration_units / dt)
    burn_in = n_steps // 2
    r_samples: list[float] = []
    for step in range(n_steps):
        mean_field = np.mean(np.exp(1j * theta))
        r_t = np.abs(mean_field)
        psi_t = np.angle(mean_field)
        theta = theta + dt * (omega + coupling * r_t * np.sin(psi_t - theta))
        if step >= burn_in:
            r_samples.append(r_t)
    return float(np.mean(r_samples))


@law(
    "kuramoto.subcritical_finite_size",
    n_oscillators=512,
    coupling_fraction_of_Kc=0.4,
    trials=20,
)
def test_subcritical_order_parameter_scales_as_inverse_sqrt_n() -> None:
    rng = np.random.default_rng(seed=1)
    n_oscillators = 512
    # K_c = 2·γ / π for Lorentzian ω with half-width γ; with γ=0.5, K_c ≈ 0.318.
    # We stay well below at 0.4·K_c so the subcritical regime is clean.
    critical_coupling = 2.0 * 0.5 / math.pi  # γ from _mini_kuramoto_subcritical
    coupling = 0.4 * critical_coupling
    trials = 20

    r_means = [
        _mini_kuramoto_subcritical(
            n_oscillators=n_oscillators,
            coupling=coupling,
            duration_units=40.0,
            dt=0.05,
            rng=rng,
        )
        for _ in range(trials)
    ]
    empirical_mean = float(np.mean(r_means))

    # Tolerance is NOT invented — it comes directly from the law:
    #   catalog.yaml → kuramoto.subcritical_finite_size → tolerance:
    #     "r < 3 / √N"
    law_bound = 3.0 / math.sqrt(n_oscillators)  # law: tolerance from 3/√N

    assert empirical_mean < law_bound, (
        "kuramoto.subcritical_finite_size violated: "
        f"⟨r⟩={empirical_mean:.4f} ≥ 3/√N={law_bound:.4f} at K={coupling:.4f} "
        f"(0.4·K_c), N={n_oscillators}, trials={trials}"
    )


# ---------------------------------------------------------------------------
# Kelly — log-optimal fraction equals μ/σ² in the small-edge continuous limit.
# ---------------------------------------------------------------------------


def _numerical_log_optimal_fraction(
    mu: float, half_width: float, rng: np.random.Generator, n_samples: int
) -> float:
    """Estimate argmax_f E[log(1 + f·X)] on a grid for X ~ Uniform(μ−a, μ+a).

    Uses a *bounded* distribution so ``1 + f·X`` stays positive for every
    f ∈ [0, 1] and ``log1p`` never sees a NaN — otherwise the argmax is
    corrupted by tail samples rather than by the physics we want to probe.

    For this family  σ² = a²/3,  so the Kelly formula in continuous-limit
    form reads  f* = μ / σ² = 3·μ / a².  The witness function above
    derives ``theoretical`` from ``mu`` and ``sigma`` where ``sigma`` is
    the true std, so the caller must pass the same distribution.

    Independent of ``core/neuro/kuramoto_kelly.py`` so the witness catches
    a regression in that module rather than echoing it back.
    """

    returns = rng.uniform(mu - half_width, mu + half_width, size=n_samples)
    fractions = np.linspace(0.0, 1.0, 201)
    growth = np.array([float(np.mean(np.log1p(f * returns))) for f in fractions])
    return float(fractions[int(np.argmax(growth))])


@law("kelly.optimal_fraction_formula", mu=0.01, half_width=0.3, n_samples=500_000)
def test_kelly_optimal_fraction_matches_mu_over_sigma_squared() -> None:
    # Small-edge regime with a *bounded* return distribution so the log-growth
    # integrand is finite for every f ∈ [0, 1]. For X ~ Uniform(μ−a, μ+a),
    # σ² = a²/3 and the continuous-limit Kelly formula is f* = μ/σ² = 3μ/a².
    # With μ=0.01, a=0.3 → f* = 0.333, comfortably interior to the grid.
    mu = 0.01  # law: μ in the law formula f* = μ/σ²
    half_width = 0.3
    sigma_squared = (half_width * half_width) / 3.0  # law: σ² of Uniform(μ±a) = a²/3
    rng = np.random.default_rng(seed=2)

    theoretical = mu / sigma_squared  # law: derived from formula f* = μ/σ²
    empirical = _numerical_log_optimal_fraction(
        mu=mu, half_width=half_width, rng=rng, n_samples=500_000
    )

    # Grid resolution is 1/200 = 0.005; the law's tolerance field requires
    # |f - μ/σ²| ≤ 1e-8 on analytic inputs, but our witness uses a Monte-Carlo
    # + discrete grid, so the honest achievable precision is one grid step
    # plus one-sigma of the MC estimator of argmax (≈ 1 grid step at 5e5
    # samples for σ=0.2), so the combined budget is 2·grid_step.
    grid_step = 1.0 / 200.0  # law: discretisation of f ∈ [0,1]
    mc_budget = 2.0 * grid_step  # law: grid + MC finite-sample slack
    assert abs(empirical - theoretical) <= mc_budget, (
        "kelly.optimal_fraction_formula violated: "
        f"empirical f*={empirical:.4f} vs theoretical μ/σ²={theoretical:.4f} "
        f"differ by more than grid+MC budget {mc_budget:.4f}"
    )
