# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
r"""Exact stochastic-thermodynamics primitives for the overdamped Langevin.

This module supplies the *fluctuation-theorem* layer that the GeoSync
physics kernel was missing. The existing thermodynamics machinery
(:mod:`core.physics.thermodynamics`, :mod:`core.physics.free_energy_variational`,
:mod:`core.physics.landauer`) covers equilibrium free energy, the Landauer
bound, and variational free energy, but contained **no** non-equilibrium
fluctuation theorem — no Jarzynski equality, no Crooks relation, no
detailed-balance / equipartition witness. This module closes that gap with
closed-form, exactly-testable statistical mechanics.

Physical model
--------------

A single overdamped degree of freedom :math:`x` in a time-dependent
harmonic potential :math:`V(x, t) = \tfrac{1}{2} k(t)\, x^2`, evolving by
the overdamped Langevin equation (mobility :math:`1/\gamma`):

.. math::

    \mathrm{d}x = -\frac{1}{\gamma} V'(x, t)\, \mathrm{d}t
                  + \sqrt{\frac{2 k_B T}{\gamma}}\, \mathrm{d}W_t .

Integrated with Euler-Maruyama at step ``dt``:

.. math::

    x \leftarrow x - \frac{\mathrm{d}t}{\gamma} k\, x
                 + \sqrt{2 k_B T\, \mathrm{d}t / \gamma}\; \mathcal N(0, 1).

The equilibrium free energy of the harmonic well is the Gaussian
partition-function result

.. math::

    F(k) = -\frac{1}{2\beta}\,\ln\!\frac{2\pi}{\beta k},
    \qquad \beta = \frac{1}{k_B T},

so a stiffness ramp :math:`k_i \to k_f` has the *exact* free-energy
difference

.. math::

    \Delta F = -\frac{1}{2\beta}\,\ln\frac{k_i}{k_f}.

Work along a protocol is accumulated in the Sekimoto stochastic-energetics
convention: at each step the protocol parameter advances at *fixed*
configuration, and the work increment is the resulting change of potential
energy,

.. math::

    \mathrm{d}W = \frac{\partial V}{\partial k}\,\mathrm{d}k
                = \tfrac12\, x^2\, \mathrm{d}k .

The Jarzynski equality then holds *exactly* in expectation over the
non-equilibrium work distribution, for an arbitrarily fast protocol:

.. math::

    \big\langle e^{-\beta W} \big\rangle = e^{-\beta \Delta F},

and the second law follows by Jensen's inequality,
:math:`\langle W \rangle \ge \Delta F`, with the gap (mean dissipated work)
shrinking as the protocol is slowed toward the quasi-static limit.

This is pure statistical mechanics. It is **not** a market model and emits
no market claim — the only inputs are a stiffness schedule, a temperature,
and a random seed.

Public surface
--------------

* :func:`harmonic_free_energy` — closed-form :math:`F(k)`.
* :func:`delta_free_energy` — closed-form :math:`\Delta F(k_i \to k_f)`.
* :func:`langevin_ensemble_step` — one vectorized Euler-Maruyama step of
  an ensemble in a harmonic well of given stiffness.
* :func:`stiffness_ramp_work` — ensemble **work** array for a linear
  stiffness-ramp protocol (the Jarzynski observable). Fails closed on a
  pre-ramp equipartition-witness violation (INV-ST1).
* :func:`stationary_samples` — draws from the Boltzmann stationary
  distribution by relaxing an ensemble; the equipartition witness.
* :func:`jarzynski_average` — :math:`\langle e^{-\beta W}\rangle` of a work
  array, with a fail-closed effective-sample-size underflow guard.
* :func:`equipartition_band` — the 1/√M sampling-noise band used by the
  pre-ramp equipartition witness.

All functions are pure, NumPy-vectorized, deterministic for a given seed,
and ``mypy --strict`` clean. No I/O, no hidden state.

References
----------
* Jarzynski, C. (1997). *Nonequilibrium equality for free energy
  differences.* Phys. Rev. Lett. **78**, 2690.
* Crooks, G. E. (1999). *Entropy production fluctuation theorem and the
  nonequilibrium work relation for free energy differences.* Phys. Rev. E
  **60**, 2721.
* Sekimoto, K. (1998). *Langevin equation and thermodynamics.* Prog. Theor.
  Phys. Suppl. **130**, 17 (stochastic energetics / work convention).
"""

from __future__ import annotations

from typing import Final

import numpy as np
import numpy.typing as npt

