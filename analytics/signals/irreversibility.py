"""Irreversibility-Gated Signal (IGS).

This module implements batch and streaming utilities for computing the
Irreversibility-Gated Signal features that were specified for TradePulse.
The implementation focuses on numerical transparency and correctness –
rank-based discretisation is reproduced exactly for both batch and streaming
workflows so the outputs remain consistent across operating modes.

Exposed API
-----------
- :class:`IGSConfig`
- :class:`IGSMetrics`
- :func:`compute_igs_features`
- :func:`igs_directional_signal`
- :class:`StreamingIGS`
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

import math
import numpy as np
import pandas as pd

__all__ = [
    "IGSConfig",
    "IGSMetrics",
    "compute_igs_features",
    "igs_directional_signal",
    "StreamingIGS",
]


# ---------------------------------------------------------------------------
# Configuration and metric containers
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class IGSConfig:
    """Configuration controlling IGS computations."""

    window: int = 600
    n_states: int = 7
    min_counts: int = 50
    eps: float = 1e-12
    normalize_flux: bool = True
    detrend: bool = False
    perm_emb_dim: int = 5
    perm_tau: int = 1
    pi_method: str = "empirical"
    regime_weights: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    rolling_normalize: bool = False

    def __post_init__(self) -> None:
        if self.window < 3:
            raise ValueError("window must be at least 3 observations")
        if self.n_states < 3:
            raise ValueError("n_states must be at least 3")
        if self.perm_emb_dim < 3:
            raise ValueError("perm_emb_dim must be at least 3")
        if self.perm_tau < 1:
            raise ValueError("perm_tau must be positive")
        if len(self.regime_weights) != 3:
            raise ValueError("regime_weights must contain three entries")
        if self.pi_method not in {"empirical", "eigen"}:
            raise ValueError("pi_method must be 'empirical' or 'eigen'")
        if self.pi_method != "empirical":
            raise NotImplementedError("only empirical stationary distribution is supported")


@dataclass(slots=True)
class IGSMetrics:
    """Structured output produced by the streaming engine."""

    timestamp: pd.Timestamp
    epr: float
    flux_index: float
    tra: float
    pe: float
    regime_score: float
    regime: str


# ---------------------------------------------------------------------------
# Low level helpers
# ---------------------------------------------------------------------------
def _log_returns(price: pd.Series) -> pd.Series:
    returns = np.log(price).diff()
    returns.name = "log_return"
    return returns


def _quantize_states(window_returns: np.ndarray, n_states: int) -> np.ndarray:
    series = pd.Series(window_returns, copy=False)
    ranks = series.rank(method="average", pct=True).to_numpy()
    states = np.floor(ranks * n_states).astype(int)
    return np.clip(states, 0, n_states - 1)


def _transition_counts(states: np.ndarray, n_states: int) -> np.ndarray:
    counts = np.zeros((n_states, n_states), dtype=float)
    if len(states) <= 1:
        return counts
    for current_state, next_state in zip(states[:-1], states[1:]):
        counts[current_state, next_state] += 1.0
    return counts


def _transition_matrix(counts: np.ndarray, eps: float) -> np.ndarray:
    n_states = counts.shape[0]
    row_totals = counts.sum(axis=1, keepdims=True)
    return (counts + eps) / (row_totals + n_states * eps)


def _stationary_distribution(states: np.ndarray, n_states: int, eps: float) -> np.ndarray:
    occupancy = np.bincount(states, minlength=n_states).astype(float)
    total = occupancy.sum()
    if total <= 0.0:
        return np.full(n_states, 1.0 / n_states)
    return occupancy / (total + eps)


def _entropy_production(P: np.ndarray, pi: np.ndarray, eps: float) -> Tuple[float, np.ndarray]:
    pij = np.maximum(pi[:, None] * P, eps)
    pji = np.maximum(pi[None, :] * P.T, eps)
    entropy_matrix = pij * (np.log(pij) - np.log(pji))
    epr = float(np.sum(entropy_matrix))
    flux = pij - pji
    return epr, flux


def _flux_index(flux: np.ndarray, normalize: bool) -> float:
    n_states = flux.shape[0]
    if n_states <= 1:
        return 0.0
    indices = np.arange(n_states, dtype=float)
    distance = indices[None, :] - indices[:, None]
    upper = np.triu_indices(n_states, k=1)
    numerator = float(np.sum(flux[upper] * distance[upper]))
    denominator = float(np.sum(np.abs(flux[upper] * distance[upper])) + 1e-12)
    if not normalize:
        return numerator
    return float(np.clip(numerator / denominator, -1.0, 1.0))


def _time_reversal_asymmetry(window_returns: np.ndarray) -> float:
    if len(window_returns) < 3:
        return float("nan")
    forward = np.mean(window_returns[1:] ** 2 * window_returns[:-1])
    backward = np.mean(window_returns[:-1] ** 2 * window_returns[1:])
    return float(forward - backward)


def _permutation_entropy(window_returns: np.ndarray, dim: int, tau: int, eps: float) -> float:
    n_vectors = len(window_returns) - (dim - 1) * tau
    if dim < 3 or n_vectors <= 1:
        return float("nan")
    counts: dict[Tuple[int, ...], int] = {}
    for start in range(n_vectors):
        segment = window_returns[start : start + dim * tau : tau]
        order = tuple(np.argsort(segment, kind="mergesort"))
        counts[order] = counts.get(order, 0) + 1
    freq = np.array(list(counts.values()), dtype=float)
    probabilities = freq / freq.sum()
    entropy = -np.sum(probabilities * np.log(probabilities + eps))
    entropy_max = math.log(math.factorial(dim))
    return float(entropy / entropy_max)


def _regime_components(epr: float, flux_index: float, pe: float) -> Tuple[float, float, float]:
    irreversible_component = 1.0 - math.exp(-max(epr, 0.0))
    directional_component = min(abs(flux_index), 1.0)
    if math.isnan(pe):
        entropy_component = float("nan")
    else:
        entropy_component = np.clip(1.0 - pe, 0.0, 1.0)
    return irreversible_component, directional_component, entropy_component


def _regime_score(components: Sequence[float], weights: Sequence[float]) -> float:
    components_arr = np.asarray(components, dtype=float)
    weights_arr = np.asarray(weights, dtype=float)
    valid = np.isfinite(components_arr)
    if not np.any(valid):
        return float("nan")
    components_valid = components_arr[valid]
    weights_valid = weights_arr[valid]
    if np.all(weights_valid == 0):
        weights_valid = np.ones_like(weights_valid)
    score = float(np.average(components_valid, weights=weights_valid))
    return float(np.clip(score, 0.0, 1.0))


def _classify_regime(epr: float, flux_index: float, pe: float) -> str:
    if epr < 1e-3 and (not math.isnan(pe) and pe > 0.7):
        return "reversible"
    if epr > 0.05 and abs(flux_index) > 0.3:
        return "directional"
    if epr > 0.2:
        return "turbulent"
    return "mixed"


def _compute_window_metrics(window_returns: np.ndarray, cfg: IGSConfig) -> Optional[Tuple[float, float, float, float, float, str]]:
    finite_mask = np.isfinite(window_returns)
    if np.count_nonzero(finite_mask) < cfg.min_counts:
        return None
    if not np.all(finite_mask):
        return None

    states = _quantize_states(window_returns, cfg.n_states)
    counts = _transition_counts(states, cfg.n_states)
    P = _transition_matrix(counts, cfg.eps)
    pi = _stationary_distribution(states, cfg.n_states, cfg.eps)
    epr, flux = _entropy_production(P, pi, cfg.eps)
    flux_index = _flux_index(flux, cfg.normalize_flux)
    tra = _time_reversal_asymmetry(window_returns)
    pe = _permutation_entropy(window_returns, cfg.perm_emb_dim, cfg.perm_tau, cfg.eps)
    components = _regime_components(epr, flux_index, pe)
    regime_score = _regime_score(components, cfg.regime_weights)
    regime = _classify_regime(epr, flux_index, pe)
    return epr, flux_index, tra, pe, regime_score, regime


# ---------------------------------------------------------------------------
# Batch interface
# ---------------------------------------------------------------------------
def compute_igs_features(price: pd.Series, cfg: Optional[IGSConfig] = None) -> pd.DataFrame:
    """Compute IGS features for the provided price series."""
    if cfg is None:
        cfg = IGSConfig()
    if price.isnull().any():
        price = price.dropna()
    if (price <= 0).any():
        raise ValueError("price series must contain strictly positive values")

    returns = _log_returns(price).iloc[1:]
    if cfg.detrend:
        trend = returns.rolling(max(5, cfg.window // 10), min_periods=1).mean()
        returns = returns - trend

    features = pd.DataFrame(
        data=np.nan,
        index=price.index,
        columns=["epr", "flux_index", "tra", "pe", "regime_score"],
    )

    values = returns.to_numpy()
    timestamps = returns.index.to_list()
    window = cfg.window

    for end in range(window, len(values) + 1):
        window_returns = values[end - window : end]
        metrics = _compute_window_metrics(window_returns, cfg)
        if metrics is None:
            continue
        epr, flux_index, tra, pe, regime_score, _ = metrics
        ts = timestamps[end - 1]
        features.loc[ts, "epr"] = epr
        features.loc[ts, "flux_index"] = flux_index
        features.loc[ts, "tra"] = tra
        features.loc[ts, "pe"] = pe
        features.loc[ts, "regime_score"] = regime_score

    return features


def igs_directional_signal(
    features: pd.DataFrame,
    *,
    epr_q: float = 0.7,
    flux_q: float = 0.6,
    regime_threshold: Optional[float] = None,
) -> pd.Series:
    """Generate a {-1, 0, 1} gating signal from IGS feature columns."""
    required_cols = {"epr", "flux_index", "regime_score"}
    missing = required_cols - set(features.columns)
    if missing:
        raise ValueError(f"features missing required columns: {sorted(missing)}")

    result = pd.Series(0, index=features.index, dtype=int)
    mask = features[["epr", "flux_index"]].notna().all(axis=1)
    if regime_threshold is not None:
        mask &= features["regime_score"] >= regime_threshold
    if not mask.any():
        return result

    epr_threshold = features.loc[mask, "epr"].quantile(epr_q)
    flux_threshold = features.loc[mask, "flux_index"].abs().quantile(flux_q)

    long_mask = mask & (features["epr"] >= epr_threshold) & (features["flux_index"] >= max(flux_threshold, 0.0))
    short_mask = mask & (features["epr"] >= epr_threshold) & (features["flux_index"] <= -max(flux_threshold, 0.0))

    result[long_mask] = 1
    result[short_mask] = -1
    return result


# ---------------------------------------------------------------------------
# Streaming engine
# ---------------------------------------------------------------------------
class StreamingIGS:
    """Streaming computation of IGS metrics."""

    def __init__(self, cfg: Optional[IGSConfig] = None) -> None:
        self.cfg = cfg or IGSConfig()
        self._returns: deque[float] = deque(maxlen=self.cfg.window)
        self._last_price: Optional[float] = None
        self._last_metrics: Optional[IGSMetrics] = None

    def update(self, timestamp: pd.Timestamp, price: float) -> Optional[IGSMetrics]:
        if price <= 0:
            raise ValueError("price must be positive")

        if self._last_price is None:
            self._last_price = float(price)
            return None

        ret = math.log(price) - math.log(self._last_price)
        self._last_price = float(price)
        self._returns.append(ret)

        if len(self._returns) < self.cfg.window:
            return None

        window_returns = np.fromiter(self._returns, dtype=float, count=len(self._returns))
        metrics = _compute_window_metrics(window_returns, self.cfg)
        if metrics is None:
            return None

        igs_metrics = IGSMetrics(
            timestamp=pd.Timestamp(timestamp),
            epr=metrics[0],
            flux_index=metrics[1],
            tra=metrics[2],
            pe=metrics[3],
            regime_score=metrics[4],
            regime=metrics[5],
        )
        self._last_metrics = igs_metrics
        return igs_metrics

    def get_current_metrics(self) -> Optional[IGSMetrics]:
        return self._last_metrics

    def get_signal(
        self,
        *,
        epr_threshold: Optional[float] = None,
        flux_threshold: Optional[float] = None,
        regime_threshold: Optional[float] = None,
    ) -> int:
        metrics = self._last_metrics
        if metrics is None:
            return 0

        if regime_threshold is not None and not (metrics.regime_score >= regime_threshold):
            return 0

        epr_ok = epr_threshold is None or metrics.epr >= epr_threshold
        flux_ok = flux_threshold is None or abs(metrics.flux_index) >= flux_threshold
        if not (epr_ok and flux_ok):
            return 0

        if metrics.flux_index > 0:
            return 1
        if metrics.flux_index < 0:
            return -1
        return 0

    def reset(self) -> None:
        self._returns.clear()
        self._last_price = None
        self._last_metrics = None
