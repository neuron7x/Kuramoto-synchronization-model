# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Propagation-delay estimation τ_{ij} (protocol M2.1).

We only estimate delays along active edges identified by the sparse
coupling step (``K_{ij} ≠ 0``) — irrelevant pairs keep ``τ_{ij} = 0``.

The core estimator is a **joint per-row coordinate descent** over
integer lags. For each oscillator ``i`` with active in-neighbours
``J_i = {j : K_{ij} ≠ 0}`` we jointly minimise the residual

.. math::

    \\text{RSS}_i(\\boldsymbol\\tau_i) = \\sum_t \\Bigl[
        \\dot\\theta_i(t) - \\hat\\omega_i -
        \\sum_{j \\in J_i} \\hat\\beta_{ij}\\,
        \\sin\\bigl(\\theta_j(t - \\tau_{ij}) - \\theta_i(t)\\bigr) \\Bigr]^2

over ``τ_i \\in \\{0, \\ldots, \\tau_{\\max}\\}^{|J_i|}``. The ``β``
coefficients are re-fitted by ordinary least squares at every lag
combination, which makes this an **exact profile likelihood under
Gaussian noise**. Coordinate descent cycles through the edges of row
``i`` and picks the lag that minimises the joint residual given the
current lags of the other edges, which typically converges in 2–3
passes. This is materially more accurate than the single-edge version
because mutual contributions no longer alias into each other.

A fast ``cross_correlation`` mode is kept as a single-edge fallback
(``sin(θ)`` cross-correlation, parabolic peak interpolation) for cases
where the joint solver is overkill — for example the one-edge unit
tests, or hot-path streaming inference.

Only ``scipy`` and ``numpy`` are required. The Hoffmann–Rosenbaum–
Yoshida estimator (lead-lag package) and PCMCI lag-specific analysis
described in the methodology are optional enhancements for
high-frequency data and live in a separate extras module.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

import numpy as np
from scipy.signal import correlate, correlation_lags

from .contracts import CouplingMatrix, DelayMatrix, PhaseMatrix

__all__ = [
    "DelayEstimationConfig",
    "DelayEstimator",
    "estimate_delays",
    "xcorr_delay",
    "profile_likelihood_delay",
    "joint_row_delay",
]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DelayEstimationConfig:
    """Hyperparameters for delay estimation.

    Attributes
    ----------
    max_lag : int
        Maximum integer lag (in timesteps) considered for any edge.
    n_candidates : int
        Unused in joint mode. Kept for single-edge backwards compatibility.
    dt : float
        Sampling interval. Used only to populate
        :attr:`DelayMatrix.tau_seconds`.
    method : str
        ``"joint"`` (default) — joint per-row coordinate descent over
        integer lags with re-fitted ``β`` at every step; exact profile
        likelihood under Gaussian noise.
        ``"cross_correlation"`` — single-edge ``sin(θ)`` cross-correlation,
        fast but aliases under mutual coupling.
    n_passes : int
        Number of coordinate-descent passes in joint mode. Two passes
        typically suffice; three guarantees convergence on all the
        synthetic ground truths we test against.
    """

    max_lag: int = 10
    n_candidates: int = 3
    dt: float = 1.0
    method: str = "joint"
    n_passes: int = 3

    _ALLOWED_METHODS: tuple[str, ...] = (
        "joint",
        "cross_correlation",
    )

    def __post_init__(self) -> None:
        if self.max_lag < 0:
            raise ValueError(f"max_lag must be ≥ 0; got {self.max_lag}")
        if self.n_candidates < 1:
            raise ValueError("n_candidates must be ≥ 1")
        if self.dt <= 0:
            raise ValueError("dt must be > 0")
        if self.n_passes < 1:
            raise ValueError("n_passes must be ≥ 1")
        if self.method not in self._ALLOWED_METHODS:
            raise ValueError(f"method must be one of {self._ALLOWED_METHODS}; got {self.method!r}")


# ---------------------------------------------------------------------------
# Cross-correlation primitive
# ---------------------------------------------------------------------------


