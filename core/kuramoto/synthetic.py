# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Synthetic Sakaguchi–Kuramoto ground-truth generator (protocol M3.1).

This module builds a :class:`~core.kuramoto.contracts.SyntheticGroundTruth`
with known ``K``, ``τ``, ``α``, ``ω`` and ``σ``, forward-simulated via
Euler–Maruyama on the delay SDE

.. math::

    \\dot\\theta_i(t) = \\omega_i + \\sum_j K_{ij}\\,
        \\sin\\bigl(\\theta_j(t - \\tau_{ij}) - \\theta_i(t) - \\alpha_{ij}\\bigr)
        + \\xi_i(t), \\qquad \\xi_i \\sim \\mathcal{N}(0, \\sigma^2).

Design choices
--------------
* **Full DDE handling.** The history buffer is kept for
  ``max(τ)`` steps so delayed lookups are always well-defined. Phases
  for ``t < 0`` are sampled from ``U(0, 2π)`` and held constant at
  ``θ(0)`` for the initial transient; analyses typically discard the
  first ``5·max(τ)`` steps to let the history flush.
* **Structured ``α``.** ``alpha_structure`` toggles between
  ``"zero"`` (standard Kuramoto), ``"symmetric"``, ``"antisymmetric"``
  (leader–follower) and ``"mixed"`` (no symmetry constraint). Different
  structures exercise different pathways in the estimators, so the
  production validation suite should call all four.
* **Deterministic under seed.** A single ``numpy.random.Generator`` is
  threaded through every randomisation step, so downstream tests can
  reproduce exact trajectories by replaying the seed.
* **Contract-native output.** Returned object is a frozen, deeply
  immutable :class:`SyntheticGroundTruth` whose ``generated_phases`` is a
  valid :class:`PhaseMatrix` in ``[0, 2π)``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from .contracts import PhaseMatrix, SyntheticGroundTruth

__all__ = [
    "AlphaStructure",
    "SyntheticConfig",
    "generate_sakaguchi_kuramoto",
]

AlphaStructure = Literal["zero", "symmetric", "antisymmetric", "mixed"]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SyntheticConfig:
    """Hyperparameters for ground-truth Sakaguchi–Kuramoto generation.

    Attributes
    ----------
    N, T : int
        Number of oscillators and simulation steps. Effective trajectory
        length after discarding the transient is ``T - burn_in``.
    dt : float
        Integration step.
    K_sparsity : float
        Probability that an off-diagonal entry of ``K`` is **zero**.
        ``0.85`` means 15 % dense, matching the methodology's default.
    K_scale : tuple[float, float]
        Uniform range for non-zero coupling weights. Signed entries are
        drawn directly; both excitatory and inhibitory edges appear.
    tau_max : int
        Maximum integer delay (in timesteps). A random integer in
        ``[0, tau_max]`` is drawn per non-zero edge.
    alpha_max : float
        Maximum absolute phase frustration in radians.
    alpha_structure : AlphaStructure
        Symmetry constraint on α (see module docstring).
    omega_center, omega_spread : float
        Natural frequencies are drawn from
        ``N(omega_center, omega_spread)``.
    sigma_noise : float
        Diffusion coefficient σ.
    burn_in : int
        Number of initial timesteps discarded so the delay buffer can
        flush. Must satisfy ``burn_in ≥ 5 * tau_max``.
    seed : int
        Master RNG seed.
    asset_prefix : str
        Prefix for generated ``asset_ids``.
    timestamps_dtype : Literal["float", "int"]
        Dtype of the returned ``timestamps`` vector.
    """

    N: int = 12
    T: int = 4000
    dt: float = 0.05
    K_sparsity: float = 0.85
    K_scale: tuple[float, float] = (0.8, 2.0)
    tau_max: int = 3
    alpha_max: float = np.pi / 6
    alpha_structure: AlphaStructure = "mixed"
    omega_center: float = 0.5
    omega_spread: float = 0.15
    sigma_noise: float = 0.05
    burn_in: int = 200
    seed: int = 0
    asset_prefix: str = "x"
    timestamps_dtype: Literal["float", "int"] = "float"

    def __post_init__(self) -> None:
        if self.N < 2:
            raise ValueError("N must be ≥ 2")
        if self.T < self.burn_in + 100:
            raise ValueError(f"T={self.T} too small; need T ≥ burn_in + 100 = {self.burn_in + 100}")
        if self.dt <= 0:
            raise ValueError("dt must be > 0")
        if not 0.0 <= self.K_sparsity <= 1.0:
            raise ValueError("K_sparsity must lie in [0, 1]")
        if self.K_scale[0] <= 0 or self.K_scale[1] <= self.K_scale[0]:
            raise ValueError("K_scale must be a valid (low, high) tuple with low > 0")
        if self.tau_max < 0:
            raise ValueError("tau_max must be ≥ 0")
        if self.burn_in < 5 * self.tau_max:
            raise ValueError(f"burn_in={self.burn_in} must be ≥ 5·tau_max={5 * self.tau_max}")
        if not 0.0 <= self.alpha_max <= np.pi:
            raise ValueError("alpha_max must lie in [0, π]")
        if self.sigma_noise < 0:
            raise ValueError("sigma_noise must be ≥ 0")