__all__ = [
    "harmonic_free_energy",
    "delta_free_energy",
    "langevin_ensemble_step",
    "stiffness_ramp_work",
    "stationary_samples",
    "jarzynski_average",
    "equipartition_band",
]

FloatArray = npt.NDArray[np.float64]

# Default protocol parameters reproduce the verified reference run:
# seeds {1, 7, 42, 123} give ⟨e^{-βW}⟩ ∈ [0.498, 0.500] vs target 0.5000.
_DEFAULT_ENSEMBLE: Final[int] = 40_000
_DEFAULT_TAU: Final[float] = 1.0
_DEFAULT_DT: Final[float] = 0.005

# Pre-ramp equipartition witness (INV-ST1) band.
#
# For x ~ N(0, σ²) with σ² = kT/k_i, the unbiased sample-variance estimator
# s² has, by the χ²_{M-1} sampling law, relative standard error
#
#     SE[s²] / σ² = sqrt( 2 / (M - 1) ),
#
# so the band on the relative deviation |s² − σ²|/σ² is grounded in 1/√M
# (Monte-Carlo sampling noise), NOT a hand-tuned constant. We fail closed at
# ``_EQUIPARTITION_NSIGMA`` standard errors: a draw whose variance lands beyond
# that band signals a mis-specified initial ensemble (wrong σ², a degenerate
# RNG, or a broken kT/k_i scaling) and is rejected before any work accrues.
#
# The witness requires a minimum ensemble: below ``_EQUIPARTITION_MIN_ENSEMBLE``
# the 6-σ band exceeds 100 % of σ² and the test would be vacuous (it could not
# distinguish a correct draw from a grossly wrong one), so we refuse to run the
# Jarzynski protocol on an ensemble too small to carry the witness.
_EQUIPARTITION_NSIGMA: Final[float] = 6.0
_EQUIPARTITION_MIN_ENSEMBLE: Final[int] = 100

# Jarzynski exponential-average outlier guard (INV-ST2 numerical hygiene).
#
# ⟨e^{−βW}⟩ is dominated by the rare low-W tail. If a handful of extreme-low
# samples carry essentially all the weight, the estimator is statistically
# under-resolved (its variance is governed by a few draws, not M of them).
# We measure the normalised effective sample size
#
#     ESS / M = (Σ wᵢ)² / (M · Σ wᵢ²),   wᵢ = e^{−β(Wᵢ − W_min)},
#
# and emit a guard when the effective fraction collapses below this floor, so
# silent tail-underflow cannot masquerade as convergence.
_JARZYNSKI_MIN_ESS_FRACTION: Final[float] = 1.0e-3


def _validate_positive(name: str, value: float) -> None:
    """Fail-closed guard: physical scales must be strictly positive and finite."""
    if not np.isfinite(value) or value <= 0.0:
        raise ValueError(f"{name} must be a positive finite float, got {value!r}")


def equipartition_band(ensemble: int, *, n_sigma: float = _EQUIPARTITION_NSIGMA) -> float:
    r"""Relative-deviation band for the pre-ramp equipartition witness (INV-ST1).

    Returns ``n_sigma · sqrt(2 / (ensemble − 1))``, the ``n_sigma``-standard-error
    band on the relative deviation of the sample variance from ``kT/k`` for a
    Gaussian ensemble of size ``ensemble``. This is the 1/√M Monte-Carlo
    sampling-noise scale, not a tuned tolerance.

    Parameters
    ----------
    ensemble:
        Number of independent samples ``M`` (must be ≥ 2).
    n_sigma:
        Number of sampling standard errors for the fail-closed band.
    """
    if ensemble < 2:
        raise ValueError(f"ensemble must be ≥ 2 for a variance band, got {ensemble!r}")
    return float(n_sigma) * float(np.sqrt(2.0 / (ensemble - 1)))


