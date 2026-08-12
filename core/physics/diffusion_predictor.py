# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T7 — Heat-kernel RANK-PROPAGATION volatility front predictor.

Provenance tier: EXTRAPOLATED. This module is a heuristic ranking
relaxation, not a validated physical-diffusion model. The name
"diffusion" here is historical/topological (heat kernel on a graph),
NOT physical (Fickian) diffusion. See the NOT-FICKIAN note below.

Per-step operator (what the code actually computes):
    ρ(t) = R( exp(-D · L(κ) · t) · ρ₀ )

where:
    L(κ)  = graph Laplacian with Ricci-modulated edge weights
    D_ij  = D₀ · exp(κ_ij)   (Ricci curvature scaling)
    ρ₀    = initial score density (recent realised vol per asset,
            L1-normalised to the probability simplex)
    R(·)  = clamp-to-≥0 then L1-renormalise to sum 1
            (projection back onto the probability simplex)

`exp(-L·t)·ρ₀` alone is the graph heat kernel; the surrounding `R(·)`
projects the result back onto the simplex. The output is therefore a
normalised RANKING SCORE that relaxes toward the graph's stationary
distribution, not a free, unbounded heat distribution.

NOT FICKIAN DIFFUSION (the load-bearing correction):
    This operator is a relaxation toward equilibrium on a FINITE graph,
    NOT physical (Fickian) diffusion on an unbounded medium. Free Fickian
    diffusion has a mean-square displacement that grows ⟨x²⟩ = 2Dt without
    bound (scaling exponent 1). Here, two facts break that:

      1. Finite-graph boundary (dominant): the heat kernel exp(-Lt) on a
         finite line/lattice cannot spread past the end nodes. ρ relaxes to
         the graph's stationary (uniform, for a connected unweighted graph)
         distribution, so the MSD SATURATES at the stationary-distribution
         variance — the long-horizon scaling exponent collapses toward 0,
         NOT 1. On an infinite line exp(-Lt) WOULD give ⟨x²⟩=2Dt; on this
         finite graph it does not.

      2. Simplex projection R (a guard, mostly inactive): for a valid graph
         Laplacian and a non-negative ρ₀ on the simplex, exp(-Lt) already
         conserves mass (Σρ=1) and stays non-negative, so R(·) is a no-op
         to machine precision. R only changes the result when the kernel
         emits negative mass — i.e. round-off or a non-Laplacian L — at
         which point it clamps and L1-renormalises so the output stays a
         valid ranking on the simplex. It is a fail-safe that pins the
         object to a RANKING, not the cause of the non-Fickian behaviour.

    Net: this is a graph relaxation / rank propagation whose MSD saturates,
    so it is emphatically NOT mass-conserving free diffusion. Pinned in-code
    by test_msd_exponent_is_non_fickian in the T7 test module, which
    measures the saturating MSD exponent on a known line graph.

Volatility front = assets where the propagated score ρ_i(t+1) > θ.

Backtest metric: ROC-AUC for front ranking vs realised vol spikes at
horizon t+1 to t+3. The relative ordering of the scores is the only
quantity consumed downstream; the simplex normalisation is a monotone-
preserving convenience, not a conservation law.

Topological motivation (heuristic, not a validated financial law):
    On the heat kernel, score leaks faster across positively curved
    edges (well-connected neighbourhoods) and slower across negatively
    curved edges (bottlenecks). The graph-curvature intuition is from
    network science (Sandhu 2016); its predictive value for volatility
    fronts is an EXTRAPOLATED hypothesis tested only by backtest here.

References:
    Kikuchi "Graph diffusion for network analysis" (2025)
    Chung "Spectral Graph Theory" (1997)
    Sandhu et al. "Graph curvature for cancer networks" Sci. Rep. (2016)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.linalg import expm

_LOGGER = logging.getLogger("geosync.physics.diffusion")


