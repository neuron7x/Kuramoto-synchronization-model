# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Causal validation of identified coupling via lag-specific tests (M1.5).

The methodology asks us to cross-check the sparse coupling matrix
against an independent causal-discovery algorithm. The reference
choice is PCMCI (tigramite), which we expose through an optional
adapter — it is a heavy C/OpenMP dependency that we are unwilling to
pin into the core environment.

As a fall-back that always works on a bare numpy/scipy install we
ship a lightweight lag-specific Granger-style test: for every ordered
pair ``(j → i)`` and every lag ``τ ∈ [1, max_lag]`` we compare the
residuals of two linear regressions on ``sin(θ_i(t))`` — a restricted
model using only the oscillator's own past, and an unrestricted model
that also includes ``sin(θ_j(t − τ))``. The ``F``-statistic is
converted to a p-value via ``scipy.stats``. This is not a substitute
for PCMCI (it ignores conditioning sets and therefore over-reports
indirect causes) but it is a cheap and exposure-safe sanity check
that is reproducible on any machine.

Both backends return the same :class:`CausalValidationReport`, so the
downstream Jaccard overlap computation against the identified
coupling is identical.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats

from .contracts import CouplingMatrix, PhaseMatrix

__all__ = [
    "CausalValidationReport",
    "CausalValidationConfig",
    "lag_granger_causality",
    "pcmci_causality",
    "compare_to_coupling",
]


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CausalValidationReport:
    """Result of an independent causal-discovery run.

    Attributes
    ----------
    causal_graph : np.ndarray
        Boolean ``(N, N)`` matrix where ``causal_graph[i, j] = True``
        means “``j`` is a significant cause of ``i``” under the chosen
        significance threshold.
    p_values : np.ndarray
        ``(N, N)`` array of the best (smallest) p-value across the
        tested lag grid for each ordered pair. Diagonal is set to
        ``nan``.
    best_lag : np.ndarray
        ``(N, N)`` int array of the lag at which the best p-value was
        achieved. ``0`` on the diagonal.
    method : str
        Name of the backend that produced the report.
    """

    causal_graph: np.ndarray
    p_values: np.ndarray
    best_lag: np.ndarray
    method: str

    def __post_init__(self) -> None:
        for name in ("causal_graph", "p_values", "best_lag"):
            arr = getattr(self, name)
            if isinstance(arr, np.ndarray):
                arr_ro = arr.copy()
                arr_ro.flags.writeable = False
                object.__setattr__(self, name, arr_ro)


@dataclass(frozen=True, slots=True)
class CausalValidationConfig:
    """Hyperparameters for causal validation backends.

    Attributes
    ----------
    max_lag : int
        Largest lag tested, in timesteps.
    alpha : float
        Significance threshold on the per-pair p-value.
    backend : str
        ``"granger"`` (default, pure numpy) or ``"pcmci"``
        (optional, requires ``tigramite``).
    """

    max_lag: int = 5
    alpha: float = 0.01
    backend: str = "granger"

    _ALLOWED_BACKENDS: tuple[str, ...] = ("granger", "pcmci")

    def __post_init__(self) -> None:
        if self.max_lag < 1:
            raise ValueError("max_lag must be ≥ 1")
        if not 0.0 < self.alpha < 1.0:
            raise ValueError("alpha must lie in (0, 1)")
        if self.backend not in self._ALLOWED_BACKENDS:
            raise ValueError(
                f"backend must be one of {self._ALLOWED_BACKENDS}; got {self.backend!r}"
            )


# ---------------------------------------------------------------------------
# Lag-specific Granger test (pure numpy)
# ---------------------------------------------------------------------------


def _ols_rss(X: np.ndarray, y: np.ndarray) -> tuple[float, int]:
    """Ordinary least squares residual sum of squares and rank."""
    if X.size == 0:
        centred = y - y.mean()
        return float(np.dot(centred, centred)), 0
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    return float(np.dot(resid, resid)), int(X.shape[1])


def lag_granger_causality(
    phases: PhaseMatrix,
    *,
    config: CausalValidationConfig | None = None,
) -> CausalValidationReport:
    """Lag-specific Granger causality on ``sin(θ)`` observables.

    For every ordered pair ``(j → i)`` and every ``τ ∈ [1, max_lag]``
    we regress ``sin(θ_i(t))`` on its own lag-1 past (restricted) and
    on its lag-1 past plus ``sin(θ_j(t − τ))`` (unrestricted). The
    F-statistic of the model-comparison test is converted to a
    p-value; for each pair we keep the smallest p-value across the
    lag grid and the lag that achieved it.

    The single auto-regressive lag keeps the test cheap and
    conservative — adding more own-past lags would reduce power and
    is unnecessary for our use, which is a sanity check against the
    sparse coupling output rather than a full causal-discovery run.
    """
    cfg = config or CausalValidationConfig()
    theta = np.asarray(phases.theta, dtype=np.float64)
    T, N = theta.shape
    if T <= cfg.max_lag + 2:
        raise ValueError(f"trajectory length T={T} too short for max_lag={cfg.max_lag}")

    sin_theta = np.sin(theta)
    p_values = np.full((N, N), np.nan, dtype=np.float64)
    best_lag = np.zeros((N, N), dtype=np.int64)

    # Precompute the auto-regressive restricted design once per i
    for i in range(N):
        # Target: sin(θ_i(t)) for t ∈ [max_lag, T)
        y = sin_theta[cfg.max_lag :, i]
        y_lag1 = sin_theta[cfg.max_lag - 1 : T - 1, i]
        X_restricted = np.column_stack([np.ones_like(y), y_lag1])
        rss_r, k_r = _ols_rss(X_restricted, y)
        n = y.shape[0]
        for j in range(N):
            if j == i:
                continue
            best_p = 1.0
            best_tau = 0
            for tau in range(1, cfg.max_lag + 1):
                x_j = sin_theta[cfg.max_lag - tau : T - tau, j]
                X_full = np.column_stack([np.ones_like(y), y_lag1, x_j])
                rss_u, k_u = _ols_rss(X_full, y)
                dfn = k_u - k_r
                dfd = n - k_u
                if dfn <= 0 or dfd <= 0 or rss_u <= 0:
                    continue
                f_stat = ((rss_r - rss_u) / dfn) / (rss_u / dfd)
                if f_stat <= 0 or not np.isfinite(f_stat):
                    continue
                p = float(stats.f.sf(f_stat, dfn, dfd))
                if p < best_p:
                    best_p = p
                    best_tau = tau
            p_values[i, j] = best_p
            best_lag[i, j] = best_tau

    causal = np.zeros((N, N), dtype=bool)
    off_diag = ~np.eye(N, dtype=bool)
    causal[off_diag] = p_values[off_diag] < cfg.alpha

    return CausalValidationReport(
        causal_graph=causal,
        p_values=p_values,
        best_lag=best_lag,
        method="granger",
    )


