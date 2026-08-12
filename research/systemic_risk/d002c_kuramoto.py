# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002C — Minimal Kuramoto integrator over a substrate K-trajectory.

Shared infrastructure consumed by:

  * :mod:`d002c_crn_validator` (C2.3) — Common-Random-Numbers
    variance-reduction GO/NO-GO measurement
  * :mod:`d002c_sweep_runner` (C2.4, pending) — the full Signal
    Amplification Sweep driver

API surface
===========
A single pure function :func:`simulate_kuramoto` that takes a
substrate K-trajectory of shape ``(T_quarters, N, N)`` and a
seed, and returns a :class:`d002c_metrics.KuramotoTrajectory`
sampled at ``steps_per_quarter`` resolution. Determinism is
strict: same ``(K, seed, config)`` produces bit-exact identical
output across calls, processes, and machines.

Numerical method
================
Heun's method (improved Euler / 2nd order Runge-Kutta) on the
Kuramoto ODE

    dθ_i/dt = ω_i + (1/N) Σ_j K_ij sin(θ_j - θ_i)

with K constant inside each quarter (block-constant over t).
Heun's method costs ~2× Euler per step but cuts the local
truncation error from O(dt²) to O(dt³); for the steps-per-
quarter regime we use (≥10), this is comfortably accurate
without resorting to RK4.

ω is drawn from a Lorentzian (Cauchy) distribution with scale
``omega_gamma`` (default 0.5). Initial phases θ(0) are drawn
uniformly from [-π, π). Both draws are seeded by the same RNG
key so a single seed fully determines a realisation.

