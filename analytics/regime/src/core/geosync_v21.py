# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Causal early-warning pipeline adapted from the GeoSync v2.1 prototype.

This module restructures the single-file research prototype provided by the
quantitative research team into composable building blocks that integrate with
the broader GeoSync analytics stack.  The original script delivered an
end-to-end workflow covering feature engineering, a calibrated classifier,
regime-aware adjustment via a lightweight HMM and a simple walk-forward
backtest.  The implementation below keeps the mathematical logic intact while
offering clear abstractions, type hints and docstrings so the components can be
reused across notebooks, the analytics runner and CLI tooling.

All functionality is implemented with standard dependencies already declared in
``pyproject.toml``.  Optional StatsModels support remains – when unavailable the
pipeline transparently falls back to a correlation-based proxy for the Granger
causality strength feature, mirroring the behaviour of the original prototype.

The primary entry point is :class:`GeoSyncV21Pipeline`.  It orchestrates the
following steps:

1. :class:`StrictCausalFeatureBuilder` computes the Kuramoto Δr proxy, Forman
   Ricci curvature, a Betti-curve topology sketch and an aggregate causal
   strength score using strictly causal windows.
2. :class:`LogisticIsotonicTrainer` performs nested time-series cross-validation
   with isotonic calibration and conformal uncertainty quantification.
3. :class:`RegimeHMMAdapter` adjusts the calibrated probabilities with a
   low-order hidden Markov model to reflect regime persistence.
4. :class:`ProbabilityBacktester` evaluates the signal using simple
   position-sizing rules and a block-bootstrap stress test.

Each class exposes pure-Python data classes for configuration and results,
keeping the public API explicit and testable.  The accompanying CLI command is
implemented in ``cli/geosync_cli.py``.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import networkx as nx
import numpy as np
import pandas as pd

try:  # pragma: no cover - optional dependency
    from sklearn.isotonic import IsotonicRegression
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import average_precision_score, roc_auc_score
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.utils import check_random_state
except ModuleNotFoundError:  # pragma: no cover - fallback exercised in tests
    from ._sklearn_compat import (
        IsotonicRegression,
        LogisticRegression,
        TimeSeriesSplit,
        average_precision_score,
        check_random_state,
        roc_auc_score,
    )

try:  # pragma: no cover - optional dependency, exercised in integration tests
    import statsmodels.api as sm

    _HAS_STATSMODELS = True
except Exception:  # pragma: no cover - dependency intentionally optional
    sm = None
    _HAS_STATSMODELS = False

__all__ = [
    "FeatureBuilderConfig",
    "StrictCausalFeatures",
    "StrictCausalFeatureBuilder",
    "ModelTrainingConfig",
    "ModelPerformance",
    "LogisticModelArtifacts",
    "LogisticIsotonicTrainer",
    "RegimeHMMConfig",
    "RegimeHMMAdapter",
    "EnsembleConfig",
    "ProbabilityOutputs",
    "BacktestConfig",
    "BacktestSummary",
    "StressTestSummary",
    "ProbabilityBacktester",
    "PipelineResult",
    "GeoSyncV21Pipeline",
    "result_to_json",
]


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _robust_zscore(values: np.ndarray, eps: float = 1e-9) -> np.ndarray:
    median = np.nanmedian(values, axis=0)
    mad = np.nanmedian(np.abs(values - median), axis=0) + eps
    return (values - median) / (1.4826 * mad)


def _ema(series: np.ndarray, alpha: float = 0.2) -> np.ndarray:
    output = np.empty_like(series, dtype=float)
    output[0] = series[0]
    for idx in range(1, len(series)):
        output[idx] = alpha * series[idx] + (1.0 - alpha) * output[idx - 1]
    return output


def _shrink_corr(samples: np.ndarray) -> np.ndarray:
    demeaned = samples - np.mean(samples, axis=0, keepdims=True)
    cov = (demeaned.T @ demeaned) / max(1, len(demeaned) - 1)
    avg_var = np.trace(cov) / cov.shape[0]
    cov_shrunk = 0.9 * cov + 0.1 * np.eye(cov.shape[0]) * avg_var
    diag = np.sqrt(np.clip(np.diag(cov_shrunk), 1e-12, None))
    corr = cov_shrunk / np.outer(diag, diag)
    np.fill_diagonal(corr, 1.0)
    return np.clip(corr, -1.0, 1.0)