def _assert_equipartition(
    x: FloatArray,
    *,
    expected_var: float,
    n_sigma: float = _EQUIPARTITION_NSIGMA,
    context: str,
) -> None:
    r"""Fail-closed INV-ST1 witness on a drawn ensemble (raises ``ValueError``).

    Checks that ``Var(x)`` matches the equipartition value ``expected_var =
    kT/k`` within the 1/√M sampling band. Used as the *pre-ramp* witness so a
    mis-initialised Jarzynski ensemble is rejected before any work accrues.
    """
    ensemble = int(x.shape[0])
    if ensemble < _EQUIPARTITION_MIN_ENSEMBLE:
        raise ValueError(
            f"INV-ST1 witness requires ensemble ≥ {_EQUIPARTITION_MIN_ENSEMBLE} "
            f"to be non-vacuous (the {n_sigma:.0f}-σ band exceeds 100 % below it), "
            f"got ensemble={ensemble} for {context}."
        )
    observed_var = float(np.var(x))
    rel_dev = abs(observed_var - expected_var) / expected_var
    band = equipartition_band(ensemble, n_sigma=n_sigma)
    if not (rel_dev < band):
        raise ValueError(
            f"INV-ST1 VIOLATED ({context}): Var(x)={observed_var:.6f} vs "
            f"kT/k={expected_var:.6f}, rel_dev={rel_dev:.5f} exceeds the "
            f"{n_sigma:.0f}-σ equipartition band={band:.5f} "
            f"(= {n_sigma:.0f}·sqrt(2/(M−1)), M={ensemble}). The initial ensemble "
            f"does not match the Boltzmann equilibrium Var(x)=kT/k of the initial "
            f"well; the Jarzynski estimate would be biased. Refusing to ramp."
        )


def harmonic_free_energy(k: float, kT: float = 1.0) -> float:
    r"""Equilibrium free energy of a 1-D harmonic well :math:`V = \tfrac12 k x^2`.

    Closed form from the Gaussian partition function
    :math:`Z = \sqrt{2\pi / (\beta k)}`, :math:`F = -k_B T \ln Z`:

    .. math::

        F(k) = -\frac{1}{2\beta}\,\ln\frac{2\pi}{\beta k},
        \qquad \beta = 1/k_B T.

    Parameters
    ----------
    k:
        Harmonic stiffness, strictly positive.
    kT:
        Thermal energy :math:`k_B T`, strictly positive.

    Returns
    -------
    float
        The Helmholtz free energy :math:`F(k)` in units of :math:`k_B T`.
    """
    _validate_positive("k", k)
    _validate_positive("kT", kT)
    beta = 1.0 / kT
    return -(1.0 / (2.0 * beta)) * float(np.log(2.0 * np.pi / (beta * k)))


def delta_free_energy(ki: float, kf: float, kT: float = 1.0) -> float:
    r"""Exact free-energy difference of a stiffness change :math:`k_i \to k_f`.

    .. math::

        \Delta F = F(k_f) - F(k_i)
                 = -\frac{1}{2\beta}\,\ln\frac{k_i}{k_f}.

    The :math:`2\pi` and :math:`\beta` factors of the partition function
    cancel, leaving the clean log-stiffness-ratio form. For the reference
    ramp :math:`k_i=1 \to k_f=4`, :math:`kT=1`, this is
    :math:`\tfrac12\ln 4 \approx 0.693`, and :math:`e^{-\beta\Delta F} =
    \sqrt{k_i/k_f} = 0.5`.

    Parameters
    ----------
    ki, kf:
        Initial and final stiffness, both strictly positive.
    kT:
        Thermal energy :math:`k_B T`, strictly positive.
    """
    _validate_positive("ki", ki)
    _validate_positive("kf", kf)
    _validate_positive("kT", kT)
    beta = 1.0 / kT
    return -(1.0 / (2.0 * beta)) * float(np.log(ki / kf))


def langevin_ensemble_step(
    x: FloatArray,
    *,
    k: float,
    dt: float,
    kT: float,
    gamma: float,
    rng: np.random.Generator,
) -> FloatArray:
    r"""One vectorized Euler-Maruyama step in a harmonic well of stiffness ``k``.

    Advances every trajectory in the ensemble ``x`` by

    .. math::

        x \leftarrow x - \frac{\mathrm{d}t}{\gamma} k\, x
                     + \sqrt{2 k_B T\, \mathrm{d}t / \gamma}\; \mathcal N(0, 1).

    Parameters
    ----------
    x:
        Ensemble of positions, shape ``(M,)``.
    k:
        Current harmonic stiffness, strictly positive.
    dt:
        Integration timestep, strictly positive.
    kT:
        Thermal energy, strictly positive.
    gamma:
        Friction coefficient, strictly positive.
    rng:
        Seeded NumPy generator providing the thermal noise.

    Returns
    -------
    FloatArray
        The advanced ensemble, same shape as ``x``.
    """
    _validate_positive("k", k)
    _validate_positive("dt", dt)
    _validate_positive("kT", kT)
    _validate_positive("gamma", gamma)
    # INV-ST1: the overdamped Langevin SDE for this module is
    #   dx = -(1/gamma) V'(x) dt + sqrt(2 k_B T / gamma) dW
    # so the Euler-Maruyama diffusion scale is sqrt(2 k_B T dt / gamma) — gamma
    # in the DENOMINATOR, matching the (dt/gamma) drift below. The prior form
    # sqrt(2*gamma*kT*dt) put gamma in the numerator, which left the stationary
    # variance gamma^2-dependent (Var = gamma^2 * kT/k) instead of the
    # fluctuation-dissipation result kT/k. It happened to be exact only at the
    # gamma=1 used by every existing T8 test, so the error was masked.
    noise_scale = float(np.sqrt(2.0 * kT * dt / gamma))
    drift = (dt / gamma) * k * x
    return np.asarray(x - drift + noise_scale * rng.standard_normal(x.shape), dtype=np.float64)