# ---------------------------------------------------------------------------
# Optional PCMCI backend
# ---------------------------------------------------------------------------


def pcmci_causality(
    phases: PhaseMatrix,
    *,
    config: CausalValidationConfig | None = None,
) -> CausalValidationReport:
    """PCMCI causal discovery via :mod:`tigramite` (optional dep).

    Raises :class:`OptionalDependencyError` from
    :mod:`core.kuramoto.phase_extractor` when ``tigramite`` is not
    installed. The returned report uses the same contract as
    :func:`lag_granger_causality` so callers can switch backends
    without touching downstream code.
    """
    try:
        # fmt: off
        # ruff: noqa: I001
        from tigramite.data_processing import DataFrame  # type: ignore[import-not-found,unused-ignore]
        from tigramite.independence_tests.parcorr import ParCorr  # type: ignore[import-not-found,unused-ignore]
        from tigramite.pcmci import PCMCI  # type: ignore[import-not-found,unused-ignore]
        # fmt: on
    except ImportError as exc:  # pragma: no cover - exercised only without tigramite
        from .phase_extractor import OptionalDependencyError

        raise OptionalDependencyError(
            "PCMCI backend requires the optional 'tigramite' package (pip install tigramite)"
        ) from exc

    cfg = config or CausalValidationConfig(backend="pcmci")
    theta = np.asarray(phases.theta, dtype=np.float64)
    sin_theta = np.sin(theta)
    N = theta.shape[1]

    dataframe = DataFrame(data=sin_theta, var_names=list(phases.asset_ids))
    pcmci_obj = PCMCI(
        dataframe=dataframe,
        cond_ind_test=ParCorr(significance="analytic"),
        verbosity=0,
    )
    results = pcmci_obj.run_pcmci(
        tau_max=cfg.max_lag,
        pc_alpha=cfg.alpha,
        alpha_level=cfg.alpha,
    )

    # tigramite graph has shape (N, N, tau_max+1) with strings like ''
    # for absent links and '-->' / 'o->' for oriented ones. We turn it
    # into our boolean matrix.
    graph = results["graph"]
    pvals = results["p_matrix"]
    causal = np.zeros((N, N), dtype=bool)
    p_out = np.full((N, N), np.nan, dtype=np.float64)
    best_lag = np.zeros((N, N), dtype=np.int64)
    for i in range(N):
        for j in range(N):
            if i == j:
                continue
            # tigramite stores source → target at index (source, target, lag)
            lag_scores = [
                (lag, float(pvals[j, i, lag]))
                for lag in range(1, cfg.max_lag + 1)
                if graph[j, i, lag] != ""
            ]
            if not lag_scores:
                continue
            lag, p = min(lag_scores, key=lambda x: x[1])
            causal[i, j] = p < cfg.alpha
            p_out[i, j] = p
            best_lag[i, j] = lag

    return CausalValidationReport(
        causal_graph=causal,
        p_values=p_out,
        best_lag=best_lag,
        method="pcmci",
    )


# ---------------------------------------------------------------------------
# Jaccard comparison against identified coupling
# ---------------------------------------------------------------------------


def compare_to_coupling(
    report: CausalValidationReport, coupling: CouplingMatrix
) -> dict[str, float]:
    """Jaccard / precision / recall of causal edges vs coupling edges.

    The methodology requires Jaccard ≥ 0.4 for the causal backend to
    count as a validation of the coupling estimator. This helper
    returns all four relevant scalars so callers can emit a full
    quality report in one go.
    """
    c_edges = np.asarray(report.causal_graph, dtype=bool)
    k_edges = np.asarray(np.abs(coupling.K) > 0, dtype=bool)
    off = ~np.eye(c_edges.shape[0], dtype=bool)
    c_edges = c_edges & off
    k_edges = k_edges & off

    inter = int((c_edges & k_edges).sum())
    union = int((c_edges | k_edges).sum())
    jaccard = inter / union if union else 0.0
    precision = inter / int(k_edges.sum()) if k_edges.any() else 0.0
    recall = inter / int(c_edges.sum()) if c_edges.any() else 0.0
    return {
        "jaccard": float(jaccard),
        "precision": float(precision),
        "recall": float(recall),
        "n_causal_edges": float(c_edges.sum()),
        "n_coupling_edges": float(k_edges.sum()),
    }