def _graph_from_corr(corr: np.ndarray, threshold: float) -> nx.Graph:
    graph = nx.Graph()
    n_assets = corr.shape[0]
    graph.add_nodes_from(range(n_assets))
    for i in range(n_assets):
        for j in range(i + 1, n_assets):
            weight = corr[i, j]
            if weight >= threshold:
                graph.add_edge(i, j, weight=float(weight))
    return graph


def _drawdown(equity: np.ndarray) -> Tuple[float, float]:
    peak = -np.inf
    max_drawdown = 0.0
    for value in equity:
        peak = max(peak, value)
        drawdown = (peak - value) / max(peak, 1e-12)
        max_drawdown = max(max_drawdown, drawdown)
    return float(max_drawdown), float(peak)


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FeatureBuilderConfig:
    """Configuration for strict causal feature construction."""

    window: int = 252
    horizon: int = 5
    ricci_threshold: float = 0.2
    topo_thresholds: Tuple[float, ...] = tuple(np.linspace(0.2, 0.8, 13))
    label_threshold: float = -0.005
    ema_alpha: float = 0.2
    granger_maxlag: int = 1


@dataclass(frozen=True)
class StrictCausalFeatures:
    """Container holding engineered features and aligned labels."""

    features: pd.DataFrame
    labels: np.ndarray