def stiffness_ramp_work(
    seed: int,
    *,
    ensemble: int = _DEFAULT_ENSEMBLE,
    tau: float = _DEFAULT_TAU,
    dt: float = _DEFAULT_DT,
    ki: float = 1.0,
    kf: float = 4.0,
    kT: float = 1.0,
    gamma: float = 1.0,
) -> FloatArray:
    r"""Ensemble work array for a linear stiffness-ramp protocol.

    The protocol drives the stiffness linearly :math:`k_i \to k_f` over
    duration ``tau`` while every trajectory obeys the overdamped Langevin
    dynamics. The ensemble is initialised from the equilibrium of the
    *initial* well (:math:`\mathrm{Var}(x) = k_B T / k_i`). Work is
    accumulated in the Sekimoto convention: at each step the stiffness
    advances at fixed configuration and the work increment is the resulting
    change of potential energy,

    .. math::

        \mathrm{d}W = \tfrac12 (k_{\text{next}} - k_{\text{cur}})\, x^2 .

    Parameters
    ----------
    seed:
        Seed for the deterministic NumPy generator.
    ensemble:
        Number of independent trajectories ``M``.
    tau:
        Protocol duration. Slower ramps (larger ``tau``) dissipate less work.
    dt:
        Integration timestep.
    ki, kf:
        Initial and final stiffness.
    kT, gamma:
        Thermal energy and friction coefficient.

    Returns
    -------
    FloatArray
        Work values, shape ``(ensemble,)``. ``⟨e^{-W/kT}⟩`` equals
        :math:`e^{-\beta \Delta F}` to within the Jarzynski tolerance, and
        ``⟨W⟩ ≥ ΔF`` (second law).
    """
    _validate_positive("tau", tau)
    _validate_positive("dt", dt)
    _validate_positive("ki", ki)
    _validate_positive("kf", kf)
    _validate_positive("kT", kT)
    _validate_positive("gamma", gamma)
    if ensemble <= 0:
        raise ValueError(f"ensemble must be a positive integer, got {ensemble!r}")

    rng = np.random.default_rng(seed)
    n_steps = int(tau / dt)
    if n_steps <= 0:
        raise ValueError(f"tau/dt must yield ≥1 step, got tau={tau}, dt={dt}")

    x = rng.standard_normal(ensemble) * float(np.sqrt(kT / ki))
    # Fail-closed PRE-RAMP equipartition witness (INV-ST1): the initial ensemble
    # MUST sit at the Boltzmann equilibrium of the initial well, Var(x)=kT/k_i,
    # within the 1/√M sampling band. A mis-initialised ensemble silently biases
    # ⟨e^{−βW}⟩; we reject it before a single unit of work is accumulated.
    _assert_equipartition(
        x,
        expected_var=kT / ki,
        context=f"pre-ramp init at ki={ki}, kT={kT}, seed={seed}",
    )
    work = np.zeros(ensemble, dtype=np.float64)
    for i in range(n_steps):
        k_cur = ki + (kf - ki) * i / n_steps
        k_next = ki + (kf - ki) * (i + 1) / n_steps
        # Sekimoto work increment dW = (∂V/∂k) dk = ½ x² dk. The ½ is
        # load-bearing: dropping it (i.e. dW = x² dk, "off by a factor of 2")
        # doubles every work value and collapses ⟨e^{−βW}⟩ from 0.5 to ≈0.31
        # for the reference ramp — a ~38 % bias that the INV-ST2 anchor and the
        # factor-2 adversarial test both detect.
        work += 0.5 * (k_next - k_cur) * x * x
        x = langevin_ensemble_step(x, k=k_next, dt=dt, kT=kT, gamma=gamma, rng=rng)
    return work