# ---------------------------------------------------------------------------
# Parameter sampling
# ---------------------------------------------------------------------------


def _sample_parameters(
    cfg: SyntheticConfig, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Draw K, τ, α, ω consistent with ``cfg``.

    ``K`` is **signed**: values are drawn from ``±U(K_scale)`` with
    balanced sign probabilities (50/50 excitatory/inhibitory). The
    sparsity mask is applied off-diagonal only. ``τ`` and ``α`` are
    zero wherever ``K`` is zero so the model retains the right degrees
    of freedom.
    """
    N = cfg.N

    # Natural frequencies
    omega = rng.normal(cfg.omega_center, cfg.omega_spread, size=N)

    # Coupling: signed weights with signed sparsity mask
    mag = rng.uniform(cfg.K_scale[0], cfg.K_scale[1], size=(N, N))
    sign = rng.choice(np.array([-1.0, 1.0]), size=(N, N))
    K = mag * sign
    mask = rng.random((N, N)) < cfg.K_sparsity
    K[mask] = 0.0
    np.fill_diagonal(K, 0.0)

    # Delays: only where K is non-zero
    tau = rng.integers(0, cfg.tau_max + 1, size=(N, N))
    np.fill_diagonal(tau, 0)
    tau[K == 0] = 0

    # Frustration: structure-dependent
    alpha_raw = rng.uniform(-cfg.alpha_max, cfg.alpha_max, size=(N, N))
    if cfg.alpha_structure == "zero":
        alpha = np.zeros((N, N))
    elif cfg.alpha_structure == "symmetric":
        alpha = 0.5 * (alpha_raw + alpha_raw.T)
    elif cfg.alpha_structure == "antisymmetric":
        alpha = 0.5 * (alpha_raw - alpha_raw.T)
    elif cfg.alpha_structure == "mixed":
        alpha = alpha_raw
    else:  # pragma: no cover - defended by dataclass validation
        raise ValueError(f"Unknown alpha_structure: {cfg.alpha_structure!r}")
    np.fill_diagonal(alpha, 0.0)
    alpha[K == 0] = 0.0

    return (
        K.astype(np.float64),
        tau.astype(np.int64),
        alpha.astype(np.float64),
        omega.astype(np.float64),
    )


# ---------------------------------------------------------------------------
# Euler–Maruyama SDDE integrator
# ---------------------------------------------------------------------------


def _simulate_sdde(
    K: np.ndarray,
    tau: np.ndarray,
    alpha: np.ndarray,
    omega: np.ndarray,
    *,
    T: int,
    dt: float,
    sigma: float,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    """Forward-simulate the Sakaguchi–Kuramoto SDDE.

    Implementation notes
    --------------------
    * **Vectorised across edges.** The drift is computed via
      ``sin(Θ_j(t - τ_{ij}) - Θ_i(t) - α_{ij})`` using advanced
      indexing into the full phase history. We pre-compute the
      per-edge lookup indices once and reuse them every step.
    * **Delay lookup is clamped.** For ``t < τ_{ij}`` we use
      ``θ_j(0)`` as the initial history (constant history). The caller
      discards ``burn_in ≥ 5·τ_max`` steps so the transient is gone
      by the time the analysis sees the trajectory.
    * **Noise term.** Standard Euler–Maruyama scaling ``σ·√dt·N(0,1)``.
    """
    N = len(omega)
    theta = np.empty((T, N), dtype=np.float64)
    theta[0] = rng.uniform(0.0, 2 * np.pi, size=N)
    noise_history = np.empty((T, N), dtype=np.float64)
    noise_history[0] = 0.0

    # Precompute connectivity mask for a tiny speed-up
    active = K != 0.0
    sqrt_dt = float(np.sqrt(dt))

    # Index arrays for delayed lookups (row i, col j with lag τ_{ij})
    # Shape (N, N) -> broadcast per timestep
    for t in range(1, T):
        # For every (i, j), delayed time index, clamped to ≥ 0
        t_delayed = np.clip(t - 1 - tau, 0, t - 1)  # bounds: delay index ∈ [0, t-1]
        # theta_j(t - τ_{ij}): gather along axis 0 using j-column index
        # theta shape (T, N); we need theta[t_delayed[i,j], j]
        col_idx = np.broadcast_to(np.arange(N)[np.newaxis, :], (N, N))
        theta_delayed = theta[t_delayed, col_idx]  # (N, N), θ_j(t - τ_ij)
        phase_diff = theta_delayed - theta[t - 1][:, np.newaxis] - alpha
        coupling = np.sum(np.where(active, K * np.sin(phase_diff), 0.0), axis=1)
        noise = sigma * rng.standard_normal(N) * sqrt_dt
        theta[t] = theta[t - 1] + dt * (omega + coupling) + noise
        noise_history[t] = noise

    return theta, noise_history


# ---------------------------------------------------------------------------
# High-level generator
# ---------------------------------------------------------------------------


def generate_sakaguchi_kuramoto(
    config: SyntheticConfig | None = None,
) -> SyntheticGroundTruth:
    """Build a :class:`SyntheticGroundTruth` for estimator validation.

    The returned object has:

    - ``generated_phases.theta`` wrapped to ``[0, 2π)``, length
      ``T − burn_in`` (the burn-in is discarded from the head).
    - ``true_K``, ``true_tau``, ``true_alpha``, ``true_omega`` matching
      the actual parameters used inside the simulator.
    - ``noise_realizations`` aligned with the kept phase window for
      noise-aware downstream tests (e.g. filtering).
    - ``metadata`` dict carrying the full config for reproducibility.
    """
    cfg = config or SyntheticConfig()
    rng = np.random.default_rng(cfg.seed)

    K, tau, alpha, omega = _sample_parameters(cfg, rng)

    theta_full, noise_full = _simulate_sdde(
        K,
        tau,
        alpha,
        omega,
        T=cfg.T,
        dt=cfg.dt,
        sigma=cfg.sigma_noise,
        rng=rng,
    )

    # Discard burn-in
    theta = np.mod(theta_full[cfg.burn_in :], 2 * np.pi).astype(np.float64)
    noise = noise_full[cfg.burn_in :].astype(np.float64)

    # Timestamps
    n_kept = theta.shape[0]
    if cfg.timestamps_dtype == "float":
        timestamps = (np.arange(n_kept, dtype=np.float64)) * cfg.dt
    else:
        timestamps = np.arange(n_kept, dtype=np.int64)

    asset_ids = tuple(f"{cfg.asset_prefix}{i:03d}" for i in range(cfg.N))
    pm = PhaseMatrix(
        theta=theta,
        timestamps=timestamps,
        asset_ids=asset_ids,
        extraction_method="hilbert",
        frequency_band=(0.0 + 1e-9, 1.0 / (2 * cfg.dt)),
    )

    metadata = {
        "N": cfg.N,
        "T_raw": cfg.T,
        "T_kept": n_kept,
        "dt": cfg.dt,
        "burn_in": cfg.burn_in,
        "K_sparsity": cfg.K_sparsity,
        "K_scale": cfg.K_scale,
        "tau_max": cfg.tau_max,
        "alpha_max": cfg.alpha_max,
        "alpha_structure": cfg.alpha_structure,
        "sigma_noise": cfg.sigma_noise,
        "seed": cfg.seed,
    }

    return SyntheticGroundTruth(
        true_K=K,
        true_tau=tau,
        true_alpha=alpha,
        true_omega=omega,
        generated_phases=pm,
        noise_realizations=noise,
        metadata=metadata,
    )