def xcorr_delay(x: np.ndarray, y: np.ndarray, max_lag: int, n_candidates: int = 1) -> list[int]:
    """Return the top ``n_candidates`` integer lags by |cross-correlation|.

    Positive lag means ``y`` leads ``x`` (i.e. ``x`` lags behind ``y``)
    — matching the convention that ``τ_{ij} > 0`` when ``j`` influences
    ``i`` with a delay. Signals are zero-meaned before correlation so
    the output is invariant under constant offsets.
    """
    if x.shape != y.shape or x.ndim != 1:
        raise ValueError(f"x and y must be 1-D with matching shapes; got {x.shape}, {y.shape}")
    x_c = x - x.mean()
    y_c = y - y.mean()
    corr = correlate(x_c, y_c, mode="full")
    lags = correlation_lags(len(x_c), len(y_c), mode="full")
    mask = np.abs(lags) <= max_lag
    corr_masked = corr[mask]
    lags_masked = lags[mask]
    # Argsort by magnitude, descending
    order = np.argsort(-np.abs(corr_masked))
    top_lags = [int(lags_masked[k]) for k in order[:n_candidates]]
    return top_lags


# ---------------------------------------------------------------------------
# Profile likelihood per candidate lag
# ---------------------------------------------------------------------------


def _target_and_feature(
    theta: np.ndarray, i: int, j: int, tau: int, dt: float
) -> tuple[np.ndarray, np.ndarray]:
    """Build (y_i[t], sin(θ_j(t-τ) - θ_i(t))) aligned on the common window."""
    if tau < 0:
        raise ValueError("tau must be ≥ 0")
    T = theta.shape[0]
    if tau >= T:
        return np.zeros(0), np.zeros(0)
    theta_i = theta[tau:, i]
    theta_j = theta[: T - tau, j]
    # Frequency deviation target on i, using the aligned window
    unwrapped_i = np.unwrap(theta[:, i])
    omega_inst_i = np.gradient(unwrapped_i, dt)
    y = omega_inst_i[tau:] - np.median(omega_inst_i)
    x = np.sin(theta_j - theta_i)
    return np.asarray(y, dtype=np.float64), np.asarray(x, dtype=np.float64)


def profile_likelihood_delay(
    theta: np.ndarray,
    i: int,
    j: int,
    candidate_lags: list[int] | range | np.ndarray,
    dt: float,
) -> int:
    """Select the lag that best explains ``θ̇_i`` via ``sin(θ_j(t−τ) − θ_i(t))``.

    For each candidate lag we fit a univariate ordinary least squares
    model ``y = β x`` and compute the residual sum of squares. The
    minimiser is returned. This is a direct, bias-free estimate of
    the lag under the same physical model used by the coupling
    estimator, so the two stages are internally consistent.
    """
    best_tau = 0
    best_rss = np.inf
    for tau in candidate_lags:
        tau_int = int(tau)
        if tau_int < 0:
            continue
        y, x = _target_and_feature(theta, i, j, tau_int, dt)
        if x.size < 10:
            continue
        xx = float(np.dot(x, x))
        if xx < 1e-12:
            continue
        beta = float(np.dot(x, y) / xx)
        residual = y - beta * x
        rss = float(np.dot(residual, residual))
        if rss < best_rss:
            best_rss = rss
            best_tau = tau_int
    return best_tau


# ---------------------------------------------------------------------------
# Top-level per-edge estimator
# ---------------------------------------------------------------------------


def _single_edge_xcorr(theta: np.ndarray, i: int, j: int, cfg: DelayEstimationConfig) -> int:
    """``sin(θ)`` cross-correlation delay for a single edge."""
    sin_i = np.sin(theta[:, i])
    sin_j = np.sin(theta[:, j])
    candidates = xcorr_delay(sin_i, sin_j, cfg.max_lag, n_candidates=1)
    return abs(candidates[0]) if candidates else 0