def stationary_samples(
    seed: int,
    *,
    k: float,
    ensemble: int = _DEFAULT_ENSEMBLE,
    kT: float = 1.0,
    gamma: float = 1.0,
    dt: float = _DEFAULT_DT,
    relax_steps: int = 2000,
) -> FloatArray:
    r"""Draw an ensemble from the Boltzmann stationary distribution of a well.

    Initialises trajectories at the origin and relaxes them in a *fixed*
    harmonic well for ``relax_steps`` Langevin steps. After relaxation the
    ensemble is distributed as :math:`p(x) \propto e^{-\beta V(x)}`, a
    zero-mean Gaussian with the equipartition variance

    .. math::

        \mathrm{Var}(x) = \frac{k_B T}{k}.

    The relaxation timescale is :math:`\gamma / k`; the default
    ``relax_steps`` covers many such times for the reference parameters.

    Parameters
    ----------
    seed:
        Seed for the deterministic generator.
    k:
        Harmonic stiffness, strictly positive.
    ensemble:
        Number of independent trajectories.
    kT, gamma, dt:
        Thermal energy, friction, timestep.
    relax_steps:
        Number of Langevin steps used to reach stationarity.

    Returns
    -------
    FloatArray
        Stationary samples, shape ``(ensemble,)``.
    """
    _validate_positive("k", k)
    _validate_positive("kT", kT)
    _validate_positive("gamma", gamma)
    _validate_positive("dt", dt)
    if ensemble <= 0:
        raise ValueError(f"ensemble must be a positive integer, got {ensemble!r}")
    if relax_steps <= 0:
        raise ValueError(f"relax_steps must be a positive integer, got {relax_steps!r}")

    rng = np.random.default_rng(seed)
    x = np.zeros(ensemble, dtype=np.float64)
    for _ in range(relax_steps):
        x = langevin_ensemble_step(x, k=k, dt=dt, kT=kT, gamma=gamma, rng=rng)
    return x


def jarzynski_average(
    work: FloatArray,
    kT: float = 1.0,
    *,
    min_ess_fraction: float = _JARZYNSKI_MIN_ESS_FRACTION,
) -> float:
    r"""Exponential work average :math:`\langle e^{-\beta W}\rangle`.

    The Jarzynski estimator of :math:`e^{-\beta \Delta F}`. Computed in a
    shifted-exponential form for numerical stability:
    :math:`\langle e^{-\beta(W - W_{\min})}\rangle\, e^{-\beta W_{\min}}`.

    Outlier / underflow guard
    -------------------------
    ⟨e^{−βW}⟩ is dominated by the rare low-:math:`W` tail. When a handful of
    extreme-low-work samples carry essentially all the exponential weight, the
    estimator is statistically under-resolved and may silently *underflow* (the
    bulk terms round to zero, leaving the mean determined by a few draws). We
    measure the normalised effective sample size

    .. math::

        \mathrm{ESS}/M = \frac{(\sum_i w_i)^2}{M \sum_i w_i^2},
        \qquad w_i = e^{-\beta (W_i - W_{\min})},

    and raise :class:`ValueError` when it collapses below ``min_ess_fraction``.
    This is a fail-closed numerical-hygiene check: a near-zero ESS means the
    reported average is not a converged ensemble quantity and must not be
    trusted as :math:`e^{-\beta\Delta F}`.

    Parameters
    ----------
    work:
        Ensemble work array.
    kT:
        Thermal energy, strictly positive.
    min_ess_fraction:
        Minimum tolerated ESS/M before the estimator is rejected as
        tail-underflowed. The default ``1e-3`` admits the converged reference
        runs (ESS/M ≈ 0.3–0.6) while rejecting degenerate single-draw weight.
    """
    _validate_positive("kT", kT)
    if work.size == 0:
        raise ValueError("work array must be non-empty")
    if not np.all(np.isfinite(work)):
        raise ValueError("work array must be finite (no NaN/inf)")
    beta = 1.0 / kT
    w_min = float(np.min(work))
    weights = np.exp(-beta * (work - w_min))  # ∈ (0, 1], anchored at the minimum
    sum_w = float(np.sum(weights))
    sum_w2 = float(np.sum(weights * weights))
    ess_fraction = (sum_w * sum_w) / (float(work.size) * sum_w2)
    if ess_fraction < min_ess_fraction:
        raise ValueError(
            f"Jarzynski estimator under-resolved: ESS/M={ess_fraction:.2e} below "
            f"floor {min_ess_fraction:.2e}. The exponential average is carried by "
            f"a vanishing fraction of the {work.size} samples (low-W tail "
            f"underflow); ⟨e^(−βW)⟩ is not a converged ensemble quantity and is "
            f"refused. Increase the ensemble or slow the protocol."
        )
    shifted = sum_w / float(work.size)
    return shifted * float(np.exp(-beta * w_min))
