# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Kuramoto ODE simulation engine.

Coupling semantics implemented by this module (FP-1: one equation, one owner
of scale). The canonical Kuramoto right-hand side is::

    θ̇_i = ω_i + K · Σ_j A_norm[i,j] · sin(θ_j − θ_i)

where ``K`` is the **only** scalar coupling gain and ``A_norm`` is topology /
affinity only (zero diagonal, no hidden ``K``). The single owner of scale is
the RHS: :func:`_dtheta_dt` multiplies the topology sum by ``K`` explicitly.

- Global all-to-all mode (no explicit adjacency):
  ``A_norm[i,j] = 1/N`` for ``i != j`` (topology), so
  ``θ̇_i = ω_i + (K/N) · Σ_{j != i} sin(θ_j - θ_i)``.
- Explicit adjacency mode:
  ``A_norm = cfg.adjacency`` with zero diagonal (topology only), so
  ``θ̇_i = ω_i + K · Σ_j A_ij sin(θ_j - θ_i)``.

In both modes, no-self-coupling is enforced by zeroing diagonal weights and
``K`` enters the dynamics exactly once.

Back-compatibility: a caller that historically pre-multiplied its adjacency by
``K`` before handing it to the engine can set
``KuramotoConfig.legacy_pre_scaled_adjacency=True``. The engine then treats the
matrix as already-scaled effective coupling ``C = K·A`` and applies a unit gain
in the RHS, reproducing the pre-FP-1 numerical trajectory bit-for-bit. The
default (``False``) is the canonical single-owner-of-scale path.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray

from .config import KuramotoConfig

__all__ = ["KuramotoEngine", "KuramotoResult", "run_simulation"]

_logger = logging.getLogger(__name__)


@dataclass(slots=True)
class KuramotoResult:
    """Simulation output container with shape and finiteness safeguards."""

    phases: NDArray[np.float64]
    order_parameter: NDArray[np.float64]
    time: NDArray[np.float64]
    config: KuramotoConfig
    summary: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._validate_shapes()
        self.summary = self._compute_summary()

    def _validate_shapes(self) -> None:
        expected_steps = self.config.steps + 1
        expected_n = self.config.N
        if self.phases.shape != (expected_steps, expected_n):
            raise ValueError(
                "Result phases shape mismatch: "
                f"expected {(expected_steps, expected_n)}, got {self.phases.shape}."
            )
        if self.order_parameter.shape != (expected_steps,):
            raise ValueError(
                "Result order_parameter shape mismatch: "
                f"expected {(expected_steps,)}, got {self.order_parameter.shape}."
            )
        if self.time.shape != (expected_steps,):
            raise ValueError(
                f"Result time shape mismatch: expected {(expected_steps,)}, got {self.time.shape}."
            )

        if not np.isfinite(self.phases).all():
            raise ValueError("Result contains non-finite phase values.")
        if not np.isfinite(self.order_parameter).all():
            raise ValueError("Result contains non-finite order_parameter values.")
        if not np.isfinite(self.time).all():
            raise ValueError("Result contains non-finite time values.")
        tol = 1e-12
        if np.any(self.order_parameter < -tol) or np.any(self.order_parameter > 1.0 + tol):
            raise ValueError(
                "Result order_parameter values must stay within [0, 1] (±1e-12 tolerance)."
            )

    def _compute_summary(self) -> dict[str, Any]:
        R = self.order_parameter
        cfg = self.config
        return {
            "final_R": float(R[-1]),
            "mean_R": float(R.mean()),
            "max_R": float(R.max()),
            "min_R": float(R.min()),
            "std_R": float(R.std()),
            "N": cfg.N,
            "K": cfg.K,
            "dt": cfg.dt,
            "steps": cfg.steps,
            "total_time": float(self.time[-1]),
            "coupling_mode": cfg.coupling_mode,
            "seed": cfg.seed,
        }


