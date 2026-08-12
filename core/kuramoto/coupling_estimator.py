# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Sparse signed coupling inference ``K_ij`` (protocol M1.3).

Given a :class:`~core.kuramoto.contracts.PhaseMatrix` we solve, for each
oscillator ``i`` independently, the penalised regression

.. math::

    \\dot\\theta_i(t) - \\bar\\omega_i \\;=\\; \\sum_{j \\neq i}
        \\beta_{ij}\\, \\sin\\bigl(\\theta_j(t) - \\theta_i(t)\\bigr) + \\varepsilon_i

where ``β_{ij} ≡ K_{ij}`` is the signed coupling we are after. The
design matrix is composed of phase-difference sines and the target
is the instantaneous frequency deviation from its temporal median.

This module ships a **pure-numpy** Minimax Concave Penalty (MCP),
SCAD, and L1 (Lasso) proximal-gradient solver — the methodology
explicitly warns against the deprecated ``stability-selection`` PyPI
package (broken on sklearn ≥ 1.3) and notes that ``skglm`` is optional.
Keeping the core path dependency-free guarantees the identification
stack runs on a bare scipy install.

On top of the row solver we ship a **complementary-pairs stability
selection** wrapper (Shah & Samworth, 2013) that returns per-edge
selection probabilities. Edges whose maximum selection probability
across the regularisation grid exceeds the user-chosen threshold are
retained; all others are zeroed out.

The output is a contract-compliant :class:`CouplingMatrix` with
optional per-edge ``stability_scores``.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray

from .contracts import CouplingMatrix, PhaseMatrix
from .identifiability import (
    IdentifiabilityReport,
    front_gate_verdict,
    linearised_edge_covariance,
)

__all__ = [
    "CouplingEstimationConfig",
    "CouplingEstimator",
    "PersistentExcitationError",
    "SwingCouplingEstimate",
    "SwingDesign",
    "SwingDesignStrategy",
    "estimate_coupling",
    "estimate_swing_coupling",
    "estimate_swing_coupling_integral",
    "mcp_prox",
    "scad_prox",
    "soft_threshold",
    "complementary_pairs_stability",
    "swing_strategy_registry",
]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CouplingEstimationConfig:
    """Hyperparameters for row-wise sparse coupling regression.

    Attributes
    ----------
    penalty : str
        ``"mcp"`` (default), ``"scad"``, or ``"lasso"``.
    lambda_reg : float
        Regularisation strength used by :func:`CouplingEstimator.estimate`
        when stability selection is disabled.
    gamma : float
        Concavity parameter for MCP/SCAD. ``γ = 3.0`` is the standard
        choice. For MCP the prox is well-defined as long as
        ``γ * L > 1``, where ``L`` is the Lipschitz constant of the
        smooth part; the row solver enforces this automatically.
    dt : float
        Sampling interval used for the finite-difference derivative of
        the unwrapped phase. Matches the ``timestamps`` units.
    max_iter : int
        Proximal-gradient iteration cap per row.
    tol : float
        Relative convergence tolerance on the coefficient infinity-norm.
    standardize : bool
        If ``True`` the design-matrix columns are rescaled to unit
        standard deviation before solving and the coefficients are
        back-transformed afterwards. Strongly recommended — it removes
        the dependence of ``λ`` on the phase-difference variance.
    stability_selection : bool
        If ``True``, call :func:`complementary_pairs_stability` inside
        :meth:`CouplingEstimator.estimate` and zero out edges below
        ``stability_threshold``.
    lambda_grid : tuple[float, ...] | None
        Regularisation grid for stability selection. If ``None`` a
        log-spaced grid on ``[1e-3, 1e-1]`` is used.
    n_subsamples : int
        Number of complementary-pair subsamples (each pair produces
        two fits, so the total number of fits per lambda is
        ``2 * n_subsamples``).
    subsample_fraction : float
        Fraction of rows drawn into each half of a complementary pair.
    stability_threshold : float
        Minimum selection probability for an edge to survive.
    random_state : int | None
        Seed for stability-selection resampling.
    """

    penalty: str = "mcp"
    lambda_reg: float = 0.01
    gamma: float = 3.0
    dt: float = 1.0
    max_iter: int = 500
    tol: float = 1e-5
    standardize: bool = True
    stability_selection: bool = False
    lambda_grid: tuple[float, ...] | None = None
    n_subsamples: int = 40
    subsample_fraction: float = 0.5
    stability_threshold: float = 0.6
    random_state: int | None = None

    _ALLOWED_PENALTIES: tuple[str, ...] = field(default=("mcp", "scad", "lasso"), repr=False)

    def __post_init__(self) -> None:
        if self.penalty not in self._ALLOWED_PENALTIES:
            raise ValueError(
                f"penalty must be one of {self._ALLOWED_PENALTIES}; got {self.penalty!r}"
            )
        if self.lambda_reg <= 0:
            raise ValueError("lambda_reg must be > 0")
        if self.gamma <= 1.0:
            raise ValueError("gamma must be > 1 for MCP/SCAD")
        if self.dt <= 0:
            raise ValueError("dt must be > 0")
        if self.max_iter < 1:
            raise ValueError("max_iter must be ≥ 1")
        if not 0.0 < self.subsample_fraction < 1.0:
            raise ValueError("subsample_fraction must lie in (0, 1)")
        if not 0.0 <= self.stability_threshold <= 1.0:
            raise ValueError("stability_threshold must lie in [0, 1]")


# ---------------------------------------------------------------------------
# Proximal operators
# ---------------------------------------------------------------------------


def soft_threshold(x: np.ndarray, t: float) -> np.ndarray:
    """Component-wise soft-thresholding operator (L1 prox)."""
    return np.asarray(np.sign(x) * np.maximum(np.abs(x) - t, 0.0), dtype=np.float64)


def mcp_prox(z: np.ndarray, lam: float, gamma: float, step: float) -> np.ndarray:
    """Proximal operator of the MCP penalty (Breheny & Huang, 2011).

    The MCP is

        P_λ(t) = λ|t| − t² / (2γ)  for |t| ≤ γλ,
                 γλ² / 2            otherwise.

    For step-size ``step = 1/L`` the proximal map has the closed form

    - ``|z| ≤ step·λ``:              ``0``
    - ``step·λ < |z| ≤ γλ``:         ``sign(z)·(|z| − step·λ) / (1 − step/γ)``
    - ``|z| > γλ``:                  ``z``

    and requires ``step < γ`` for the middle branch to stay contractive.
    """
    if step >= gamma:
        # Fall back to soft-thresholding on the offending coordinates;
        # in practice the row solver always picks ``step = 1/L`` small enough.
        return soft_threshold(z, step * lam)
    abs_z = np.abs(z)
    out = np.where(
        abs_z <= step * lam,
        0.0,
        np.where(
            abs_z <= gamma * lam,
            np.sign(z) * (abs_z - step * lam) / (1.0 - step / gamma),
            z,
        ),
    )
    return np.asarray(out, dtype=np.float64)


def scad_prox(z: np.ndarray, lam: float, gamma: float, step: float) -> np.ndarray:
    """Proximal operator of the SCAD penalty (Fan & Li, 2001).

    Three-region closed form; ``γ > 2`` is required for the middle
    branch to be contractive. Outside that assumption the operator
    degrades gracefully to soft-thresholding.
    """
    if gamma <= 2.0 or step >= (gamma - 1.0):
        return soft_threshold(z, step * lam)
    abs_z = np.abs(z)
    sign_z = np.sign(z)
    out = np.where(
        abs_z <= step * lam + lam,
        soft_threshold(z, step * lam),
        np.where(
            abs_z <= gamma * lam,
            sign_z * (abs_z - step * gamma * lam / (gamma - 1.0)) / (1.0 - step / (gamma - 1.0)),
            z,
        ),
    )
    return np.asarray(out, dtype=np.float64)


# ---------------------------------------------------------------------------
# Row solver
# ---------------------------------------------------------------------------


def _apply_prox(z: np.ndarray, lam: float, step: float, penalty: str, gamma: float) -> np.ndarray:
    if penalty == "lasso":
        return soft_threshold(z, step * lam)
    if penalty == "mcp":
        return mcp_prox(z, lam, gamma, step)
    if penalty == "scad":
        return scad_prox(z, lam, gamma, step)
    raise ValueError(f"Unknown penalty {penalty!r}")