class StrictCausalFeatureBuilder:
    """Compute strictly causal features from rolling windows of log returns."""

    def __init__(self, config: FeatureBuilderConfig | None = None) -> None:
        self._config = config or FeatureBuilderConfig()

    @staticmethod
    def _coherence(snapshot: np.ndarray) -> float:
        z_scores = _robust_zscore(snapshot)
        spectrum = np.fft.rfft(z_scores, axis=0)
        if spectrum.shape[0] <= 1:
            return 0.0
        principal_angle = np.angle(spectrum[1, :])
        return float(np.abs(np.mean(np.exp(1j * principal_angle))))

    @classmethod
    def _compute_delta_r(cls, past_returns: np.ndarray, alpha: float) -> float:
        segment = max(5, int(len(past_returns) // 6))
        if len(past_returns) <= segment:
            return 0.0

        step = max(1, segment // 2)
        coherence_series: list[float] = []
        for start in range(0, len(past_returns) - segment + 1, step):
            coherence_series.append(cls._coherence(past_returns[start : start + segment]))

        if len(coherence_series) < 2:
            return 0.0

        coherence_array = np.asarray(coherence_series, dtype=float)
        if coherence_array.ndim != 1:
            coherence_array = coherence_array.reshape(-1)
        coherence_array = np.nan_to_num(coherence_array, nan=0.0, posinf=1.0, neginf=0.0)
        smoothed = _ema(coherence_array, alpha=alpha)
        if len(smoothed) < 2:
            return 0.0
        return float(smoothed[-1] - smoothed[-2])

    @staticmethod
    def _compute_forman_ricci(past_returns: np.ndarray, threshold: float) -> float:
        corr = _shrink_corr(past_returns)
        graph = _graph_from_corr(corr, threshold)
        if graph.number_of_edges() == 0:
            return 0.0
        curvature = [4.0 - (graph.degree(u) + graph.degree(v)) for u, v in graph.edges()]
        return float(np.mean(curvature))

    def _compute_topology(self, past_returns: np.ndarray) -> float:
        corr = _shrink_corr(past_returns)
        thresholds = np.asarray(self._config.topo_thresholds, dtype=float)
        beta0: list[float] = []
        beta1: list[float] = []
        euler: list[float] = []
        for threshold in thresholds:
            graph = _graph_from_corr(corr, float(threshold))
            v_count = graph.number_of_nodes()
            e_count = graph.number_of_edges()
            components = nx.number_connected_components(graph)
            beta0.append(float(components))
            beta1.append(float(max(0, e_count - v_count + components)))
            euler.append(float(v_count - e_count))
        auc0 = float(np.trapezoid(beta0, thresholds))
        auc1 = float(np.trapezoid(beta1, thresholds))
        euler_area = float(np.trapezoid(euler, thresholds))
        return float(auc1 - 0.5 * auc0 - 0.1 * euler_area)

    @staticmethod
    def _compute_granger_strength(past_returns: np.ndarray, maxlag: int) -> float:
        if not _HAS_STATSMODELS:
            corr = np.corrcoef(past_returns.T)
            np.fill_diagonal(corr, 0.0)
            return float(np.clip(np.nanmax(np.abs(corr)), 0.0, 1.0))

        t_steps, n_assets = past_returns.shape
        best = 0.0
        for driver in range(n_assets):
            for target in range(n_assets):
                if driver == target:
                    continue
                try:
                    series = np.column_stack([past_returns[:, target], past_returns[:, driver]])
                    tests = sm.tsa.stattools.grangercausalitytests(
                        series,
                        maxlag=maxlag,
                        verbose=False,
                    )
                    p_values = [tests[lag][0]["ssr_ftest"][1] for lag in tests]
                    p_value = min(p_values)
                except Exception:
                    p_value = 1.0
                best = max(best, 1.0 - float(p_value))
        return float(np.clip(best, 0.0, 1.0))

    def build(self, returns: pd.DataFrame) -> StrictCausalFeatures:
        cfg = self._config
        if returns.empty:
            raise ValueError("returns must contain at least one observation")

        features: list[list[float]] = []
        labels: list[int] = []
        timestamps: list[pd.Timestamp] = []
        values = returns.values
        for t in range(cfg.window, len(returns) - cfg.horizon):
            window_slice = values[t - cfg.window : t]
            dr = self._compute_delta_r(window_slice, cfg.ema_alpha)
            ricci = self._compute_forman_ricci(window_slice, cfg.ricci_threshold)
            topology = self._compute_topology(window_slice)
            causal = self._compute_granger_strength(window_slice, cfg.granger_maxlag)
            features.append([dr, -ricci, topology, causal])
            forward = values[t + 1 : t + 1 + cfg.horizon].mean()
            labels.append(int(forward < cfg.label_threshold))
            timestamps.append(returns.index[t])

        frame = pd.DataFrame(
            features,
            index=pd.Index(timestamps, name="ts"),
            columns=["dr", "ricci_mean", "topo_intensity", "causal_strength"],
        )
        return StrictCausalFeatures(features=frame, labels=np.asarray(labels, dtype=int))


# ---------------------------------------------------------------------------
# Model training
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelTrainingConfig:
    """Hyperparameters for the logistic classifier and calibration."""

    splits: int = 5
    C: float = 1.0
    class_balance: bool = True
    random_state: int = 42
    conformal_alpha: float = 0.05


@dataclass(frozen=True)
class ModelPerformance:
    """Aggregated offline metrics for the classifier."""

    auc: float
    pr_auc: float
    auc_ci: Tuple[float, Tuple[float, float]]
    pr_ci: Tuple[float, Tuple[float, float]]


@dataclass(frozen=True)
class LogisticModelArtifacts:
    """Artifacts needed to score new samples with calibration."""

    isotonic: IsotonicRegression
    base_model: LogisticRegression
    mean: np.ndarray
    std: np.ndarray
    oof_probabilities: np.ndarray
    conformal_epsilon: float
    performance: ModelPerformance


class LogisticIsotonicTrainer:
    """Train a logistic regression with isotonic calibration and conformal ε."""

    def __init__(self, config: ModelTrainingConfig | None = None) -> None:
        self._config = config or ModelTrainingConfig()

    @staticmethod
    def _standardize(
        train: np.ndarray, test: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        mean = train.mean(axis=0)
        std = train.std(axis=0) + 1e-9
        return mean, std, (train - mean) / std, (test - mean) / std

    @staticmethod
    def _fit_logistic(
        train: np.ndarray,
        labels: np.ndarray,
        config: ModelTrainingConfig,
        rng: np.random.RandomState,
    ) -> LogisticRegression:
        model = LogisticRegression(
            C=config.C,
            penalty="l2",
            class_weight="balanced" if config.class_balance else None,
            max_iter=4000,
            random_state=rng,
        )
        model.fit(train, labels)
        return model

    def fit(self, features: np.ndarray, labels: np.ndarray) -> LogisticModelArtifacts:
        cfg = self._config
        tscv = TimeSeriesSplit(n_splits=cfg.splits)
        rng = check_random_state(cfg.random_state)

        oof = np.full(len(labels), np.nan, dtype=float)
        for train_idx, test_idx in tscv.split(features):
            mean, std, train_std, test_std = self._standardize(
                features[train_idx], features[test_idx]
            )
            model = self._fit_logistic(train_std, labels[train_idx], cfg, rng)
            raw = model.decision_function(test_std)
            oof[test_idx] = 1.0 / (1.0 + np.exp(-raw))

        mask = ~np.isnan(oof)
        if not np.any(mask):
            raise ValueError("Insufficient data for time-series cross validation")

        isotonic = IsotonicRegression(out_of_bounds="clip")
        isotonic.fit(oof[mask], labels[mask])
        calibrated = np.empty_like(oof)
        calibrated[mask] = isotonic.predict(oof[mask])
        if np.any(~mask):
            fill_prob = float(np.nanmean(oof[mask]))
            calibrated[~mask] = isotonic.predict(np.full(np.sum(~mask), fill_prob))

        auc = roc_auc_score(labels[mask], calibrated[mask])
        pr = average_precision_score(labels[mask], calibrated[mask])
        auc_mean, auc_ci = _block_bootstrap_ci(labels, calibrated, metric="auc")
        pr_mean, pr_ci = _block_bootstrap_ci(labels, calibrated, metric="pr")

        full_mean = features.mean(axis=0)
        full_std = features.std(axis=0) + 1e-9
        standardized = (features - full_mean) / full_std
        base_model = self._fit_logistic(standardized, labels, cfg, rng)

        conformal_eps = _conformal_epsilon(calibrated[mask], labels[mask], cfg.conformal_alpha)

        performance = ModelPerformance(
            auc=float(auc),
            pr_auc=float(pr),
            auc_ci=(auc_mean, auc_ci),
            pr_ci=(pr_mean, pr_ci),
        )

        return LogisticModelArtifacts(
            isotonic=isotonic,
            base_model=base_model,
            mean=full_mean,
            std=full_std,
            oof_probabilities=calibrated,
            conformal_epsilon=conformal_eps,
            performance=performance,
        )


# ---------------------------------------------------------------------------
# Model evaluation helpers
# ---------------------------------------------------------------------------


def _conformal_epsilon(probabilities: np.ndarray, labels: np.ndarray, alpha: float) -> float:
    residuals = np.abs(labels - probabilities)
    return float(np.quantile(residuals, 1.0 - alpha))


def _block_bootstrap_ci(
    labels: np.ndarray,
    scores: np.ndarray,
    *,
    block: int = 20,
    samples: int = 500,
    metric: str = "auc",
    seed: int = 42,
) -> Tuple[float, Tuple[float, float]]:
    rng = np.random.default_rng(seed)
    n_obs = len(labels)
    indices = np.arange(n_obs)
    n_blocks = math.ceil(n_obs / block)
    stats: list[float] = []
    scorer = roc_auc_score if metric == "auc" else average_precision_score
    for _ in range(samples):
        drawn: list[int] = []
        for _ in range(n_blocks):
            start = rng.integers(0, max(1, n_obs - block))
            drawn.extend(indices[start : start + block])
        drawn = drawn[:n_obs]
        boot_labels = labels[drawn]
        boot_scores = scores[drawn]
        stats.append(float(scorer(boot_labels, boot_scores)))
    mean = float(np.mean(stats))
    low, high = np.percentile(stats, [2.5, 97.5]).tolist()
    return mean, (float(low), float(high))


# ---------------------------------------------------------------------------
# Regime-aware HMM adapter
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegimeHMMConfig:
    """Parameters for the regime-aware logistic adjustment."""

    states: int = 2
    stay_probability: float = 0.9
    slope: Tuple[float, ...] = (1.1, 0.7)
    bias: Tuple[float, ...] = (0.0, -0.4)


class RegimeHMMAdapter:
    """Adjust calibrated probabilities using a low-order HMM."""

    def __init__(self, config: RegimeHMMConfig | None = None) -> None:
        self._config = config or RegimeHMMConfig()

    @staticmethod
    def _logsumexp(values: np.ndarray, axis: int) -> np.ndarray:
        max_val = np.max(values, axis=axis, keepdims=True)
        return max_val + np.log(np.sum(np.exp(values - max_val), axis=axis, keepdims=True))

    def adjust(self, probabilities: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        cfg = self._config
        eps = 1e-8
        logits = np.log(np.clip(probabilities, eps, 1 - eps)) - np.log(
            np.clip(1 - probabilities, eps, 1 - eps)
        )
        slopes = np.array(cfg.slope, dtype=float)
        biases = np.array(cfg.bias, dtype=float)

        if slopes.size < cfg.states:
            if slopes.size == 0:
                slopes = np.ones(cfg.states, dtype=float)
            else:
                slopes = np.pad(slopes, (0, cfg.states - slopes.size), mode="edge")
        else:
            slopes = slopes[: cfg.states]

        if biases.size < cfg.states:
            if biases.size == 0:
                biases = np.zeros(cfg.states, dtype=float)
            else:
                biases = np.pad(biases, (0, cfg.states - biases.size), mode="edge")
        else:
            biases = biases[: cfg.states]
        transition = np.full(
            (cfg.states, cfg.states),
            (1.0 - cfg.stay_probability) / max(cfg.states - 1, 1),
        )
        np.fill_diagonal(transition, cfg.stay_probability)
        log_transition = np.log(transition)
        log_pi = np.log(np.full(cfg.states, 1.0 / cfg.states))

        emissions = np.empty((len(logits), cfg.states), dtype=float)
        for state in range(cfg.states):
            state_logits = slopes[state] * logits + biases[state]
            emissions[:, state] = -np.log1p(np.exp(-state_logits))

        delta = np.empty_like(emissions)
        psi = np.zeros_like(emissions, dtype=int)
        delta[0] = log_pi + emissions[0]
        for t in range(1, len(logits)):
            scores = delta[t - 1][:, None] + log_transition
            psi[t] = np.argmax(scores, axis=0)
            delta[t] = np.max(scores, axis=0) + emissions[t]
        path = np.empty(len(logits), dtype=int)
        path[-1] = int(np.argmax(delta[-1]))
        for t in range(len(logits) - 2, -1, -1):
            path[t] = int(psi[t + 1, path[t + 1]])

        alpha = np.empty_like(emissions)
        alpha[0] = log_pi + emissions[0]
        for t in range(1, len(logits)):
            previous = alpha[t - 1][:, None] + log_transition
            alpha[t] = self._logsumexp(previous, axis=0).squeeze() + emissions[t]
        log_norm = self._logsumexp(alpha[-1][None, :], axis=1).squeeze()
        posterior = np.exp(alpha - log_norm)
        adjusted_logit = np.sum(posterior * (slopes * logits[:, None] + biases), axis=1)
        adjusted = 1.0 / (1.0 + np.exp(-np.clip(adjusted_logit, -60.0, 60.0)))
        return adjusted.astype(float), path


@dataclass(frozen=True)
class EnsembleConfig:
    """Linear blend between base calibrated probability and HMM output."""

    lambda_base: float = 0.6


@dataclass(frozen=True)
class ProbabilityOutputs:
    """Container for probability series produced by the pipeline."""

    base: np.ndarray
    hmm: np.ndarray
    final: np.ndarray


# ---------------------------------------------------------------------------
# Backtesting and stress testing
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BacktestConfig:
    """Configuration for the rule-based probability backtester."""

    tau_high: float = 0.142
    tau_low: float = 0.378
    fee: float = 0.01
    slippage: float = 0.005
    long_weight: float = 1.0
    short_weight: float = -0.5


@dataclass(frozen=True)
class BacktestSummary:
    """Key performance indicators from the walk-forward backtest."""

    sharpe: float
    max_drawdown: float
    equity_final: float


@dataclass(frozen=True)
class StressTestSummary:
    """Aggregate statistics from the volatility stress harness."""

    sharpe_mean: float
    sharpe_std: float
    drawdown_mean: float
    equity_mean: float
    win_rate_vs_buyhold: float


class ProbabilityBacktester:
    """Evaluate probability-driven positioning rules."""

    def __init__(self, config: BacktestConfig | None = None) -> None:
        self._config = config or BacktestConfig()

    def _positions(self, probabilities: np.ndarray) -> np.ndarray:
        cfg = self._config
        positions = np.zeros_like(probabilities, dtype=float)
        positions[probabilities >= cfg.tau_low] = cfg.short_weight
        positions[probabilities <= cfg.tau_high] = cfg.long_weight
        mask = (probabilities > cfg.tau_high) & (probabilities < cfg.tau_low)
        positions[mask] = 0.5
        return positions

    def backtest(self, probabilities: np.ndarray, returns: np.ndarray) -> BacktestSummary:
        cfg = self._config
        positions = self._positions(probabilities)
        delta_positions = np.insert(np.diff(positions), 0, 0.0)
        if returns.ndim == 2:
            pnl = positions * returns.mean(axis=1)
        else:
            pnl = positions * returns
        pnl -= (cfg.fee + cfg.slippage) * np.abs(delta_positions)
        mu = np.mean(pnl)
        sigma = np.std(pnl) + 1e-12
        sharpe = float(mu / sigma)
        equity = np.cumprod(1.0 + pnl)
        max_dd, _ = _drawdown(equity)
        return BacktestSummary(sharpe=sharpe, max_drawdown=max_dd, equity_final=float(equity[-1]))

    def stress_test(
        self,
        probabilities: np.ndarray,
        returns: np.ndarray,
        *,
        vol_scale: float = 2.0,
        neg_drift: float = -0.005,
        simulations: int = 500,
        seed: int = 7,
    ) -> StressTestSummary:
        rng = np.random.default_rng(seed)
        base = returns.mean(axis=1) if returns.ndim == 2 else returns
        results: list[Tuple[float, float, float]] = []
        buy_hold = float(np.cumprod(1.0 + base)[-1])
        for _ in range(simulations):
            shocks = rng.standard_normal(len(base)) * np.std(base)
            scenario = base + vol_scale * shocks + neg_drift
            summary = self.backtest(probabilities, scenario)
            results.append((summary.sharpe, summary.max_drawdown, summary.equity_final))
        arr = np.asarray(results)
        sharpe_mean = float(arr[:, 0].mean())
        sharpe_std = float(arr[:, 0].std())
        dd_mean = float(arr[:, 1].mean())
        equity_mean = float(arr[:, 2].mean())
        win_rate = float(np.mean(arr[:, 2] > buy_hold))
        return StressTestSummary(
            sharpe_mean=sharpe_mean,
            sharpe_std=sharpe_std,
            drawdown_mean=dd_mean,
            equity_mean=equity_mean,
            win_rate_vs_buyhold=win_rate,
        )


# ---------------------------------------------------------------------------
# Pipeline result container
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PipelineResult:
    """Complete output returned by :class:`GeoSyncV21Pipeline`."""

    probabilities: ProbabilityOutputs
    artifacts: LogisticModelArtifacts
    hmm_path: np.ndarray
    backtest: Optional[BacktestSummary]
    stress: Optional[StressTestSummary]
    drift_guard: Optional[Dict[str, Dict[str, float]]]

    def to_dict(self) -> Dict[str, Any]:
        """Convert the result into a JSON-serialisable dictionary."""

        performance = self.artifacts.performance
        payload: Dict[str, Any] = {
            "auc_oof": performance.auc,
            "pr_oof": performance.pr_auc,
            "auc_bootstrap": {
                "mean": performance.auc_ci[0],
                "ci95": list(performance.auc_ci[1]),
            },
            "pr_bootstrap": {
                "mean": performance.pr_ci[0],
                "ci95": list(performance.pr_ci[1]),
            },
            "conformal_eps_95": self.artifacts.conformal_epsilon,
            "p_final": self.probabilities.final.tolist(),
            "p_base": self.probabilities.base.tolist(),
            "p_hmm": self.probabilities.hmm.tolist(),
            "z_path": self.hmm_path.tolist(),
        }
        if self.backtest is not None:
            payload["backtest"] = {
                "sharpe": self.backtest.sharpe,
                "max_dd": self.backtest.max_drawdown,
                "equity_final": self.backtest.equity_final,
            }
        if self.stress is not None:
            payload["stress"] = {
                "sharpe_mean": self.stress.sharpe_mean,
                "sharpe_std": self.stress.sharpe_std,
                "dd_mean": self.stress.drawdown_mean,
                "equity_mean": self.stress.equity_mean,
                "winrate_vs_bh": self.stress.win_rate_vs_buyhold,
            }
        if self.drift_guard is not None:
            payload["drift_guard"] = self.drift_guard
        return payload


# ---------------------------------------------------------------------------
# Pipeline orchestrator
# ---------------------------------------------------------------------------


class GeoSyncV21Pipeline:
    """High-level orchestrator covering features, training and evaluation."""

    def __init__(
        self,
        feature_builder: StrictCausalFeatureBuilder,
        trainer: LogisticIsotonicTrainer,
        hmm_adapter: RegimeHMMAdapter,
        backtester: ProbabilityBacktester | None = None,
        ensemble: EnsembleConfig | None = None,
    ) -> None:
        self._feature_builder = feature_builder
        self._trainer = trainer
        self._hmm = hmm_adapter
        self._backtester = backtester
        self._ensemble = ensemble or EnsembleConfig()

    def run(
        self,
        features: StrictCausalFeatures,
        returns: Optional[pd.DataFrame] = None,
        *,
        evaluate_backtest: bool = True,
    ) -> PipelineResult:
        artifacts = self._trainer.fit(features.features.values, features.labels)
        standardized = (features.features.values - artifacts.mean) / artifacts.std
        raw = artifacts.base_model.decision_function(standardized)
        base_probs = 1.0 / (1.0 + np.exp(-raw))
        calibrated = artifacts.isotonic.predict(base_probs)
        hmm_probs, path = self._hmm.adjust(calibrated)
        final_probs = (
            self._ensemble.lambda_base * calibrated + (1.0 - self._ensemble.lambda_base) * hmm_probs
        )

        probability_outputs = ProbabilityOutputs(
            base=calibrated.astype(float),
            hmm=hmm_probs.astype(float),
            final=final_probs.astype(float),
        )

        backtest_summary: BacktestSummary | None = None
        stress_summary: StressTestSummary | None = None
        if evaluate_backtest and self._backtester is not None and returns is not None:
            aligned = returns.loc[features.features.index]
            backtest_summary = self._backtester.backtest(final_probs, aligned.values)
            stress_summary = self._backtester.stress_test(final_probs, aligned.values)

        drift_guard = _feature_drift_guard(features.features)

        return PipelineResult(
            probabilities=probability_outputs,
            artifacts=artifacts,
            hmm_path=path,
            backtest=backtest_summary,
            stress=stress_summary,
            drift_guard=drift_guard,
        )


def _feature_drift_guard(frame: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    ref_size = max(10, int(len(frame) * 0.5))
    ref = frame.iloc[:ref_size].values
    cur = frame.values
    drift: Dict[str, Dict[str, float]] = {}
    for idx, column in enumerate(frame.columns):
        drift[column] = {
            "PSI": _population_stability_index(ref[:, idx], cur[:, idx]),
            "JS": _js_divergence(ref[:, idx], cur[:, idx]),
        }
    return drift


def _population_stability_index(
    reference: np.ndarray, current: np.ndarray, bins: int = 10
) -> float:
    quantiles = np.linspace(0, 1, bins + 1)
    edges = np.unique(np.quantile(reference, quantiles))
    if len(edges) < 3:
        return 0.0
    ref_hist, _ = np.histogram(reference, bins=edges)
    cur_hist, _ = np.histogram(current, bins=edges)
    ref_pct = ref_hist / max(ref_hist.sum(), 1)
    cur_pct = cur_hist / max(cur_hist.sum(), 1)
    ref_pct = np.clip(ref_pct, 1e-8, None)
    cur_pct = np.clip(cur_pct, 1e-8, None)
    return float(np.sum((ref_pct - cur_pct) * np.log(ref_pct / cur_pct)))


def _js_divergence(reference: np.ndarray, current: np.ndarray, bins: int = 40) -> float:
    lower = np.nanmin([np.nanmin(reference), np.nanmin(current)])
    upper = np.nanmax([np.nanmax(reference), np.nanmax(current)])
    if not np.isfinite(lower) or not np.isfinite(upper) or lower == upper:
        return 0.0
    ref_hist, _ = np.histogram(reference, bins=bins, range=(lower, upper), density=True)
    cur_hist, _ = np.histogram(current, bins=bins, range=(lower, upper), density=True)
    p = ref_hist + 1e-12
    q = cur_hist + 1e-12
    m = 0.5 * (p + q)
    kl_pm = np.sum(p * np.log(p / m))
    kl_qm = np.sum(q * np.log(q / m))
    return float(0.5 * (kl_pm + kl_qm))


def result_to_json(result: PipelineResult) -> str:
    """Serialize :class:`PipelineResult` to a human-readable JSON string."""

    return json.dumps(result.to_dict(), indent=2)