class KuramotoEngine:
    """Deterministic Kuramoto RK4 integrator for validated configurations."""

    def __init__(self, config: KuramotoConfig) -> None:
        self._cfg = config
        self._omega, self._theta0 = self._resolve_initial_conditions(config)
        self._adj = self._resolve_adjacency(config)
        # FP-1: K is the sole owner of coupling scale and lives in the RHS.
        # In the legacy pre-scaled path the matrix already carries K (C = K·A),
        # so the RHS gain must be unity to avoid double-scaling.
        self._coupling_gain: float = 1.0 if config.legacy_pre_scaled_adjacency else float(config.K)
        # FP-1 fail-closed: a negative coupling gain is repulsive and cannot
        # claim attractive Kuramoto physics. The canonical single-owner path
        # rejects it at construction. (The legacy pre-scaled path folds the sign
        # into the supplied matrix, so the gain it uses is the unit 1.0 above.)
        if self._coupling_gain < 0.0:
            raise ValueError(
                "FP-1: coupling gain K must be non-negative for the canonical "
                f"single-owner-of-scale path; got K={config.K!r}. A repulsive/signed "
                "coupling must be expressed via a signed adjacency with "
                "legacy_pre_scaled_adjacency or a CLAIM_SIGNED coupling spec."
            )
        self._validate_runtime_inputs(self._omega, self._theta0, self._adj)

    def run(self) -> KuramotoResult:
        """Integrate ODE trajectories and return validated :class:`KuramotoResult`."""
        cfg = self._cfg
        N = cfg.N
        steps = cfg.steps
        dt = cfg.dt
        omega = self._omega
        adj = self._adj

        phases = np.empty((steps + 1, N), dtype=np.float64)
        R_arr = np.empty(steps + 1, dtype=np.float64)
        time_arr = np.arange(steps + 1, dtype=np.float64) * dt

        gain = self._coupling_gain

        theta = self._theta0.copy()
        phases[0] = theta
        R_arr[0] = _order_parameter(theta)

        _logger.debug(
            "Starting Kuramoto simulation: N=%d, K=%.4f, dt=%.6f, steps=%d, mode=%s",
            N,
            cfg.K,
            dt,
            steps,
            cfg.coupling_mode,
        )

        for k in range(steps):
            theta = _rk4_step(theta, omega, adj, dt, K=gain)
            if not np.isfinite(theta).all():
                raise FloatingPointError(f"Non-finite phase values encountered at step={k + 1}.")
            phases[k + 1] = theta
            R_arr[k + 1] = _order_parameter(theta)

        return KuramotoResult(phases=phases, order_parameter=R_arr, time=time_arr, config=cfg)

    @staticmethod
    def _resolve_initial_conditions(
        cfg: KuramotoConfig,
    ) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        rng = np.random.default_rng(cfg.seed)

        omega = (
            cfg.omega.astype(np.float64, copy=False)
            if cfg.omega is not None
            else rng.standard_normal(cfg.N)
        )
        theta0 = (
            cfg.theta0.astype(np.float64, copy=False)
            if cfg.theta0 is not None
            else rng.uniform(0.0, 2.0 * np.pi, cfg.N)
        )
        return omega, theta0

    @staticmethod
    def _resolve_adjacency(cfg: KuramotoConfig) -> NDArray[np.float64]:
        """Build the topology-only coupling matrix ``A_norm`` (FP-1).

        Returns affinity/topology with zero diagonal and **no** embedded scalar
        gain ``K`` — the gain is applied once in the RHS (:func:`_dtheta_dt`).

        - Explicit adjacency (``cfg.adjacency is not None``): ``A_norm`` is the
          supplied matrix with its diagonal zeroed (no-self-coupling). The RHS
          then forms ``K · Σ_j A_norm[i,j] · sin(θ_j − θ_i)``.
        - Global all-to-all (``cfg.adjacency is None``): ``A_norm[i,j] = 1/N``
          for ``i != j``. The ``1/N`` is the all-to-all normalisation (part of
          the topology), not the coupling gain; combined with the RHS gain it
          reproduces the mean-field ``(K/N) · Σ_{j != i} sin(θ_j − θ_i)``.

        Legacy back-compat (``cfg.legacy_pre_scaled_adjacency=True``): the
        matrix is treated as already-scaled effective coupling ``C = K·A`` and
        returned pre-multiplied by ``K`` (diagonal zeroed); the engine then
        applies a unit RHS gain, reproducing the pre-FP-1 trajectory exactly.
        """
        N = cfg.N
        if cfg.legacy_pre_scaled_adjacency:
            K = cfg.K
            if cfg.adjacency is not None:
                legacy_adj = K * cfg.adjacency.astype(np.float64, copy=True)
                np.fill_diagonal(legacy_adj, 0.0)
                return legacy_adj
            legacy_global = np.full((N, N), K / N, dtype=np.float64)
            np.fill_diagonal(legacy_global, 0.0)
            return legacy_global

        if cfg.adjacency is not None:
            adj = cfg.adjacency.astype(np.float64, copy=True)
            np.fill_diagonal(adj, 0.0)
            return adj

        adj = np.full((N, N), 1.0 / N, dtype=np.float64)
        np.fill_diagonal(adj, 0.0)
        return adj

    @staticmethod
    def _validate_runtime_inputs(
        omega: NDArray[np.float64],
        theta0: NDArray[np.float64],
        adj: NDArray[np.float64],
    ) -> None:
        if omega.ndim != 1 or theta0.ndim != 1 or omega.shape != theta0.shape:
            raise ValueError("Runtime vectors omega and theta0 must be 1-D and same shape.")

        n = omega.shape[0]
        if adj.shape != (n, n):
            raise ValueError(f"Runtime adjacency shape must be {(n, n)}, got {adj.shape}.")

        if (
            not np.isfinite(omega).all()
            or not np.isfinite(theta0).all()
            or not np.isfinite(adj).all()
        ):
            raise ValueError("Runtime inputs must all be finite.")