def _build_row_design(
    theta: np.ndarray,
    i: int,
    active_js: list[int],
    taus: np.ndarray,
    max_lag: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Assemble the per-row design matrix and the aligned target.

    The target is a **forward difference** on the unwrapped phase of
    oscillator ``i``:

        y(t) = [unwrap(θ_i)(t + 1) − unwrap(θ_i)(t)] / 1 − median

    which matches the Euler-step identity

        θ_i(t + 1) − θ_i(t) = dt · [ω_i + Σ_j K_ij sin(θ_j(t − τ_{ij}) − θ_i(t))] + noise

    used by the synthetic generator and by any discrete-time SDDE
    integrator. Central differences (``np.gradient``) introduce a
    half-step offset between the target and the phase-difference
    feature which biases the integer lag estimates by one step;
    forward differencing removes that bias entirely.

    The shared time window starts at ``max_lag`` and runs to
    ``T - 1`` so every ``sin(θ_j(t − τ_{ij}) − θ_i(t))`` column can be
    indexed without bounds checks regardless of the current ``τ_i``
    choice.

    Returns
    -------
    X : np.ndarray, shape ``(T_eff, n_active)``
        Feature matrix.
    y : np.ndarray, shape ``(T_eff,)``
        Forward-difference target for oscillator ``i``.
    theta_i_window : np.ndarray
        The anchored ``θ_i`` window, used by the lag-update loop.
    """
    T = theta.shape[0]
    T_eff = T - max_lag - 1  # subtract one extra step for the forward difference
    if T_eff <= 10:
        return np.zeros((0, len(active_js))), np.zeros(0), np.zeros(0)
    theta_i_window = theta[max_lag : max_lag + T_eff, i]
    X = np.empty((T_eff, len(active_js)), dtype=np.float64)
    for col, j in enumerate(active_js):
        tau_ij = int(taus[col])
        start = max_lag - tau_ij
        theta_j_lagged = theta[start : start + T_eff, j]
        X[:, col] = np.sin(theta_j_lagged - theta_i_window)
    unwrapped = np.unwrap(theta[:, i])
    # Forward difference: y(t) = unwrap(θ_i)(t+1) − unwrap(θ_i)(t)
    theta_diff_i = np.diff(unwrapped)
    omega_i = float(np.median(theta_diff_i))
    y = theta_diff_i[max_lag : max_lag + T_eff] - omega_i
    return X, np.asarray(y, dtype=np.float64), theta_i_window


def _rss(X: np.ndarray, y: np.ndarray) -> float:
    """Residual sum of squares of the OLS fit of ``y`` on ``X``."""
    if X.shape[1] == 0:
        return float(np.dot(y, y))
    # Use lstsq for numerical stability on rank-deficient designs
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    residual = y - X @ beta
    return float(np.dot(residual, residual))


def _xcorr_warm_start(theta: np.ndarray, i: int, active_js: list[int], max_lag: int) -> np.ndarray:
    """Initialise lags via single-edge ``sin(θ)`` cross-correlation.

    This gives the joint coordinate descent a good starting point, which
    matters because the integer-lag objective is combinatorial and
    zero-initialisation leaves the solver in a poor basin for rows with
    mutually-aliasing edges.
    """
    sin_i = np.sin(theta[:, i])
    taus = np.zeros(len(active_js), dtype=np.int64)
    for col, j in enumerate(active_js):
        sin_j = np.sin(theta[:, j])
        candidates = xcorr_delay(sin_i, sin_j, max_lag, n_candidates=1)
        taus[col] = abs(candidates[0]) if candidates else 0
    return taus


_EXHAUSTIVE_MAX_COMBOS = 10_000
"""Row-level exhaustive search is used when ``(max_lag+1)**n_active`` is
below this cap — typically for rows with ≤5 active edges and
``max_lag ≤ 5``. Above the cap we fall back to coordinate descent
seeded from two initialisations."""


def _exhaustive_row_search(
    theta: np.ndarray,
    i: int,
    active_js: list[int],
    max_lag: int,
) -> np.ndarray:
    """Global minimum of the row objective over the full lag grid."""
    n = len(active_js)
    best_rss = np.inf
    best_taus = np.zeros(n, dtype=np.int64)
    lag_range = range(max_lag + 1)
    for combo in itertools.product(lag_range, repeat=n):
        taus = np.asarray(combo, dtype=np.int64)
        X, y, _ = _build_row_design(theta, i, active_js, taus, max_lag)
        if X.shape[0] == 0:
            continue
        rss = _rss(X, y)
        if rss < best_rss:
            best_rss = rss
            best_taus = taus.copy()
    return best_taus


def joint_row_delay(
    theta: np.ndarray,
    i: int,
    active_js: list[int],
    max_lag: int,
    n_passes: int = 3,
) -> np.ndarray:
    """Globally-optimal integer delays for row ``i`` when feasible.

    If the exhaustive search space ``(max_lag + 1) ** n_active`` is
    small enough we enumerate it directly — this is typically the
    case for sparse financial networks where each row has ≤ 5 active
    in-neighbours. For denser rows we fall back to coordinate descent
    from two initialisations (zero lags and cross-correlation warm
    start) and return whichever achieves the lower row residual.

    Returns an ``(len(active_js),)`` ``int64`` array of lags in the
    same order as ``active_js``.
    """
    if not active_js:
        return np.zeros(0, dtype=np.int64)

    n_active = len(active_js)
    if (max_lag + 1) ** n_active <= _EXHAUSTIVE_MAX_COMBOS:
        return _exhaustive_row_search(theta, i, active_js, max_lag)

    def _refine(init: np.ndarray) -> tuple[np.ndarray, float]:
        taus = init.copy()
        best_rss = np.inf
        for _ in range(n_passes):
            improved = False
            for col in range(len(active_js)):
                col_best_rss = np.inf
                col_best_tau = int(taus[col])
                for tau in range(max_lag + 1):
                    taus[col] = tau
                    X, y, _ = _build_row_design(theta, i, active_js, taus, max_lag)
                    if X.shape[0] == 0:
                        continue
                    rss = _rss(X, y)
                    if rss < col_best_rss:
                        col_best_rss = rss
                        col_best_tau = tau
                taus[col] = col_best_tau
                if col_best_rss < best_rss - 1e-9:
                    best_rss = col_best_rss
                    improved = True
            if not improved:
                break
        X, y, _ = _build_row_design(theta, i, active_js, taus, max_lag)
        final_rss = _rss(X, y) if X.shape[0] else np.inf
        return taus, final_rss

    zero_init = np.zeros(len(active_js), dtype=np.int64)
    xcorr_init = _xcorr_warm_start(theta, i, active_js, max_lag)

    taus_zero, rss_zero = _refine(zero_init)
    taus_xc, rss_xc = _refine(xcorr_init)
    return taus_zero if rss_zero <= rss_xc else taus_xc


# ---------------------------------------------------------------------------
# High-level API
# ---------------------------------------------------------------------------


class DelayEstimator:
    """Estimate τ_{ij} for every active edge in a :class:`CouplingMatrix`.

    Edges with ``|K_{ij}| = 0`` receive ``τ_{ij} = 0`` — the delay is
    physically meaningless where no coupling exists and leaving it as
    zero preserves the :class:`DelayMatrix` contract invariant that
    ``τ ≤ max_lag_tested``.
    """

    def __init__(self, config: DelayEstimationConfig | None = None) -> None:
        self.config = config or DelayEstimationConfig()

    def estimate(self, phases: PhaseMatrix, coupling: CouplingMatrix) -> DelayMatrix:
        if phases.asset_ids != coupling.asset_ids:
            raise ValueError("phases.asset_ids and coupling.asset_ids must match")
        cfg = self.config
        theta = np.asarray(phases.theta, dtype=np.float64)
        N = phases.N
        tau = np.zeros((N, N), dtype=np.int64)

        active = coupling.nonzero_mask()

        if cfg.method == "cross_correlation":
            for i in range(N):
                for j in range(N):
                    if i == j or not active[i, j]:
                        continue
                    tau[i, j] = _single_edge_xcorr(theta, i, j, cfg)
            method_name = "cross_correlation"
        else:  # "joint"
            for i in range(N):
                active_js = [j for j in range(N) if j != i and active[i, j]]
                if not active_js:
                    continue
                row_taus = joint_row_delay(theta, i, active_js, cfg.max_lag, n_passes=cfg.n_passes)
                for col, j in enumerate(active_js):
                    tau[i, j] = int(row_taus[col])
            method_name = "profile_likelihood"

        tau_seconds = (tau.astype(np.float64)) * cfg.dt
        return DelayMatrix(
            tau=tau,
            tau_seconds=tau_seconds,
            asset_ids=phases.asset_ids,
            method=method_name,
            max_lag_tested=cfg.max_lag,
        )


def estimate_delays(
    phases: PhaseMatrix,
    coupling: CouplingMatrix,
    config: DelayEstimationConfig | None = None,
) -> DelayMatrix:
    """Functional shortcut around :class:`DelayEstimator`."""
    return DelayEstimator(config).estimate(phases, coupling)