Strict scope
============
Integrator only. NO metric evaluation. NO CRN bookkeeping.
NO claim layer. Output is a frozen
:class:`KuramotoTrajectory`.
"""

from __future__ import annotations

import math
from typing import Final

import numpy as np
from numpy.typing import NDArray

from .d002c_metrics import KuramotoTrajectory

# Default integrator hyperparameters
DEFAULT_STEPS_PER_QUARTER: Final[int] = 10
DEFAULT_OMEGA_GAMMA: Final[float] = 0.5  # Lorentzian scale


class IntegratorInvalid(RuntimeError):
    """Bad input to :func:`simulate_kuramoto`."""


def _draw_lorentzian(rng: np.random.Generator, *, size: int, gamma: float) -> NDArray[np.float64]:
    """Draw `size` samples from Cauchy(0, gamma) using the inverse-CDF method.

    rng.standard_cauchy() would also work but its tail is uncontrolled —
    the inverse-CDF form keeps us deterministic in numpy's PCG64 state
    while letting us clip extreme tails if we ever choose to.
    """
    u = rng.random(size=size, dtype=np.float64)
    # Inverse Cauchy CDF: γ tan(π (U − 1/2))
    return gamma * np.tan(np.pi * (u - 0.5))


def _kuramoto_rhs(
    theta: NDArray[np.float64],
    omega: NDArray[np.float64],
    K: NDArray[np.float64],
    *,
    N: int,
) -> NDArray[np.float64]:
    """Right-hand side of the Kuramoto ODE: dθ/dt at the given state."""
    # diff[i, j] = θ_j - θ_i
    diff = theta[None, :] - theta[:, None]
    coupling = (K * np.sin(diff)).sum(axis=1) / float(N)
    rhs: NDArray[np.float64] = (omega + coupling).astype(np.float64, copy=False)
    return rhs


def simulate_kuramoto(
    K_trajectory: NDArray[np.float64],
    *,
    seed: int,
    steps_per_quarter: int = DEFAULT_STEPS_PER_QUARTER,
    omega_gamma: float = DEFAULT_OMEGA_GAMMA,
    record_theta: bool = True,
) -> KuramotoTrajectory:
    """Integrate the Kuramoto ODE on the supplied K-trajectory.

    Parameters
    ----------
    K_trajectory
        Shape ``(T_quarters, N, N)``. K is block-constant inside each
        quarter; the integrator uses ``K_trajectory[step //
        steps_per_quarter]`` at each inner step.
    seed
        Seeds the random ω draw, the initial-phase draw, and any
        downstream non-determinism. A single seed fully specifies a
        realisation.
    steps_per_quarter
        Inner integration steps per quarter. Total trajectory length
        is ``T_quarters * steps_per_quarter``. Default 10 — the
        smallest value that produces stable Heun integration on a
        Kuramoto at critical onset (verified empirically; smaller
        values produce step-aliased R(t)).
    omega_gamma
        Scale of the Lorentzian natural-frequency distribution.
        ``γ = 0.5`` is the canonical choice for the Kuramoto-on-graph
        critical coupling K_c = 2γ.
    record_theta
        If False, return ``theta=None`` (saves memory for metrics
        that only consume R). Default True for back-compat with
        all three D-002C metrics.

    Returns
    -------
    KuramotoTrajectory
        Order parameter R(t) sampled every step, plus per-node
        phases θ(t, j) if requested.

    Raises
    ------
    IntegratorInvalid
        On malformed K_trajectory, non-positive steps_per_quarter,
        or non-finite omega_gamma.
    """
    if K_trajectory.ndim != 3:
        raise IntegratorInvalid(
            f"K_trajectory must be 3-D (T_quarters, N, N); got shape {K_trajectory.shape}"
        )
    T_q, N, M = K_trajectory.shape
    if M != N:
        raise IntegratorInvalid(f"K_trajectory last two axes must be square; got {N}x{M}")
    if T_q < 1 or N < 2:
        raise IntegratorInvalid(f"K_trajectory has degenerate shape (T={T_q}, N={N})")
    if not np.all(np.isfinite(K_trajectory)):
        raise IntegratorInvalid("K_trajectory contains non-finite values")
    if steps_per_quarter < 1:
        raise IntegratorInvalid(f"steps_per_quarter must be >= 1; got {steps_per_quarter}")
    if not math.isfinite(omega_gamma) or omega_gamma <= 0.0:
        raise IntegratorInvalid(f"omega_gamma must be finite and > 0; got {omega_gamma}")

    rng = np.random.default_rng(seed)
    omega = _draw_lorentzian(rng, size=N, gamma=omega_gamma)
    theta: NDArray[np.float64] = np.asarray(
        rng.uniform(-math.pi, math.pi, size=N), dtype=np.float64
    )

    total_steps = T_q * steps_per_quarter
    dt = 1.0 / float(steps_per_quarter)  # one quarter == one unit time

    R_traj = np.empty(total_steps, dtype=np.float64)
    if record_theta:
        theta_traj: NDArray[np.float64] | None = np.empty((total_steps, N), dtype=np.float64)
    else:
        theta_traj = None

    for step in range(total_steps):
        q = step // steps_per_quarter
        K = K_trajectory[q]
        # Heun's method (improved Euler / RK2)
        k1 = _kuramoto_rhs(theta, omega, K, N=N)
        theta_pred = theta + dt * k1
        k2 = _kuramoto_rhs(theta_pred, omega, K, N=N)
        theta = theta + 0.5 * dt * (k1 + k2)
        # Wrap to [-π, π) to keep float32-safe over long runs;
        # the order parameter and the metric layer are wrap-invariant.
        theta = (theta + math.pi) % (2.0 * math.pi) - math.pi
        # Record observables
        z = np.mean(np.exp(1j * theta))
        R_traj[step] = float(np.abs(z))
        if theta_traj is not None:
            theta_traj[step] = theta

    return KuramotoTrajectory(
        R=R_traj,
        theta=theta_traj,
        steps_per_quarter=steps_per_quarter,
        horizon_quarters=T_q,
    )


__all__ = [
    "DEFAULT_STEPS_PER_QUARTER",
    "DEFAULT_OMEGA_GAMMA",
    "IntegratorInvalid",
    "simulate_kuramoto",
]