def _dtheta_dt(
    theta: NDArray[np.float64],
    omega: NDArray[np.float64],
    adj: NDArray[np.float64],
    *,
    K: float = 1.0,
) -> NDArray[np.float64]:
    """Evaluate the Kuramoto RHS for a single phase vector (FP-1).

    Computes ``θ̇_i = ω_i + K · Σ_j adj[i,j] · sin(θ_j − θ_i)`` where ``K`` is
    the single scalar coupling gain (the sole owner of scale) and ``adj`` is
    topology-only affinity ``A_norm`` with zero diagonal. ``K`` defaults to
    ``1.0`` so a caller that supplies an already-scaled effective matrix
    ``C = K·A`` (legacy convention) gets the identical, un-double-scaled result.
    """
    diff = theta[np.newaxis, :] - theta[:, np.newaxis]
    sin_diff = np.sin(diff)
    coupling = K * (adj * sin_diff).sum(axis=1)
    out: NDArray[np.float64] = omega + coupling
    if not np.isfinite(out).all():
        raise FloatingPointError("Non-finite derivative values produced by Kuramoto RHS.")
    return out


def _rk4_step(
    theta: NDArray[np.float64],
    omega: NDArray[np.float64],
    adj: NDArray[np.float64],
    dt: float,
    *,
    K: float = 1.0,
) -> NDArray[np.float64]:
    """Advance one Runge-Kutta 4 integration step (FP-1 single-owner gain ``K``)."""
    k1 = _dtheta_dt(theta, omega, adj, K=K)
    k2 = _dtheta_dt(theta + 0.5 * dt * k1, omega, adj, K=K)
    k3 = _dtheta_dt(theta + 0.5 * dt * k2, omega, adj, K=K)
    k4 = _dtheta_dt(theta + dt * k3, omega, adj, K=K)
    return theta + (dt / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)


# INV-K1 round-off tolerance. The Kuramoto order parameter is
# ``R = |⟨e^{iθ}⟩|`` and Cauchy–Schwarz gives the EXACT bound ``R ≤ 1`` with
# equality iff all phases are equal, so the only way ``R`` can exceed 1 in
# IEEE-754 is the accumulation round-off of the complex mean. That round-off is
# bounded by a few ULP of the magnitude-1 summands; ``1e-8`` is many orders of
# magnitude above that floor, so any ``R`` beyond ``1 + 1e-8`` is NOT round-off
# — it is a non-finite or divergent integrator state leaking through. We clip
# genuine round-off (``R ≤ 1 + tol``) back into ``[0, 1]`` and FAIL CLOSED on
# anything larger rather than silently repairing it.
_INV_K1_ROUNDOFF_TOL: float = 1e-8


def _order_parameter(theta: NDArray[np.float64]) -> float:
    """Compute the Kuramoto order parameter ``R = |mean(exp(iθ))|`` (INV-K1).

    INV-K1 (Cauchy–Schwarz): ``R = |⟨e^{iθ}⟩| ∈ [0, 1]`` exactly, with ``R = 1``
    iff all phases are equal. This function is FAIL-CLOSED on any violation that
    cannot be explained by floating-point round-off:

    * a non-finite magnitude (NaN/±Inf — e.g. NaN/Inf phases) raises
      :class:`ValueError`;
    * a magnitude exceeding ``1 + 1e-8`` raises :class:`FloatingPointError`,
      because beyond the documented round-off bound it signals integrator
      divergence, not arithmetic noise;
    * only genuine round-off (``R ≤ 1 + 1e-8``) is clipped into ``[0, 1]``.

    Valid integrator output (``R`` already in ``[0, 1]``) is returned unchanged.
    """
    # Non-finite phases (NaN/±Inf) make ``exp`` emit an "invalid value"
    # RuntimeWarning before producing the NaN we then detect and raise on; the
    # detection IS the contract, so silence the redundant warning rather than
    # let it leak (or be promoted to an error by a strict warning filter).
    with np.errstate(invalid="ignore"):
        mag = float(np.abs(np.exp(1j * theta).mean()))
    if not np.isfinite(mag):
        raise ValueError(
            f"INV-K1 violated: order parameter magnitude is non-finite ({mag!r}); "
            "Cauchy–Schwarz guarantees R = |mean(exp(iθ))| ∈ [0,1] for finite phases, "
            "so a non-finite R is a divergent / non-finite integrator state."
        )
    if mag > 1.0 + _INV_K1_ROUNDOFF_TOL:
        raise FloatingPointError(
            f"INV-K1 violated: order parameter R={mag!r} exceeds 1 by more than the "
            f"round-off tolerance {_INV_K1_ROUNDOFF_TOL!r}; Cauchy–Schwarz caps "
            "R = |mean(exp(iθ))| at 1, so this magnitude signals integrator "
            "divergence, not floating-point round-off."
        )
    # Only genuine round-off (mag ≤ 1 + tol) reaches here; clip it into [0, 1].
    if mag > 1.0:
        return 1.0
    if mag < 0.0:  # pragma: no cover - |·| is never negative; defensive floor.
        return 0.0
    return mag


def run_simulation(config: KuramotoConfig) -> KuramotoResult:
    """Convenience one-shot entry point around :class:`KuramotoEngine`."""
    return KuramotoEngine(config).run()