@dataclass(frozen=True, slots=True)
class VolatilityFrontPrediction:
    """Prediction of the volatility front (simplex ranking scores).

    `density_*` fields are L1-normalised RANKING SCORES on the probability
    simplex (sum to 1 by the per-step renormalisation R), NOT a conserved
    physical mass distribution. See module docstring (NOT FICKIAN).
    """

    predicted_front: list[int]  # asset indices ranked above threshold θ
    density_t1: NDArray[np.float64]  # propagated score at t+1 (sum=1)
    density_t3: NDArray[np.float64]  # propagated score at t+3 (sum=1)
    initial_density: NDArray[np.float64]
    threshold: float


@dataclass(frozen=True, slots=True)
class BacktestResult:
    """Backtest evaluation of front prediction."""

    n_windows: int
    roc_auc_t1: float
    roc_auc_t3: float
    precision_t1: float
    recall_t1: float
    mean_lead_time: float  # average steps prediction leads actual spike


class DiffusionVolatilityPredictor:
    """Predict the volatility front via heat-kernel RANK PROPAGATION.

    Despite the historical class name, this is a ranking relaxation on the
    probability simplex, not physical (Fickian) diffusion: the per-step
    operator is R ∘ exp(-Lt) (heat kernel followed by clamp + L1 renorm),
    whose mean-square displacement SATURATES rather than growing ∝ t. The
    public class/symbol names are retained to avoid churning the
    `core.physics.__init__` exports and consumers; the honest framing lives
    in these docstrings. The MSD saturates on any finite graph (boundary
    relaxation), not because of the renorm — see module docstring for the
    exact mechanism. Provenance tier: EXTRAPOLATED.

    Parameters
    ----------
    D_0 : float
        Base diffusion coefficient (default 1.0).
    threshold_quantile : float
        Quantile for defining "high volatility" (default 0.75).
    horizons : tuple[float, ...]
        Prediction horizons in time units (default (1.0, 3.0)).
    """

    def __init__(
        self,
        D_0: float = 1.0,
        threshold_quantile: float = 0.75,
        horizons: tuple[float, ...] = (1.0, 3.0),
    ) -> None:
        if D_0 <= 0:
            raise ValueError(f"D_0 must be > 0, got {D_0}")
        if not 0 < threshold_quantile < 1:
            raise ValueError(f"threshold_quantile in (0,1), got {threshold_quantile}")
        self._D_0 = D_0
        self._thresh_q = threshold_quantile
        self._horizons = horizons

    def _build_laplacian(
        self,
        adjacency: NDArray[np.float64],
        curvature: NDArray[np.float64] | None = None,
    ) -> NDArray[np.float64]:
        """Build curvature-weighted Laplacian."""
        A = np.asarray(adjacency, dtype=np.float64)
        if curvature is not None:
            kappa = np.asarray(curvature, dtype=np.float64)
            W = A * self._D_0 * np.exp(kappa)
        else:
            W = A * self._D_0
        W = 0.5 * (W + W.T)
        np.fill_diagonal(W, 0.0)
        D = np.diag(W.sum(axis=1))
        return D - W

    def _propagate(
        self,
        rho_0: NDArray[np.float64],
        L: NDArray[np.float64],
        t: float,
    ) -> NDArray[np.float64]:
        """ρ(t) = R( exp(-L·t) · ρ₀ ): heat kernel + simplex projection R.

        The clamp + L1 renormalisation R(·) below is a fail-safe that keeps
        the output a valid ranking on the probability simplex. For a valid
        graph Laplacian and a non-negative ρ₀ on the simplex it is a no-op
        to machine precision (exp(-Lt) already conserves mass and stays
        ≥ 0); it only bites when the kernel emits negative mass (round-off
        or a non-Laplacian L). The non-Fickian, MSD-saturating behaviour
        comes from the finite-graph boundary, not from this renorm — see the
        module docstring. Do not read this as mass-conserving free diffusion.
        """
        if t <= 0:
            return rho_0.copy()
        propagator = expm(-L * t)
        rho: NDArray[np.float64] = propagator @ rho_0
        # bounds: ρ(t) is a probability density (≥ 0); the heat-kernel
        # expm(-L·t) is non-negative for a graph Laplacian, so any
        # negativity here is expm round-off. Surface a non-trivial
        # excursion (would indicate a non-Laplacian L). Behaviour
        # unchanged by the log.
        _neg = float(-rho[rho < 0.0].sum()) if np.any(rho < 0.0) else 0.0
        if _neg > 1e-9:
            _LOGGER.warning(
                "diffusion _propagate: clamped %.3e negative density mass "
                "to 0 — heat kernel should be non-negative; check L is a "
                "valid graph Laplacian.",
                _neg,
            )
        rho = np.maximum(rho, 0.0)
        total = rho.sum()
        if total > 0:
            rho /= total
        return rho

    def predict(
        self,
        realized_vol: NDArray[np.float64],
        adjacency: NDArray[np.float64],
        curvature: NDArray[np.float64] | None = None,
    ) -> VolatilityFrontPrediction:
        """Predict volatility front from current state.

        Parameters
        ----------
        realized_vol : (N,) current realised volatility per asset.
        adjacency : (N, N) correlation-based adjacency.
        curvature : (N, N) Ricci curvature matrix (optional).

        Returns
        -------
        VolatilityFrontPrediction.
        """
        vol = np.asarray(realized_vol, dtype=np.float64)
        n = vol.size

        # Normalise vol to probability density.
        # bounds: realised volatility is ≥ 0 by construction. Unlike the
        # round-off case above, a negative input here is a genuine data
        # fault (e.g. sign error upstream) — surface it, then clamp.
        if np.any(vol < 0.0):
            _LOGGER.warning(
                "diffusion predict: %d negative realised-volatility "
                "input(s) (min=%.3e) clamped to 0 — realised vol must be "
                "non-negative; check the upstream estimator.",
                int(np.count_nonzero(vol < 0.0)),
                float(vol.min()),
            )
        rho_0 = np.maximum(vol, 0.0)
        total = rho_0.sum()
        if total > 0:
            rho_0 = rho_0 / total
        else:
            rho_0 = np.ones(n) / n

        L = self._build_laplacian(adjacency, curvature)

        rho_t1 = self._propagate(rho_0, L, self._horizons[0])
        rho_t3 = self._propagate(
            rho_0, L, self._horizons[-1] if len(self._horizons) > 1 else self._horizons[0]
        )

        # Threshold for front detection
        threshold = float(np.quantile(rho_t1, self._thresh_q))
        front = np.where(rho_t1 > threshold)[0].tolist()

        return VolatilityFrontPrediction(
            predicted_front=front,
            density_t1=rho_t1,
            density_t3=rho_t3,
            initial_density=rho_0,
            threshold=threshold,
        )

    def backtest(
        self,
        prices: NDArray[np.float64],
        adjacency_series: list[NDArray[np.float64]] | None = None,
        curvature_series: list[NDArray[np.float64]] | None = None,
        vol_window: int = 10,
        correlation_window: int = 30,
        spike_threshold_quantile: float = 0.80,
    ) -> BacktestResult:
        """Backtest volatility front prediction on historical data.

        Parameters
        ----------
        prices : (T, N) price history.
        adjacency_series : optional pre-computed adjacency per window.
        curvature_series : optional pre-computed curvature per window.
        vol_window : int, window for realised vol computation.
        correlation_window : int, window for adjacency construction.
        spike_threshold_quantile : float, quantile for "actual spike".

        Returns
        -------
        BacktestResult with ROC-AUC metrics.
        """
        prices = np.asarray(prices, dtype=np.float64)
        T, N = prices.shape

        returns = np.abs(np.diff(prices, axis=0) / np.maximum(np.abs(prices[:-1]), 1e-12))

        start = max(vol_window, correlation_window)
        n_windows = T - start - 3  # need 3 steps ahead

        if n_windows < 5:
            return BacktestResult(
                n_windows=0,
                roc_auc_t1=0.5,
                roc_auc_t3=0.5,
                precision_t1=0.0,
                recall_t1=0.0,
                mean_lead_time=0.0,
            )

        predictions_t1 = []
        actuals_t1 = []
        predictions_t3 = []
        actuals_t3 = []

        for t in range(n_windows):
            idx = start + t

            # Realised vol
            vol = np.std(returns[idx - vol_window : idx], axis=0)

            # Build adjacency from correlation
            if adjacency_series is not None and t < len(adjacency_series):
                adj = adjacency_series[t]
            else:
                ret_window = returns[idx - correlation_window : idx]
                with np.errstate(invalid="ignore"):
                    corr = np.corrcoef(ret_window, rowvar=False)
                corr = np.nan_to_num(corr, nan=0.0)
                adj = np.abs(corr)
                adj[adj < 0.3] = 0.0
                np.fill_diagonal(adj, 0.0)

            curv = (
                curvature_series[t]
                if curvature_series is not None and t < len(curvature_series)
                else None
            )

            # Predict
            pred = self.predict(vol, adj, curv)

            # Actual future vol
            if idx + 1 < returns.shape[0]:
                actual_vol_t1 = returns[idx]
                spike_thresh = np.quantile(actual_vol_t1, spike_threshold_quantile)
                actual_spike_t1 = (actual_vol_t1 > spike_thresh).astype(float)
                pred_score_t1 = pred.density_t1
                predictions_t1.append(pred_score_t1)
                actuals_t1.append(actual_spike_t1)

            if idx + 3 < returns.shape[0]:
                actual_vol_t3 = np.max(returns[idx : idx + 3], axis=0)
                spike_thresh_3 = np.quantile(actual_vol_t3, spike_threshold_quantile)
                actual_spike_t3 = (actual_vol_t3 > spike_thresh_3).astype(float)
                pred_score_t3 = pred.density_t3
                predictions_t3.append(pred_score_t3)
                actuals_t3.append(actual_spike_t3)

        # Compute ROC-AUC
        auc_t1 = self._compute_auc(predictions_t1, actuals_t1)
        auc_t3 = self._compute_auc(predictions_t3, actuals_t3)

        # Precision/Recall for t+1
        prec_t1, rec_t1 = self._precision_recall(predictions_t1, actuals_t1)

        return BacktestResult(
            n_windows=n_windows,
            roc_auc_t1=auc_t1,
            roc_auc_t3=auc_t3,
            precision_t1=prec_t1,
            recall_t1=rec_t1,
            # FIXED CONSTRUCTION CONSTANT — NOT a measured/empirical lead
            # time. The predictor emits a 1-step-ahead score by design, so
            # this field is hardcoded to that horizon (1 step) and carries
            # no information about how far ahead predictions actually lead
            # observed spikes. Any "lead time" interpretation as an
            # empirical result would be unfounded.
            mean_lead_time=1.0,
        )

    @staticmethod
    def _compute_auc(
        predictions: list[NDArray[np.float64]],
        actuals: list[NDArray[np.float64]],
    ) -> float:
        """Simple ROC-AUC via Mann-Whitney U statistic."""
        if not predictions or not actuals:
            return 0.5

        pred = np.concatenate(predictions)
        actual = np.concatenate(actuals)

        pos = pred[actual > 0.5]
        neg = pred[actual <= 0.5]

        if pos.size == 0 or neg.size == 0:
            return 0.5

        # Mann-Whitney U
        n_pos = pos.size
        n_neg = neg.size
        u = 0.0
        for p in pos:
            u += np.sum(p > neg) + 0.5 * np.sum(p == neg)

        return float(u / (n_pos * n_neg))

    @staticmethod
    def _precision_recall(
        predictions: list[NDArray[np.float64]],
        actuals: list[NDArray[np.float64]],
    ) -> tuple[float, float]:
        """Precision and recall at median threshold."""
        if not predictions or not actuals:
            return 0.0, 0.0

        pred = np.concatenate(predictions)
        actual = np.concatenate(actuals)

        thresh = np.median(pred)
        pred_binary = (pred > thresh).astype(float)

        tp = np.sum(pred_binary * actual)
        fp = np.sum(pred_binary * (1 - actual))
        fn = np.sum((1 - pred_binary) * actual)

        precision = tp / max(tp + fp, 1e-12)
        recall = tp / max(tp + fn, 1e-12)
        return float(precision), float(recall)


__all__ = [
    "DiffusionVolatilityPredictor",
    "VolatilityFrontPrediction",
    "BacktestResult",
]