def _proximal_gradient_row(
    X: np.ndarray,
    y: np.ndarray,
    lam: float,
    *,
    penalty: str = "mcp",
    gamma: float = 3.0,
    max_iter: int = 500,
    tol: float = 1e-5,
) -> np.ndarray:
    """Solve ``min_β (1/(2n))||y − Xβ||² + P_λ(β)`` via proximal gradient.

    Uses the ISTA update with a constant step size set from the
    spectral-radius upper bound ``L = ‖XᵀX‖₂ / n``. For small matrices
    (``N−1 ≲ 500``) we compute ``L`` exactly via ``numpy.linalg.svd``;
    for larger designs the row solver is still fine but you may wish to
    substitute a power-iteration estimate.
    """
    n, p = X.shape
    # Exact Lipschitz constant of the smooth gradient
    # ∇f(β) = (1/n) X^T (X β − y), so L = λ_max(X^T X) / n
    if p == 0:
        return np.zeros(0, dtype=np.float64)
    # Use SVD for a numerically robust singular value
    sigma_max = float(np.linalg.svd(X, compute_uv=False)[0])
    L = (sigma_max**2) / n
    if L <= 0:
        return np.zeros(p, dtype=np.float64)
    step = 1.0 / L

    beta = np.zeros(p, dtype=np.float64)
    Xt = X.T
    for _ in range(max_iter):
        grad = (Xt @ (X @ beta - y)) / n
        z = beta - step * grad
        beta_new = _apply_prox(z, lam, step, penalty, gamma)
        diff = float(np.max(np.abs(beta_new - beta)))
        scale = max(
            1.0, float(np.max(np.abs(beta)))
        )  # bounds: normalisation floor avoids division by near-zero beta
        beta = beta_new
        if diff < tol * scale:
            break
    return beta


# ---------------------------------------------------------------------------
# Design-matrix construction
# ---------------------------------------------------------------------------


