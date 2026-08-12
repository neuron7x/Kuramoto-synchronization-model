# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Kuramoto extensions — Sakaguchi α, higher-order, explosive-sync.

Three optional research-grade extensions of the canonical Kuramoto
model used elsewhere in this module:

1. **Sakaguchi-Kuramoto** with directed weighted coupling and a
   per-edge phase-frustration parameter
   :math:`\\alpha_{ij}`:

   .. math::
      \\dot{\\theta}_i = \\omega_i
        + \\sum_{j} K_{ij} \\sin(\\theta_j - \\theta_i - \\alpha_{ij})

   See Sakaguchi & Kuramoto (1986) "A soluble active rotator model
   showing phase transitions via mutual entrainment", *Progress of
   Theoretical Physics* 76(3), 576-581.

2. **Higher-order Kuramoto** with triadic interactions:

   .. math::
      \\dot{\\theta}_i = \\omega_i
        + \\frac{K_2}{N}\\sum_j \\sin(\\theta_j - \\theta_i)
        + \\frac{K_3}{N^2}\\sum_{j,k} \\sin(2\\theta_j - \\theta_k - \\theta_i)

   The triadic term injects 3-body resonance and produces *abrupt*
   transitions in :math:`r(t)` even on regular graphs — see Skardal
   & Arenas (2019) "Abrupt desynchronization and extensive
   multistability in globally coupled oscillator simplices",
   *Physical Review Letters* 122(24):248301.

3. **Explosive-synchronization detection** via forward / reverse
   coupling sweep with hysteresis-width measurement. Source: Gómez-
   Gardeñes et al. (2011) "Explosive synchronization transitions in
   scale-free networks", *Physical Review Letters* 106(12):128701.

Pure-function API. No I/O. NumPy primitives only; no JAX
dependency.
"""

from __future__ import annotations

import math
from typing import NamedTuple

import numpy as np
from numpy.typing import NDArray

__all__ = [
    "ExplosiveSyncReport",
    "HigherOrderConfig",
    "explosive_sync_sweep",
    "kuramoto_order_parameter",
    "sakaguchi_kuramoto_step",
    "triadic_kuramoto_step",
]


def kuramoto_order_parameter(theta: NDArray[np.float64]) -> float:
    r"""Magnitude of the complex order parameter
    :math:`r e^{i\psi} = \frac{1}{N}\sum_j e^{i\theta_j}`.

    Returns ``r ∈ [0, 1]``: 0 = incoherent, 1 = perfect phase-lock.
    """
    if theta.ndim != 1 or theta.size == 0:
        raise ValueError(f"theta must be 1-D non-empty, got shape {theta.shape}")
    z = np.exp(1j * theta)
    return float(np.abs(z.mean()))


def sakaguchi_kuramoto_step(
    theta: NDArray[np.float64],
    *,
    omega: NDArray[np.float64],
    coupling: NDArray[np.float64],
    alpha: NDArray[np.float64],
    dt: float,
) -> NDArray[np.float64]:
    r"""One forward-Euler step of the Sakaguchi-Kuramoto equation.

    Parameters
    ----------
    theta
        Phase vector, shape (N,).
    omega
        Natural-frequency vector, shape (N,).
    coupling
        Directed weighted coupling matrix :math:`K_{ij}`, shape
        (N, N). ``coupling[i, j]`` is the influence *from j on i*.
    alpha
        Per-edge phase-frustration matrix :math:`\alpha_{ij}`,
        shape (N, N). For the standard Kuramoto limit pass
        ``np.zeros((N, N))``.
    dt
        Time step (must be > 0).

    Returns
    -------
    NDArray[np.float64]
        Updated phase vector at ``t + dt``. Same shape as ``theta``.
    """
    n = theta.size
    if omega.shape != (n,):
        raise ValueError(f"omega shape {omega.shape} != ({n},)")
    if coupling.shape != (n, n):
        raise ValueError(f"coupling shape {coupling.shape} != ({n}, {n})")
    if alpha.shape != (n, n):
        raise ValueError(f"alpha shape {alpha.shape} != ({n}, {n})")
    if dt <= 0:
        raise ValueError(f"dt must be > 0, got {dt}")
    # Δ_ij = θ_j - θ_i (broadcasting)
    diff = theta[None, :] - theta[:, None]
    sin_term = np.sin(diff - alpha)  # element-wise frustration
    drift = omega + (coupling * sin_term).sum(axis=1)
    return np.asarray(theta + dt * drift, dtype=np.float64)


class HigherOrderConfig(NamedTuple):
    """Coupling configuration for the higher-order Kuramoto model.

    Attributes
    ----------
    k2
        Pairwise coupling strength :math:`K_2`.
    k3
        Triadic coupling strength :math:`K_3`. Set to 0 to recover
        the pure-pairwise model.
    """

    k2: float
    k3: float


def triadic_kuramoto_step(
    theta: NDArray[np.float64],
    *,
    omega: NDArray[np.float64],
    cfg: HigherOrderConfig,
    dt: float,
) -> NDArray[np.float64]:
    r"""One forward-Euler step of the higher-order Kuramoto equation.

    .. math::
       \dot{\theta}_i = \omega_i
         + \frac{K_2}{N}\sum_j \sin(\theta_j - \theta_i)
         + \frac{K_3}{N^2}\sum_{j, k} \sin(2\theta_j - \theta_k - \theta_i)

    The triadic term is computed efficiently via the trick

    .. math::
       \sum_{j,k} \sin(2\theta_j - \theta_k - \theta_i)
        = \mathrm{Im}\!\left[
            e^{-i\theta_i}\!
            \left(\sum_j e^{2i\theta_j}\right)\!
            \overline{\left(\sum_k e^{i\theta_k}\right)}
          \right]

    which reduces an :math:`O(N^3)` triple-loop to two FFT-style
    sums plus a Hadamard product, i.e. :math:`O(N)`.
    """
    n = theta.size
    if omega.shape != (n,):
        raise ValueError(f"omega shape {omega.shape} != ({n},)")
    if dt <= 0:
        raise ValueError(f"dt must be > 0, got {dt}")
    z1 = np.exp(1j * theta)
    z2 = np.exp(2.0j * theta)
    s1 = z1.sum()
    s2 = z2.sum()
    pair = (cfg.k2 / n) * np.imag(np.conj(z1) * s1)
    triad = (cfg.k3 / (n * n)) * np.imag(np.conj(z1) * s2 * np.conj(s1))
    drift = omega + pair + triad
    return np.asarray(theta + dt * drift, dtype=np.float64)


class ExplosiveSyncReport(NamedTuple):
    """Outcome of a coupling sweep used to detect explosive synchronization.

    Attributes
    ----------
    coupling_grid
        Sweep values of :math:`K` (forward sweep is increasing,
        reverse sweep is decreasing).
    r_forward
        Time-averaged order parameter on the forward sweep.
    r_reverse
        Time-averaged order parameter on the reverse sweep.
    hysteresis_width
        :math:`\\max_K |r_{\\text{forward}}(K) - r_{\\text{reverse}}(K)|`.
        A value above ``hysteresis_threshold`` indicates a
        first-order (discontinuous) transition.
    is_explosive
        ``True`` iff ``hysteresis_width >= hysteresis_threshold``.
    """

    coupling_grid: NDArray[np.float64]
    r_forward: NDArray[np.float64]
    r_reverse: NDArray[np.float64]
    hysteresis_width: float
    is_explosive: bool


def explosive_sync_sweep(
    *,
    coupling_grid: NDArray[np.float64],
    omega: NDArray[np.float64],
    adjacency: NDArray[np.float64],
    n_steps: int = 2000,
    burn_in: int = 500,
    dt: float = 0.05,
    seed: int = 42,
    hysteresis_threshold: float = 0.10,
) -> ExplosiveSyncReport:
    r"""Detect explosive synchronization via forward / reverse coupling sweep.

    For each :math:`K` in ``coupling_grid``, advance the standard
    Kuramoto dynamics on the supplied ``adjacency`` matrix for
    ``n_steps`` Euler steps, drop the first ``burn_in`` as transient,
    and time-average the order parameter :math:`r(t)` over the
    remainder. The forward sweep starts from random phases at the
    smallest :math:`K`; the reverse sweep starts from the
    high-coupling fully-synchronized state and decreases :math:`K`.

    Hysteresis between the two branches is the operational
    diagnostic of a first-order phase transition (Gómez-Gardeñes
    et al. 2011); a continuous transition has zero hysteresis.

    Parameters
    ----------
    coupling_grid
        Strictly increasing 1-D array of coupling values
        :math:`K` ≥ 0.
    omega
        Natural frequencies, shape (N,).
    adjacency
        Symmetric adjacency matrix (zero diagonal), shape (N, N).
    n_steps, burn_in, dt, seed, hysteresis_threshold
        Numerical-integration controls. ``burn_in < n_steps``
        required.

    Returns
    -------
    ExplosiveSyncReport
        Forward and reverse :math:`r` curves, hysteresis width,
        binary verdict.
    """
    if coupling_grid.ndim != 1 or coupling_grid.size < 3:
        raise ValueError(
            f"coupling_grid must be 1-D with >= 3 entries; got shape {coupling_grid.shape}"
        )
    if np.any(np.diff(coupling_grid) <= 0):
        raise ValueError("coupling_grid must be strictly increasing")
    n = omega.size
    if adjacency.shape != (n, n):
        raise ValueError(f"adjacency shape {adjacency.shape} != ({n}, {n})")
    if not np.allclose(np.diagonal(adjacency), 0.0):
        raise ValueError("adjacency diagonal must be 0")
    if burn_in >= n_steps:
        raise ValueError(f"burn_in {burn_in} must be < n_steps {n_steps}")
    if hysteresis_threshold <= 0:
        raise ValueError(f"hysteresis_threshold must be > 0, got {hysteresis_threshold}")

    rng = np.random.default_rng(seed)
    alpha_zero = np.zeros((n, n), dtype=np.float64)

    def _sweep(
        ks: NDArray[np.float64], theta0: NDArray[np.float64]
    ) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        r_curve = np.zeros(ks.size, dtype=np.float64)
        theta = theta0.copy()
        for idx, k in enumerate(ks):
            coupling = k * adjacency / max(n - 1, 1)
            r_t = np.zeros(n_steps - burn_in, dtype=np.float64)
            for step in range(n_steps):
                theta = sakaguchi_kuramoto_step(
                    theta,
                    omega=omega,
                    coupling=coupling,
                    alpha=alpha_zero,
                    dt=dt,
                )
                if step >= burn_in:
                    r_t[step - burn_in] = kuramoto_order_parameter(theta)
            r_curve[idx] = float(r_t.mean())
        return r_curve, theta

    # Forward sweep: random initial phases.
    theta_init = rng.uniform(-math.pi, math.pi, n)
    r_forward, theta_top = _sweep(coupling_grid, theta_init)

    # Reverse sweep: continue from the top-K synchronized state.
    r_reverse_descending, _ = _sweep(coupling_grid[::-1], theta_top)
    r_reverse = r_reverse_descending[::-1]

    width = float(np.max(np.abs(r_forward - r_reverse)))
    return ExplosiveSyncReport(
        coupling_grid=coupling_grid.copy(),
        r_forward=r_forward,
        r_reverse=r_reverse,
        hysteresis_width=width,
        is_explosive=bool(width >= hysteresis_threshold),
    )