def _build_target_and_design(
    theta: np.ndarray, dt: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return per-oscillator target ``y`` and shared design ``X``.

    ``theta`` is the *wrapped* phase matrix from
    :class:`PhaseMatrix` in ``[0, 2π)``. We unwrap along the time axis,
    differentiate once, and subtract the temporal median to remove the
    natural frequency.

    Returns
    -------
    y : np.ndarray, shape ``(T, N)``
        Frequency-deviation target per oscillator.
    sin_diff : np.ndarray, shape ``(T, N, N)``
        ``sin(θ_j − θ_i)`` with ``j`` on the last axis. Used to form the
        row-specific design ``X_i`` via slicing.
    omega_nat : np.ndarray, shape ``(N,)``
        Natural-frequency estimate per oscillator (median instantaneous
        frequency).
    """
    unwrapped = np.unwrap(theta, axis=0)
    omega_inst = np.gradient(unwrapped, dt, axis=0)  # (T, N)
    omega_nat = np.median(omega_inst, axis=0)  # (N,)
    y = omega_inst - omega_nat[np.newaxis, :]  # (T, N)
    # sin_diff[t, i, j] = sin(θ_j[t] − θ_i[t])
    diff = theta[:, np.newaxis, :] - theta[:, :, np.newaxis]
    sin_diff = np.sin(diff)
    return (
        y.astype(np.float64),
        sin_diff.astype(np.float64),
        omega_nat.astype(np.float64),
    )


def _row_design(sin_diff: np.ndarray, i: int) -> np.ndarray:
    """Extract ``X_i`` — columns ``sin(θ_j − θ_i)`` for ``j ≠ i``."""
    N = sin_diff.shape[1]
    cols = [j for j in range(N) if j != i]
    return sin_diff[:, i, cols]  # (T, N-1)


def _standardise(X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Scale columns of ``X`` to unit standard deviation.

    Returns the scaled matrix and the per-column scale factors so that
    the solved coefficients can be back-transformed (``β_original =
    β_scaled / scale``).
    """
    scale = X.std(axis=0, ddof=0)
    scale = np.where(scale > 1e-12, scale, 1.0)
    return X / scale, scale


# ---------------------------------------------------------------------------
# Single-shot estimation
# ---------------------------------------------------------------------------


def _estimate_K_single(
    theta: np.ndarray,
    lam: float,
    cfg: CouplingEstimationConfig,
) -> np.ndarray:
    """Fit coupling rows at a fixed ``λ`` without stability selection."""
    y_all, sin_diff, _ = _build_target_and_design(theta, cfg.dt)
    T, N = y_all.shape
    K = np.zeros((N, N), dtype=np.float64)
    for i in range(N):
        Xi = _row_design(sin_diff, i)
        yi = y_all[:, i]
        if cfg.standardize:
            Xi_s, x_scale = _standardise(Xi)
            y_scale = float(np.std(yi, ddof=0))
            if y_scale < 1e-12:
                y_scale = 1.0
            yi_s = (yi - float(np.mean(yi))) / y_scale
        else:
            Xi_s, x_scale = Xi, np.ones(Xi.shape[1])
            y_scale = 1.0
            yi_s = yi
        beta = _proximal_gradient_row(
            Xi_s,
            yi_s,
            lam,
            penalty=cfg.penalty,
            gamma=cfg.gamma,
            max_iter=cfg.max_iter,
            tol=cfg.tol,
        )
        # Back-transform: β_physical = β_scaled * std(y) / std(X_j)
        beta = beta * y_scale / x_scale
        # Scatter back into K with the diagonal hole preserved
        idx = 0
        for j in range(N):
            if j == i:
                continue
            K[i, j] = beta[idx]
            idx += 1
    return K


# ---------------------------------------------------------------------------
# Complementary-pairs stability selection
# ---------------------------------------------------------------------------


def complementary_pairs_stability(
    theta: np.ndarray,
    cfg: CouplingEstimationConfig,
) -> tuple[np.ndarray, np.ndarray]:
    """Complementary-pairs stability selection (Shah & Samworth, 2013).

    For each λ in ``cfg.lambda_grid`` we draw ``cfg.n_subsamples``
    complementary pairs (two disjoint halves of the time axis) and fit
    the row regression on each half independently. The selection
    probability for edge ``(i, j)`` at lambda ``λ`` is

        π_{ij}(λ) = (# halves where |K̂_{ij}| > 0) / (2 * n_subsamples)

    The score returned is the supremum of ``π_{ij}`` over the grid.

    Returns
    -------
    K_median : np.ndarray
        Median of the non-zero edge estimates across the full set of
        fits (useful as a bias-reduced weight estimate).
    stability : np.ndarray
        Per-edge selection probability in ``[0, 1]``. Diagonal is zero.
    """
    T, N = theta.shape
    rng = np.random.default_rng(cfg.random_state)
    if cfg.lambda_grid is None:
        lam_grid: np.ndarray = np.logspace(-3, -1, 10)
    else:
        lam_grid = np.asarray(cfg.lambda_grid, dtype=np.float64)

    half = int(cfg.subsample_fraction * T)
    if half < 10:
        raise ValueError(f"Subsample half size {half} too small; increase T or subsample_fraction")

    selection_count = np.zeros((len(lam_grid), N, N), dtype=np.int64)
    # Per-edge pool of active (non-zero) coupling estimates across every
    # bootstrap half AND every λ in the grid. We keep the full pool rather
    # than a running sum because the contract (docstring + variable name)
    # is the MEDIAN of the non-zero edge estimates — a robust, outlier-
    # resistant statistic — and the median cannot be computed incrementally.
    estimates: list[list[list[float]]] = [[[] for _ in range(N)] for _ in range(N)]
    n_halves = 0  # count of independent halves processed

    for _ in range(cfg.n_subsamples):
        idx = rng.permutation(T)
        half_a = np.sort(idx[:half])
        half_b = np.sort(idx[half : 2 * half])
        for half_idx in (half_a, half_b):
            theta_sub = theta[half_idx]
            n_halves += 1
            for li, lam in enumerate(lam_grid):
                K_hat = _estimate_K_single(theta_sub, float(lam), cfg)
                active = np.abs(K_hat) > 1e-10
                selection_count[li] += active
                # Pool the signed estimate of every edge that survived the
                # penalty at this (half, λ) into its per-edge collection.
                act_i, act_j = np.nonzero(active)
                for i, j in zip(act_i.tolist(), act_j.tolist(), strict=True):
                    estimates[i][j].append(float(K_hat[i, j]))
    # Selection probability per (λ, edge): fraction of halves in which
    # the edge was selected at that regularisation level
    probs = selection_count / max(n_halves, 1)
    stability = probs.max(axis=0).astype(np.float64)
    np.fill_diagonal(stability, 0.0)

    # Bias-reduced per-edge weight: the MEDIAN of the pooled non-zero
    # estimates (0.0 when an edge was never selected). The median is
    # deliberately robust — a single outlier fit cannot drag the weight,
    # matching the "median of the non-zero edge estimates" contract above.
    K_median = np.zeros((N, N), dtype=np.float64)
    for i in range(N):
        for j in range(N):
            pool = estimates[i][j]
            if pool:
                K_median[i, j] = float(np.median(np.asarray(pool, dtype=np.float64)))
    np.fill_diagonal(K_median, 0.0)
    return K_median, stability


# ---------------------------------------------------------------------------
# High-level API
# ---------------------------------------------------------------------------


class CouplingEstimator:
    """Sparse signed coupling estimator for Sakaguchi–Kuramoto identification.

    Example
    -------
    >>> cfg = CouplingEstimationConfig(penalty="mcp", lambda_reg=0.02)
    >>> est = CouplingEstimator(cfg)
    >>> coupling = est.estimate(phase_matrix)
    >>> coupling.K.shape
    (N, N)
    """

    def __init__(self, config: CouplingEstimationConfig | None = None) -> None:
        self.config = config or CouplingEstimationConfig()

    def estimate(self, phases: PhaseMatrix) -> CouplingMatrix:
        """Run the full estimation pipeline and return a validated
        :class:`CouplingMatrix`.

        If ``config.stability_selection`` is enabled, the returned
        matrix uses the median of the bootstrap weight estimates and
        carries per-edge stability scores on ``stability_scores``.
        Otherwise the matrix contains the single-``λ`` ISTA solution.
        """
        cfg = self.config
        theta = np.asarray(phases.theta, dtype=np.float64)

        if cfg.stability_selection:
            K_median, stability = complementary_pairs_stability(theta, cfg)
            K = np.where(stability >= cfg.stability_threshold, K_median, 0.0)
            np.fill_diagonal(K, 0.0)
            stability_scores: np.ndarray | None = stability
        else:
            K = _estimate_K_single(theta, cfg.lambda_reg, cfg)
            np.fill_diagonal(K, 0.0)
            stability_scores = None

        n_off_diag = K.size - K.shape[0]
        sparsity = float(1.0 - np.count_nonzero(K) / n_off_diag) if n_off_diag else 1.0

        # Sign consistency warning (methodology M1.3 Step 5)
        nz_mask = K != 0.0
        antisym = nz_mask & nz_mask.T & (np.sign(K) != np.sign(K.T))
        n_antisym_pairs = int(antisym.sum() // 2)
        n_bidirectional_pairs = int((nz_mask & nz_mask.T).sum() // 2)
        if n_bidirectional_pairs and n_antisym_pairs > 0.3 * n_bidirectional_pairs:
            logger.warning(
                "High antisymmetric ratio: %d of %d bidirectional pairs have opposite signs — "
                "verify data quality or confirm competitive dynamics are expected",
                n_antisym_pairs,
                n_bidirectional_pairs,
            )

        return CouplingMatrix(
            K=K,
            asset_ids=phases.asset_ids,
            sparsity=sparsity,
            method=cfg.penalty,
            stability_scores=stability_scores,
        )


def estimate_coupling(
    phases: PhaseMatrix,
    config: CouplingEstimationConfig | None = None,
) -> CouplingMatrix:
    """Functional shortcut around :class:`CouplingEstimator`."""
    return CouplingEstimator(config).estimate(phases)


# ---------------------------------------------------------------------------
# Second-order (swing) identification path — CALIB-GRID-001 R1
# ---------------------------------------------------------------------------
#
# The first-order path above solves
#
#     θ̇_i − ω̄_i = Σ_{j≠i} K_ij sin(θ_j − θ_i) + ε_i .
#
# Power-grid rotors are *second-order* (swing equation):
#
#     m_i θ̈_i + d_i θ̇_i = P_i − Σ_{j≠i} K_ij sin(θ_i − θ_j) .
#
# Applying the first-order identifier to swing data folds the unmodelled
# inertial term ``m_i θ̈_i`` into the residual, biasing ``K̂``. The path
# below regresses the *full* swing identity instead. With known per-node
# inertia ``m_i`` and damping ``d_i`` the model is linear in the unknowns
# ``(K_i·, P_i)``:
#
#     y_i(t) ≡ m_i θ̈_i(t) + d_i θ̇_i(t)
#            = P_i + Σ_{j≠i} (−K_ij) · sin(θ_i(t) − θ_j(t)) .
#
# A column of ones recovers the injection ``P_i`` jointly (so the natural
# frequency ``ω_i = P_i / d_i`` is *not* assumed known), and the negated
# phase-difference sines recover the signed, symmetric coupling.


class PersistentExcitationError(RuntimeError):
    """Raised when the swing design matrix is rank-deficient.

    A phase-locked trajectory has ``θ_i − θ_j → const`` so the regressor
    columns ``sin(θ_i − θ_j)`` become near-collinear: the per-node design
    Gram matrix loses rank and the least-squares solution is dominated by
    noise. Emitting a ``K̂`` from such a design would be a misleading
    instrument output, so the swing path fails closed with this typed
    diagnostic instead (instrument-honesty invariant, not a tuning knob).

    Attributes
    ----------
    node : int
        Index of the oscillator whose row design first failed the test
        (per-row solver), or ``-1`` when the *global* symmetric joint
        design is rank-deficient.
    singular_ratio : float
        Smallest-to-largest singular-value ratio of the standardised
        design (the persistent-excitation diagnostic).
    threshold : float
        The configured minimum acceptable ``singular_ratio``.
    """

    def __init__(self, node: int, singular_ratio: float, threshold: float) -> None:
        self.node = node
        self.singular_ratio = singular_ratio
        self.threshold = threshold
        where = "global symmetric design" if node < 0 else f"node {node}"
        super().__init__(
            f"persistent-excitation guard tripped ({where}): "
            f"design singular-value ratio {singular_ratio:.3e} < "
            f"threshold {threshold:.3e} — the trajectory is phase-locked / "
            f"rank-deficient and no trustworthy K̂ can be identified "
            f"(fail-closed, no silent biased estimate)"
        )


@dataclass(frozen=True, slots=True)
class SwingCouplingEstimate:
    """Result of the second-order (swing) identification path.

    Attributes
    ----------
    K : np.ndarray
        Shape ``(N, N)``, signed coupling with zero diagonal. The grid
        coupling is physically symmetric; the raw row solution is *not*
        symmetrised here (the caller decides), but the swing identity
        removes the inertial bias that produced the large antisymmetric
        residual under the first-order path.
    injection : np.ndarray
        Shape ``(N,)``, recovered per-node net power injection ``P_i``.
    omega : np.ndarray
        Shape ``(N,)``, natural frequency ``ω_i = P_i / d_i`` consistent
        with the over-damped reduction (Dörfler–Bullo SI Eq. (S15)).
    min_singular_ratio : float
        Worst per-node persistent-excitation diagnostic over all rows
        (smallest-to-largest singular-value ratio of the standardised
        design). Reported for transparency even when the guard passes.
    identifiability : IdentifiabilityReport | None
        **Additive** graded self-knowledge layer (upgrade lineage #2).
        Present only for the ``symmetric=True`` joint solve when
        ``identifiability_gate=True`` (the global design needed for the
        linearised covariance exists only there); ``None`` otherwise.
        Carries the bounded identifiability score, per-edge calibrated
        95 % confidence intervals and the ``ACCEPT`` / ``REFUSE``
        verdict. The point-estimate fields (``K``, ``injection``,
        ``omega``, ``min_singular_ratio``) are **bit-identical**
        regardless of this field — existing callers that ignore it see
        no change (verified by the R1 bit-stability tests).
    """

    K: NDArray[np.float64]
    injection: NDArray[np.float64]
    omega: NDArray[np.float64]
    min_singular_ratio: float
    identifiability: IdentifiabilityReport | None = None


def _savgol_derivatives(
    theta: NDArray[np.float64],
    dt: float,
    *,
    window: int,
    polyorder: int,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    r"""Savitzky–Golay derivatives ``(θ̇, θ̈)`` of the unwrapped phase.

    The phase is unwrapped along the time axis first so the derivative
    is taken on the continuous lift, not the wrapped ``[0, 2π)``
    representation. A local degree-``polyorder`` polynomial is fitted by
    least squares in a sliding ``window`` and its analytic first and
    second derivatives are evaluated at the window centre. On a smooth
    damped-oscillatory swing transient this is *consistent* (the naïve
    twice-applied central difference compounds truncation error and is
    only first-order at the endpoints) and it strongly rejects additive
    measurement noise — the standard treatment for swing-data RoCoF /
    acceleration estimation.

    ``window`` is forced odd and clipped to the trajectory length;
    ``polyorder`` is clipped below ``window`` (both required by the
    Savitzky–Golay least-squares fit). Shapes returned: ``(T, N)``.
    """
    from scipy.signal import savgol_filter

    unwrapped = np.unwrap(theta, axis=0)
    t_len = unwrapped.shape[0]
    win = min(window if window % 2 == 1 else window + 1, t_len if t_len % 2 == 1 else t_len - 1)
    win = max(win, 5)
    order = min(polyorder, win - 1)
    theta_dot = savgol_filter(unwrapped, win, order, deriv=1, delta=dt, axis=0)
    theta_ddot = savgol_filter(unwrapped, win, order, deriv=2, delta=dt, axis=0)
    return (
        np.asarray(theta_dot, dtype=np.float64),
        np.asarray(theta_ddot, dtype=np.float64),
    )


def _singular_ratio(design: NDArray[np.float64]) -> float:
    """Smallest-to-largest singular-value ratio of a design matrix.

    This is the reciprocal condition number; it is ``0`` for a
    rank-deficient design and ``1`` for a perfectly conditioned one. It
    is the principled persistent-excitation diagnostic (it does not
    depend on an absolute scale once the columns are standardised).
    """
    if design.shape[1] == 0:
        return 0.0
    sv = np.linalg.svd(design, compute_uv=False)
    s_max = float(sv[0])
    if s_max <= 0.0:
        return 0.0
    return float(sv[-1] / s_max)


# ---------------------------------------------------------------------------
# Swing design-assembly strategy registry (module-scale forcing function)
# ---------------------------------------------------------------------------
#
# Every symmetric-joint swing identifier ever added to this module (the
# R1 differential path #1 and the weak/integral path CALIB-GRID-002 #2)
# assembles a *path-specific* global design ``[n·R × (n_edge + n)]`` and
# target and then delegates the **identical** standardise → PE-guard →
# lstsq → unpack → identifiability → ω tail (the #759 shared
# :func:`_solve_symmetric_joint`). Before this refactor each lineage
# bolted another ``estimate_swing_coupling_*`` public function onto the
# module with its design build inlined — an open-loop universal sink
# (521 → 1322 LOC, +154 % over five lineages, monotonic). The strategy
# registry below caps that accretion: a new symmetric-joint estimation
# path must register a :class:`SwingDesignStrategy` (encapsulating only
# its design/target assembly) — it cannot edit the dispatcher core.
#
# This is a behaviour-preserving, structure-only extraction: the design
# / target each strategy returns is byte-for-byte the array the former
# inline block built, and the shared tail is unchanged, so ``K̂`` / ``P̂``
# / ``ω̂`` / the identifiability score / the PE verdict are bit-identical
# (pinned by the existing bit-stability tests and the added golden
# vectors).


@dataclass(frozen=True, slots=True)
class SwingDesign:
    """Path-specific global design assembled by a swing strategy.

    The four fields are exactly the positional arguments the shared
    :func:`_solve_symmetric_joint` back end consumes (the ``damping``
    and the three solver flags are supplied by the dispatcher, not the
    strategy — they are path-independent).

    Attributes
    ----------
    design : np.ndarray
        Global design ``(n·R, n_edge + n)`` (``R`` = per-node rows:
        ``t_len`` differential / ``n_windows`` weak).
    target : np.ndarray
        Global target ``(n·R,)``.
    edges : list[tuple[int, int]]
        Unordered edge list ``[(a, b) : a < b]`` indexing the first
        ``n_edge`` design columns.
    n_edge : int
        Edge count (``n_param = n_edge + n``).
    """

    design: NDArray[np.float64]
    target: NDArray[np.float64]
    edges: list[tuple[int, int]]
    n_edge: int


@runtime_checkable
class SwingDesignStrategy(Protocol):
    """Frozen contract every symmetric-joint swing path must satisfy.

    A strategy encapsulates **only** the path-specific design/target
    assembly. It never solves, never standardises, never touches the
    PE guard or the identifiability layer — that shared tail lives once
    in :func:`_solve_symmetric_joint`. This is the structural boundary
    that caps the monotonic accretion: adding a future estimation path
    means implementing + registering a strategy, not editing the
    dispatcher.

    Implementations are stateless callables registered under a unique
    string key in :data:`_SWING_STRATEGY_REGISTRY`.
    """

    @property
    def key(self) -> str:
        """Stable registry key (the estimation-path identity)."""
        ...

    def build(
        self,
        theta_wrapped: NDArray[np.float64],
        inertia: NDArray[np.float64],
        damping: NDArray[np.float64],
        *,
        dt: float,
        params: Mapping[str, int],
    ) -> SwingDesign:
        """Assemble the path-specific global design and target.

        ``params`` carries the path-specific integer hyperparameters
        already validated by the dispatcher (the differential path uses
        ``savgol_window`` / ``savgol_polyorder``; the weak path uses
        ``test_support`` / ``n_windows`` / ``bump_order``). The contract
        (shape / sign / ``dt``) has been enforced upstream so the
        strategy only does numeric assembly.
        """
        ...


_SWING_STRATEGY_REGISTRY: dict[str, SwingDesignStrategy] = {}


def _register_swing_strategy(strategy: SwingDesignStrategy) -> SwingDesignStrategy:
    """Register a swing design strategy under its unique key.

    Fail-closed on a duplicate key — a silent overwrite would let a new
    lineage shadow an audited path's design assembly.
    """
    if strategy.key in _SWING_STRATEGY_REGISTRY:
        raise ValueError(f"swing strategy key {strategy.key!r} already registered")
    _SWING_STRATEGY_REGISTRY[strategy.key] = strategy
    return strategy


def swing_strategy_registry() -> Mapping[str, SwingDesignStrategy]:
    """Read-only view of the registered swing design strategies.

    Consumed by the architectural forcing-function test, which asserts
    every public symmetric-joint swing estimation entry point dispatches
    through exactly the registered strategy set (no path may bypass the
    registry).
    """

    return MappingProxyType(_SWING_STRATEGY_REGISTRY)


def _dispatch_swing(
    strategy_key: str,
    theta_wrapped: NDArray[np.float64],
    inertia: NDArray[np.float64],
    damping: NDArray[np.float64],
    *,
    dt: float,
    params: Mapping[str, int],
    pe_guard: bool,
    pe_min_singular_ratio: float,
    identifiability_gate: bool,
) -> SwingCouplingEstimate:
    """Select a registered strategy, assemble its design, run the tail.

    The single dispatcher core. It is path-*independent*: a new
    symmetric-joint estimation path is added by registering a strategy,
    never by editing this function (the module-scale negative-feedback
    term — see the registry preamble).
    """
    strategy = _SWING_STRATEGY_REGISTRY[strategy_key]
    sd = strategy.build(
        theta_wrapped,
        inertia,
        damping,
        dt=dt,
        params=params,
    )
    n = theta_wrapped.shape[1]
    return _solve_symmetric_joint(
        sd.design,
        sd.target,
        sd.edges,
        sd.n_edge,
        n,
        damping,
        pe_guard=pe_guard,
        pe_min_singular_ratio=pe_min_singular_ratio,
        identifiability_gate=identifiability_gate,
    )


@dataclass(frozen=True, slots=True)
class _DifferentialSwingStrategy:
    """R1 differential symmetric-joint design (CALIB-GRID-001 R1).

    Savitzky–Golay second-derivative swing target ``m θ̈ + d θ̇`` with one
    shared parameter per unordered edge and one injection per node.
    Path-specific assembly only — the standardise → PE → solve → unpack
    → identifiability → ω tail is the shared :func:`_solve_symmetric_joint`.
    """

    key: str = "differential_symmetric"

    def build(
        self,
        theta_wrapped: NDArray[np.float64],
        inertia: NDArray[np.float64],
        damping: NDArray[np.float64],
        *,
        dt: float,
        params: Mapping[str, int],
    ) -> SwingDesign:
        theta = theta_wrapped
        m = inertia
        d = damping
        _, n = theta.shape
        savgol_window = params["savgol_window"]
        savgol_polyorder = params["savgol_polyorder"]
        if savgol_window < 5:
            raise ValueError("savgol_window must be ≥ 5")
        if savgol_polyorder < 2:
            raise ValueError("savgol_polyorder must be ≥ 2 (need a non-zero 2nd derivative)")
        theta_dot, theta_ddot = _savgol_derivatives(
            theta, dt, window=savgol_window, polyorder=savgol_polyorder
        )
        t_len = theta.shape[0]

        # One shared parameter per unordered edge (a < b) + one P_i per
        # node. Node a's equation sees +sin(θ_a−θ_b) for edge (a,b);
        # node b's equation sees sin(θ_b−θ_a) = −sin(θ_a−θ_b). Stack all
        # N·T scalar equations into one global least-squares problem.
        edges = [(a, b) for a in range(n) for b in range(a + 1, n)]
        n_edge = len(edges)
        edge_index = {e: p for p, e in enumerate(edges)}
        n_param = n_edge + n  # edge couplings, then per-node injections

        design = np.zeros((n * t_len, n_param), dtype=np.float64)
        target = np.zeros(n * t_len, dtype=np.float64)
        for i in range(n):
            r0, r1 = i * t_len, (i + 1) * t_len
            target[r0:r1] = m[i] * theta_ddot[:, i] + d[i] * theta_dot[:, i]
            for j in range(n):
                if j == i:
                    continue
                a, b = (i, j) if i < j else (j, i)
                # y = P_i + Σ (−K_ij) sin(θ_i − θ_j); the design column
                # is therefore the coefficient of (−K_{ij}).
                col = edge_index[(a, b)]
                design[r0:r1, col] += np.sin(theta[:, i] - theta[:, j])
            design[r0:r1, n_edge + i] = 1.0

        return SwingDesign(
            design=np.asarray(design, dtype=np.float64),
            target=np.asarray(target, dtype=np.float64),
            edges=edges,
            n_edge=n_edge,
        )


@dataclass(frozen=True, slots=True)
class _IntegralSwingStrategy:
    """Weak / integral-form symmetric-joint design (CALIB-GRID-002).

    The swing identity is projected onto compactly supported test
    functions and integrated, so the phase is never differentiated.
    Path-specific assembly only — the solve tail is the same shared
    :func:`_solve_symmetric_joint` as the differential path.
    """

    key: str = "integral_weak_form"

    def build(
        self,
        theta_wrapped: NDArray[np.float64],
        inertia: NDArray[np.float64],
        damping: NDArray[np.float64],
        *,
        dt: float,
        params: Mapping[str, int],
    ) -> SwingDesign:
        m = inertia
        d = damping
        t_len, n = theta_wrapped.shape
        test_support = params["test_support"]
        n_windows = params["n_windows"]
        bump_order = params["bump_order"]
        if bump_order < 2:
            raise ValueError("bump_order must be ≥ 2 (need a finite, C¹ test function)")
        if n_windows < 1:
            raise ValueError("n_windows must be ≥ 1")
        if test_support < 5:
            raise ValueError("test_support must be ≥ 5 samples")
        half = min(test_support, t_len - 1) // 2
        if half < 2:
            raise ValueError(
                f"test_support {test_support} too large for trajectory length {t_len} "
                f"(need at least one full window inside the record)"
            )

        # The phase enters the integrals *unwrapped* (the wrapped jumps
        # are not physical); φ never differentiates it — the whole point.
        theta = np.unwrap(theta_wrapped, axis=0)
        phi, dphi, d2phi = _test_function_stencil(half, bump_order, dt)

        # Uniformly placed window centres (clipped so every window fits).
        lo, hi = half, t_len - half - 1
        if hi <= lo:
            raise ValueError(f"trajectory length {t_len} too short for support {2 * half + 1}")
        centres = np.unique(np.linspace(lo, hi, n_windows).astype(np.int64))
        n_w = int(centres.size)

        edges = [(a, b) for a in range(n) for b in range(a + 1, n)]
        n_edge = len(edges)
        edge_index = {e: p for p, e in enumerate(edges)}
        n_param = n_edge + n

        design = np.zeros((n * n_w, n_param), dtype=np.float64)
        target = np.zeros(n * n_w, dtype=np.float64)
        int_phi = float(np.trapezoid(phi, dx=dt))
        for i in range(n):
            for wi in range(n_w):
                c = int(centres[wi])
                row = i * n_w + wi
                sl = slice(c - half, c + half + 1)
                theta_i = theta[sl, i]
                # Weak target: m_i ∫φ'' θ_i − d_i ∫φ' θ_i (no phase deriv).
                target[row] = m[i] * float(np.trapezoid(d2phi * theta_i, dx=dt)) - d[i] * float(
                    np.trapezoid(dphi * theta_i, dx=dt)
                )
                for j in range(n):
                    if j == i:
                        continue
                    a, b = (i, j) if i < j else (j, i)
                    col = edge_index[(a, b)]
                    sin_ij = np.sin(theta[sl, i] - theta[sl, j])
                    # y = P_i ∫φ + Σ(−K_ij) ∫φ sin(θ_i−θ_j); the design
                    # column is the coefficient of (−K_{ij}).
                    design[row, col] += float(np.trapezoid(phi * sin_ij, dx=dt))
                design[row, n_edge + i] = int_phi

        return SwingDesign(
            design=np.asarray(design, dtype=np.float64),
            target=np.asarray(target, dtype=np.float64),
            edges=edges,
            n_edge=n_edge,
        )


_register_swing_strategy(_DifferentialSwingStrategy())
_register_swing_strategy(_IntegralSwingStrategy())


def _solve_symmetric_joint(
    design: NDArray[np.float64],
    target: NDArray[np.float64],
    edges: list[tuple[int, int]],
    n_edge: int,
    n: int,
    damping: NDArray[np.float64],
    *,
    pe_guard: bool,
    pe_min_singular_ratio: float,
    identifiability_gate: bool,
) -> SwingCouplingEstimate:
    r"""Shared symmetric-joint least-squares back end (structure-only).

    Both swing identifiers — the differential
    :func:`estimate_swing_coupling` (``symmetric=True``) and the
    weak/integral :func:`estimate_swing_coupling_integral` — assemble a
    *different* global design ``[n·rows × (n_edge + n)]`` and target, but
    then run an **identical** tail: column-standardise, take the
    persistent-excitation diagnostic on the standardised design, raise
    :class:`PersistentExcitationError` if guarded and rank-deficient,
    solve the back-transformed least squares, unpack ``K_{ab}=-coef_p``
    and ``P_i=coef_{n_edge+i}``, optionally attach the additive
    identifiability report, and reduce ``ω = P/d``.

    This function is the single copy of that tail. It performs the
    *exact same operations in the exact same order* as the two former
    inline copies, so ``K``/``P``/``ω`` are **bit-identical** before and
    after the extraction (no algorithm change — pinned by the existing
    bit-stability tests and the calibration golden ledgers).

    Parameters
    ----------
    design, target : np.ndarray
        The lineage-specific global design ``(n·R, n_edge+n)`` and
        target ``(n·R,)`` (``R`` = per-node rows: ``t_len`` differential
        / ``n_windows`` weak).
    edges : list[tuple[int, int]]
        Unordered edge list ``[(a, b) : a < b]`` indexing the first
        ``n_edge`` design columns.
    n_edge, n : int
        Edge count and node count (``n_param = n_edge + n``).
    damping : np.ndarray
        Per-node ``d_i ≥ 0`` for the ``ω = P/d`` reduction.
    pe_guard, pe_min_singular_ratio, identifiability_gate
        Same semantics as the public estimators (see their docstrings).

    Returns
    -------
    SwingCouplingEstimate
        Signed symmetric ``K``, injection ``P``, ``ω``, the reciprocal
        condition number and (optional) identifiability report.

    Raises
    ------
    PersistentExcitationError
        When ``pe_guard`` and the standardised design is rank-deficient
        (``worst_ratio < pe_min_singular_ratio``).
    """
    d = damping
    # Standardise every column (the per-node intercept blocks have a
    # well-defined non-zero std). bounds: a fully constant column
    # (degenerate edge) keeps unit scale so the PE diagnostic flags it
    # rather than dividing by zero.
    scale = design.std(axis=0, ddof=0)
    scale_safe = np.where(scale > 1e-12, scale, 1.0)
    design_std = design / scale_safe

    worst_ratio = _singular_ratio(design_std)
    if pe_guard and worst_ratio < pe_min_singular_ratio:
        raise PersistentExcitationError(-1, worst_ratio, pe_min_singular_ratio)

    coef_std, *_ = np.linalg.lstsq(design_std, target, rcond=None)
    coef = coef_std / scale_safe

    k_hat = np.zeros((n, n), dtype=np.float64)
    for p_idx, (a, b) in enumerate(edges):
        k_ab = -float(coef[p_idx])  # K = −(design coefficient)
        k_hat[a, b] = k_ab
        k_hat[b, a] = k_ab
    injection = np.asarray(coef[n_edge:], dtype=np.float64)

    identifiability: IdentifiabilityReport | None = None
    if identifiability_gate:
        # Reuse the *exact* design_std / target / coef_std / scale
        # already solved — the point estimate is untouched (additive).
        # K̂_ab = −coef_p, so SE(K̂_ab) = SE(coef_p): the negation is a
        # unit-modulus map and leaves the standard error invariant; pass
        # k_hat (already negated) so the CIs are in signed-coupling units.
        edge_se, residual_var, r_squared = linearised_edge_covariance(
            np.asarray(design_std, dtype=np.float64),
            np.asarray(target, dtype=np.float64),
            np.asarray(coef_std, dtype=np.float64),
            np.asarray(scale_safe, dtype=np.float64),
            n_edge,
        )
        identifiability = front_gate_verdict(
            k_hat,
            edges,
            edge_se,
            worst_ratio,
            residual_var,
            r_squared,
        )

    # ω_i = P_i / d_i (over-damped reduction). Guard d_i = 0 explicitly.
    with np.errstate(divide="ignore", invalid="ignore"):
        omega = np.where(d > 0.0, injection / np.where(d > 0.0, d, 1.0), 0.0)

    return SwingCouplingEstimate(
        K=np.asarray(k_hat, dtype=np.float64),
        injection=np.asarray(injection, dtype=np.float64),
        omega=np.asarray(omega, dtype=np.float64),
        min_singular_ratio=float(worst_ratio),
        identifiability=identifiability,
    )


def estimate_swing_coupling(
    phases: PhaseMatrix,
    inertia: NDArray[np.float64],
    damping: NDArray[np.float64],
    *,
    dt: float,
    symmetric: bool = True,
    savgol_window: int = 51,
    savgol_polyorder: int = 4,
    pe_min_singular_ratio: float = 1e-3,
    pe_guard: bool = True,
    identifiability_gate: bool = False,
) -> SwingCouplingEstimate:
    r"""Identify ``K_ij``, ``P_i`` and ``ω_i`` from second-order swing data.

    The swing identity per oscillator ``i`` is

    .. math::

        m_i\,\ddot\theta_i(t) + d_i\,\dot\theta_i(t)
            \;=\; P_i \;+\; \sum_{j\neq i} (-K_{ij})\,
                \sin\!\bigl(\theta_i(t) - \theta_j(t)\bigr) ,

    where the derivatives are obtained by second-order central finite
    differences of the unwrapped phase.

    Two solver variants are exposed via ``symmetric``:

    * ``symmetric=True`` (default) — a **single joint** least-squares
      over all nodes with one shared parameter per *unordered* edge
      ``K_{ij}=K_{ji}`` and one injection ``P_i`` per node. This encodes
      the physical invariant that a lossless power-network coupling is
      symmetric (PREREGISTRATION § 2; ``grid_data`` builds a symmetric
      ``K``), halves the parameter count, and removes the antisymmetric
      residual that an unconstrained row solver produces on weakly
      excited near-locked trajectories. The persistent-excitation
      diagnostic is taken on this *global* standardised design.
    * ``symmetric=False`` — the unconstrained per-row OLS (one
      independent fit per node). Kept for diagnostic comparison.

    The design columns are standardised before the solve and the
    coefficients back-transformed, so the persistent-excitation
    diagnostic is scale-free.

    Parameters
    ----------
    phases : PhaseMatrix
        Wrapped phase trajectory (the contract guarantees ``[0, 2π)``).
    inertia, damping : np.ndarray
        Per-node ``m_i > 0`` and ``d_i ≥ 0`` (length ``N``). These are
        the *known* machine constants of the swing model; the coupling
        and injection are the unknowns.
    dt : float
        Sampling interval matching ``phases.timestamps`` units.
    symmetric : bool
        Solver variant (see above). Default ``True`` (physically correct
        for a lossless network coupling).
    savgol_window, savgol_polyorder : int
        Savitzky–Golay window length and polynomial order for the
        ``(θ̇, θ̈)`` estimate. ``window`` is forced odd and clipped to
        the trajectory length; ``polyorder`` is clipped below ``window``.
    pe_min_singular_ratio : float
        Minimum acceptable smallest-to-largest singular-value ratio of
        any per-node standardised design. Below this the design is
        treated as rank-deficient (phase-locked input).
    pe_guard : bool
        If ``True`` (default) a sub-threshold design raises
        :class:`PersistentExcitationError` (fail-closed). If ``False``
        the diagnostic is still reported on the result but the
        (untrustworthy) estimate is returned anyway — for diagnostic
        sweeps only.
    identifiability_gate : bool
        **Additive, opt-in** (default ``False`` ⇒ behaviour and point
        estimates bit-identical to the merged R1 path). When ``True``
        *and* ``symmetric=True``, the linearised regression covariance
        of the joint solve is propagated into per-edge 95 % confidence
        intervals and a bounded identifiability score; the resulting
        :class:`~core.kuramoto.identifiability.IdentifiabilityReport`
        (``ACCEPT`` / ``REFUSE`` + score + reason + per-edge CIs) is
        attached to ``SwingCouplingEstimate.identifiability``. This is a
        *graded self-knowledge layer* sitting **above** the hard PE
        guard — it does not raise and does not alter ``K``/``P``/``ω``;
        it lets the caller see when the instrument is out of envelope
        (e.g. the noisy calibration regime) instead of trusting a
        misleading point estimate. Theory + REFUSE threshold:
        ``research/calibration/grid_kuramoto/identifiability/THRESHOLD_PROVENANCE.md``.

    Returns
    -------
    SwingCouplingEstimate
        Signed ``K``, recovered injection ``P``, natural frequency
        ``ω = P / d``, the worst persistent-excitation ratio and (when
        ``identifiability_gate`` and ``symmetric``) the additive
        :class:`~core.kuramoto.identifiability.IdentifiabilityReport`.

    Raises
    ------
    ValueError
        On contract violations (shape / sign / ``dt``) — fail-closed,
        no silent repair.
    PersistentExcitationError
        When ``pe_guard`` is set and any row design is rank-deficient.
    """
    if dt <= 0.0:
        raise ValueError("dt must be > 0")
    if not 0.0 < pe_min_singular_ratio < 1.0:
        raise ValueError("pe_min_singular_ratio must lie in (0, 1)")

    theta = np.asarray(phases.theta, dtype=np.float64)
    _, n = theta.shape
    m = np.asarray(inertia, dtype=np.float64)
    d = np.asarray(damping, dtype=np.float64)
    if m.shape != (n,) or d.shape != (n,):
        raise ValueError(f"inertia and damping must both have shape ({n},)")
    if not np.all(np.isfinite(m)) or not np.all(np.isfinite(d)):
        raise ValueError("inertia and damping must be finite")
    if np.any(m <= 0.0):
        raise ValueError("inertia must be strictly positive")
    if np.any(d < 0.0):
        raise ValueError("damping must be non-negative")

    if symmetric:
        # Symmetric-joint path: a registered strategy assembles the
        # path-specific differential design (Savitzky–Golay derivatives
        # + one shared parameter per unordered edge + one P_i per node)
        # and the single dispatcher runs the shared standardise → PE →
        # solve → unpack → identifiability → ω tail. The strategy
        # performs the *exact same operations in the exact same order*
        # as the former inline block, so the estimate is bit-identical
        # (algorithm-preserving extraction — pinned by the R1
        # bit-stability tests and the added golden vectors). Adding a
        # future symmetric-joint path means registering a strategy, not
        # editing this dispatcher (module-scale forcing function).
        return _dispatch_swing(
            "differential_symmetric",
            theta,
            m,
            d,
            dt=dt,
            params={
                "savgol_window": savgol_window,
                "savgol_polyorder": savgol_polyorder,
            },
            pe_guard=pe_guard,
            pe_min_singular_ratio=pe_min_singular_ratio,
            identifiability_gate=identifiability_gate,
        )

    if savgol_window < 5:
        raise ValueError("savgol_window must be ≥ 5")
    if savgol_polyorder < 2:
        raise ValueError("savgol_polyorder must be ≥ 2 (need a non-zero 2nd derivative)")
    theta_dot, theta_ddot = _savgol_derivatives(
        theta, dt, window=savgol_window, polyorder=savgol_polyorder
    )
    t_len = theta.shape[0]

    k_hat = np.zeros((n, n), dtype=np.float64)
    injection = np.zeros(n, dtype=np.float64)
    identifiability: IdentifiabilityReport | None = None

    # Asymmetric variant: unconstrained per-row OLS (one independent fit
    # per node). Kept for diagnostic comparison; the symmetric joint
    # solve above is the physically correct, calibrated path.
    worst_ratio = 1.0
    for i in range(n):
        # Target: y_i = m_i θ̈_i + d_i θ̇_i
        y = m[i] * theta_ddot[:, i] + d[i] * theta_dot[:, i]
        # Regressors: [sin(θ_i − θ_j)]_{j≠i} and a constant for P_i.
        others = [j for j in range(n) if j != i]
        sin_cols = np.sin(theta[:, i][:, None] - theta[:, others])  # (T, n-1)
        design_row = np.column_stack([sin_cols, np.ones(t_len)])

        # Standardise the sine columns (the intercept column is left
        # as a unit constant so its coefficient stays physical).
        sin_scale = sin_cols.std(axis=0, ddof=0)
        # bounds: a near-constant regressor (phase-locked pair) gets
        # a unit scale so the PE diagnostic — not a divide-by-zero —
        # flags the degeneracy.
        sin_scale_safe = np.where(sin_scale > 1e-12, sin_scale, 1.0)
        design_std = design_row.copy()
        design_std[:, :-1] = sin_cols / sin_scale_safe

        ratio = _singular_ratio(design_std)
        worst_ratio = min(worst_ratio, ratio)
        if pe_guard and ratio < pe_min_singular_ratio:
            raise PersistentExcitationError(i, ratio, pe_min_singular_ratio)

        coef_std, *_ = np.linalg.lstsq(design_std, y, rcond=None)
        # Back-transform the standardised sine coefficients.
        coef = coef_std.copy()
        coef[:-1] = coef_std[:-1] / sin_scale_safe

        # y = P_i + Σ (−K_ij) sin(θ_i − θ_j)  ⇒  K_ij = −coef_j .
        for col, j in enumerate(others):
            k_hat[i, j] = -coef[col]
        injection[i] = coef[-1]

    # ω_i = P_i / d_i (over-damped reduction). Guard d_i = 0 explicitly.
    with np.errstate(divide="ignore", invalid="ignore"):
        omega = np.where(d > 0.0, injection / np.where(d > 0.0, d, 1.0), 0.0)

    return SwingCouplingEstimate(
        K=np.asarray(k_hat, dtype=np.float64),
        injection=np.asarray(injection, dtype=np.float64),
        omega=np.asarray(omega, dtype=np.float64),
        min_singular_ratio=float(worst_ratio),
        identifiability=identifiability,
    )


# ---------------------------------------------------------------------------
# Integral / weak-form (test-function) swing identification — CALIB-GRID-002
# ---------------------------------------------------------------------------
#
# The R1 path above forms the swing target ``m θ̈ + d θ̇`` by *double*
# numerical differentiation of the phase (Savitzky–Golay ``deriv=2``).
# Differentiation is a high-pass operator: it amplifies additive
# measurement noise by ``∝ 1/Δt`` per derivative, so a second derivative
# multiplies the noise PSD by ``ω⁴``. CALIB-GRID-001 R1 proved a swept
# Savitzky–Golay verification could not push the σ=0.02 Frobenius error
# below ≈0.61 at the frozen record length: no consistent *differential*
# estimator exists there.
#
# This path is a legitimately different estimator class — the **weak /
# integral form** (Messenger & Bortz, "Weak SINDy for partial
# differential equations", J. Comput. Phys. 443 (2021) 110525; and
# "Weak SINDy: Galerkin-based data-driven model selection", Multiscale
# Model. Simul. 19(3) (2021) 1474). Pick a family of compactly
# supported, ``C^{≥2}`` test functions ``φ_k(t)`` (each vanishing with
# its first derivative at the window endpoints). Multiply the swing
# identity by ``φ_k`` and integrate over the window. Integration by
# parts moves *both* time derivatives off the noisy phase and onto the
# analytically known test function:
#
#     ∫ φ_k · m_i θ̈_i dt =  m_i ∫ φ_k'' θ_i dt
#     ∫ φ_k · d_i θ̇_i dt = −d_i ∫ φ_k'  θ_i dt
#
# (the boundary terms ``[φ_k θ̇]`` and ``[φ_k' θ]`` vanish because
# ``φ_k = φ_k' = 0`` at the endpoints). The resulting linear system
#
#     m_i ∫ φ_k'' θ_i − d_i ∫ φ_k' θ_i
#         = P_i ∫ φ_k + Σ_{j≠i} (−K_ij) ∫ φ_k sin(θ_i − θ_j)
#
# contains **only θ and the analytic derivatives of φ** — the phase is
# never differentiated. Integration is a *low-pass* operator: the
# quadrature ``∫ φ_k η dt`` of zero-mean measurement noise ``η`` has
# variance ``∝ σ² ‖φ_k‖² Δt`` and *averages noise down*, the exact
# opposite of the ``ω⁴`` blow-up of double differentiation. This is the
# documented noise-propagation advantage and the reason the class is
# different, not merely a re-tuned differential estimator.


def _test_function_stencil(
    half: int,
    bump_order: int,
    dt: float,
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
    r"""Compact ``C^{bump_order-1}`` test function ``φ`` and ``φ'``, ``φ''``.

    The canonical Messenger–Bortz weak-form test function is the
    bump ``φ(s) = (1 - s²)^p`` on the reference interval ``s ∈ [-1, 1]``
    (``s = 0`` at the window centre). For ``p = bump_order ≥ 2`` it is
    ``C^{p-1}`` and ``φ = φ' = 0`` at ``s = ±1``, so the integration-by-
    parts boundary terms vanish exactly. The reference-interval
    derivatives are mapped to physical time by the chain rule with
    ``ds/dt = 1/(half·dt)`` (``half`` samples = half-window in steps):

    .. math::

        \varphi(s)   &= (1-s^2)^p \\
        \varphi'(s)  &= -2 p\, s\,(1-s^2)^{p-1} \\
        \varphi''(s) &= -2 p\,(1-s^2)^{p-1}
                        + 4 p (p-1)\, s^2 (1-s^2)^{p-2}

    Parameters
    ----------
    half : int
        Half-window length in samples; the stencil has ``2·half + 1``
        points. Must be ``≥ 2``.
    bump_order : int
        Polynomial power ``p`` of the bump (``≥ 2`` ⇒ ``φ`` is at least
        ``C¹`` so the boundary terms vanish and ``φ''`` is finite).
    dt : float
        Physical sampling interval (used by the chain rule so the
        returned ``φ'``, ``φ''`` are derivatives w.r.t. *time*).

    Returns
    -------
    phi, dphi, d2phi : np.ndarray
        Length ``2·half + 1`` arrays: the test function and its first
        and second time derivatives, sampled on the stencil.
    """
    p = bump_order
    s = np.arange(-half, half + 1, dtype=np.float64) / float(half)
    one_minus = 1.0 - s**2
    phi = one_minus**p
    # Pin the endpoints to exactly zero (float round-off otherwise leaves
    # ~1e-300 there and would re-introduce a boundary term).
    phi[0] = 0.0
    phi[-1] = 0.0
    dphi_ds = -2.0 * p * s * one_minus ** (p - 1)
    d2phi_ds2 = -2.0 * p * one_minus ** (p - 1) + 4.0 * p * (p - 1) * s**2 * one_minus ** (p - 2)
    inv = 1.0 / (float(half) * dt)
    dphi = dphi_ds * inv
    d2phi = d2phi_ds2 * (inv * inv)
    return (
        np.asarray(phi, dtype=np.float64),
        np.asarray(dphi, dtype=np.float64),
        np.asarray(d2phi, dtype=np.float64),
    )


def estimate_swing_coupling_integral(
    phases: PhaseMatrix,
    inertia: NDArray[np.float64],
    damping: NDArray[np.float64],
    *,
    dt: float,
    test_support: int = 400,
    n_windows: int = 120,
    bump_order: int = 6,
    pe_min_singular_ratio: float = 1e-3,
    pe_guard: bool = True,
    identifiability_gate: bool = False,
) -> SwingCouplingEstimate:
    r"""Identify ``K_ij``, ``P_i``, ``ω_i`` by the **weak / integral form**.

    A legitimately different estimator class from
    :func:`estimate_swing_coupling` (CALIB-GRID-001 R1): the swing
    identity is projected onto a family of compactly supported test
    functions ``φ_k`` and **integrated**, so the phase is never
    differentiated. With ``φ_k = φ_k' = 0`` at every window endpoint,
    integration by parts gives, per node ``i`` and window ``k``,

    .. math::

        m_i\!\int\!\varphi_k''\,\theta_i\,dt
            \;-\; d_i\!\int\!\varphi_k'\,\theta_i\,dt
        \;=\; P_i\!\int\!\varphi_k\,dt
            \;+\;\sum_{j\neq i}(-K_{ij})\!
            \int\!\varphi_k\,\sin(\theta_i-\theta_j)\,dt .

    Only ``θ`` and the *analytic* derivatives of ``φ`` enter the design
    — integration is a low-pass operator (the quadrature of zero-mean
    noise has variance ``∝ σ²‖φ_k‖²Δt`` and averages down) versus the
    ``ω⁴`` high-pass amplification of the differential path's double
    Savitzky–Golay derivative. Literature anchor: Messenger & Bortz,
    *Weak SINDy*, J. Comput. Phys. 443 (2021) 110525 / Multiscale
    Model. Simul. 19(3) (2021) 1474.

    The solver is the symmetric joint least-squares (one shared
    parameter per *unordered* edge ``K_{ij}=K_{ji}`` plus one injection
    ``P_i`` per node) on the column-standardised global weak design, so
    the result is a contract-identical :class:`SwingCouplingEstimate`
    and interoperates unchanged with the merged identifiability
    front-gate (``identifiability_gate=True``).

    Parameters
    ----------
    phases : PhaseMatrix
        Wrapped phase trajectory (the contract guarantees ``[0, 2π)``).
    inertia, damping : np.ndarray
        Per-node ``m_i > 0`` and ``d_i ≥ 0`` (length ``N``).
    dt : float
        Sampling interval matching ``phases.timestamps`` units.
    test_support : int
        Test-function window width in samples (``2·⌊support/2⌋+1`` after
        rounding to an odd stencil). The integration window is the
        low-pass cutoff: wider ⇒ stronger noise rejection, but it must
        stay inside the excited transient. Default ``400``.
    n_windows : int
        Number of window placements (test functions) spread uniformly
        over the trajectory; the global system has ``N·n_windows`` rows.
    bump_order : int
        Polynomial power ``p`` of the ``(1-s²)^p`` test function
        (``≥ 2`` ⇒ ``C^{p-1}`` so the boundary terms vanish).
    pe_min_singular_ratio : float
        Minimum acceptable reciprocal condition number of the
        standardised weak design. Below it the design is treated as
        rank-deficient (phase-locked / under-excited input).
    pe_guard : bool
        If ``True`` (default) a sub-threshold design raises
        :class:`PersistentExcitationError` (fail-closed). If ``False``
        the diagnostic is still reported but the estimate is returned
        anyway — for diagnostic sweeps only.
    identifiability_gate : bool
        **Additive, opt-in** graded self-knowledge layer (default
        ``False`` ⇒ behaviour bit-identical for the point estimate).
        When ``True`` the linearised covariance of the *weak* design is
        propagated into the same
        :class:`~core.kuramoto.identifiability.IdentifiabilityReport`
        the merged front-gate consumes, so the instrument's envelope is
        reported in weak-form units.

    Returns
    -------
    SwingCouplingEstimate
        Signed symmetric ``K``, recovered injection ``P``, natural
        frequency ``ω = P / d``, the reciprocal condition number of the
        weak design and (when ``identifiability_gate``) the additive
        :class:`~core.kuramoto.identifiability.IdentifiabilityReport`.

    Raises
    ------
    ValueError
        On contract violations (shape / sign / ``dt`` / window) —
        fail-closed, no silent repair.
    PersistentExcitationError
        When ``pe_guard`` is set and the weak design is rank-deficient.
    """
    if dt <= 0.0:
        raise ValueError("dt must be > 0")
    if not 0.0 < pe_min_singular_ratio < 1.0:
        raise ValueError("pe_min_singular_ratio must lie in (0, 1)")
    if bump_order < 2:
        raise ValueError("bump_order must be ≥ 2 (need a finite, C¹ test function)")
    if n_windows < 1:
        raise ValueError("n_windows must be ≥ 1")

    theta_wrapped = np.asarray(phases.theta, dtype=np.float64)
    _, n = theta_wrapped.shape
    m = np.asarray(inertia, dtype=np.float64)
    d = np.asarray(damping, dtype=np.float64)
    if m.shape != (n,) or d.shape != (n,):
        raise ValueError(f"inertia and damping must both have shape ({n},)")
    if not np.all(np.isfinite(m)) or not np.all(np.isfinite(d)):
        raise ValueError("inertia and damping must be finite")
    if np.any(m <= 0.0):
        raise ValueError("inertia must be strictly positive")
    if np.any(d < 0.0):
        raise ValueError("damping must be non-negative")

    # Symmetric-joint weak/integral path: a registered strategy
    # assembles the path-specific weak design (test-function projection
    # + integration by parts; the phase is never differentiated) and the
    # single dispatcher runs the *same* shared standardise → PE → solve
    # → unpack → identifiability → ω tail as the differential path. The
    # strategy performs the exact same operations in the exact same
    # order as the former inline block (algorithm-preserving extraction
    # — bit-identical, pinned by the CALIB-GRID-002 bit-stability tests
    # and the added golden vectors). A future symmetric-joint estimator
    # class is added by registering a strategy, never by editing this
    # dispatcher (module-scale forcing function).
    return _dispatch_swing(
        "integral_weak_form",
        theta_wrapped,
        m,
        d,
        dt=dt,
        params={
            "test_support": test_support,
            "n_windows": n_windows,
            "bump_order": bump_order,
        },
        pe_guard=pe_guard,
        pe_min_singular_ratio=pe_min_singular_ratio,
        identifiability_gate=identifiability_gate,
    )
