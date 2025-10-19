"""Irreversibility-Gated Signal (IGS).

This module implements batch and streaming utilities for computing metrics that
capture time-irreversibility in financial time series. The public surface is
kept deliberately small to ease integration inside TradePulse pipelines while
allowing offline research workflows and real-time execution to share the same
logic.

Exports
-------
- :class:`IGSConfig`
- :class:`IGSMetrics`
- :func:`compute_igs_features`
- :func:`igs_directional_signal`
- :class:`StreamingIGS`
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Deque, Literal, Optional, Sequence, Tuple

import math
from collections import deque

import numpy as np
import pandas as pd

__all__ = [
    "IGSConfig",
    "IGSMetrics",
    "compute_igs_features",
    "igs_directional_signal",
    "StreamingIGS",
]


@dataclass(slots=True)
class IGSConfig:
    """Configuration for Irreversibility-Gated Signal computations."""

    window: int = 600
    n_states: int = 7
    min_counts: int = 50
    eps: float = 1e-12
    normalize_flux: bool = True
    detrend: bool = False
    perm_emb_dim: int = 5
    perm_tau: int = 1
    pi_method: Literal["empirical", "eigen"] = "empirical"
    regime_weights: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    rolling_normalize: bool = False
    tra_buffer_size: int = 1000

    def __post_init__(self) -> None:
        if self.window <= 2:
            raise ValueError("window must be greater than 2")
        if self.n_states < 3:
            raise ValueError("n_states must be at least 3")
        if self.min_counts < 0:
            raise ValueError("min_counts must be non-negative")
        if self.perm_emb_dim < 3:
            raise ValueError("perm_emb_dim must be at least 3 for permutation entropy")
        if self.perm_tau < 1:
            raise ValueError("perm_tau must be positive")
        if len(self.regime_weights) != 3:
            raise ValueError("regime_weights must contain three values")


@dataclass(slots=True)
class IGSMetrics:
    """Container emitted by :class:`StreamingIGS` for the latest observation."""

    timestamp: pd.Timestamp
    epr: float
    flux_index: float
    tra: float
    pe: float
    regime_score: float
    regime: str = "unknown"


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _ensure_positive_prices(price: pd.Series) -> None:
    if (price <= 0.0).any():
        raise ValueError("IGS requires strictly positive prices for log returns")


def _log_returns(price: pd.Series) -> pd.Series:
    returns = np.log(price).diff()
    returns.name = "log_return"
    return returns


def _quantize_returns(values: Sequence[float], n_states: int) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return np.empty(0, dtype=int)
    ranks = pd.Series(arr).rank(method="average", pct=True).to_numpy()
    states = np.floor(ranks * n_states).astype(int)
    np.clip(states, 0, n_states - 1, out=states)
    return states


def _transition_matrix(states: np.ndarray, n_states: int, eps: float) -> Tuple[np.ndarray, np.ndarray]:
    counts = np.zeros((n_states, n_states), dtype=float)
    for src, dst in zip(states[:-1], states[1:]):
        counts[src, dst] += 1.0
    outgoing = counts.sum(axis=1, keepdims=True)
    denominator = outgoing + n_states * eps
    P = (counts + eps) / denominator
    occupancy = counts.sum(axis=1)
    total = occupancy.sum()
    if total <= eps:
        pi = np.full(n_states, 1.0 / n_states, dtype=float)
    else:
        pi = occupancy / (total + eps)
    return P, pi


def _entropy_production_rate(P: np.ndarray, pi: np.ndarray, eps: float) -> Tuple[float, np.ndarray]:
    pij = np.maximum(pi[:, None] * P, eps)
    pji = np.maximum(pi[None, :] * P.T, eps)
    matrix = pij * (np.log(pij) - np.log(pji))
    epr = float(np.nansum(matrix))
    flux = pij - pji
    return epr, flux


def _flux_index(flux: np.ndarray, normalize: bool) -> float:
    n = flux.shape[0]
    idxs = np.arange(n)
    weights = idxs[None, :] - idxs[:, None]
    upper = np.triu_indices(n, k=1)
    numerator = float(np.sum(flux[upper] * weights[upper]))
    denominator = float(np.sum(np.abs(flux[upper] * weights[upper])) + 1e-12)
    value = numerator / denominator
    if normalize:
        return float(np.clip(value, -1.0, 1.0))
    return value


def _time_reversal_asymmetry(arr: np.ndarray) -> float:
    if arr.size < 3:
        return float("nan")
    forward = np.mean(arr[1:] ** 2 * arr[:-1])
    backward = np.mean(arr[:-1] ** 2 * arr[1:])
    return float(forward - backward)


def _permutation_entropy(arr: np.ndarray, dim: int, tau: int, eps: float) -> float:
    n = arr.size - (dim - 1) * tau
    if dim < 3 or n <= 1:
        return float("nan")
    patterns: dict[tuple[int, ...], int] = {}
    for start in range(n):
        window = arr[start : start + dim * tau : tau]
        order = tuple(np.argsort(window, kind="mergesort"))
        patterns[order] = patterns.get(order, 0) + 1
    counts = np.fromiter(patterns.values(), dtype=float)
    probabilities = counts / counts.sum()
    entropy = -np.sum(probabilities * (np.log(probabilities + eps)))
    entropy_max = math.log(math.factorial(dim))
    return float(entropy / entropy_max)


def _weighted_regime_score(components: Sequence[float], weights: Sequence[float]) -> float:
    comp = np.asarray(components, dtype=float)
    mask = np.isfinite(comp)
    if not np.any(mask):
        return float("nan")
    comp = comp[mask]
    w = np.asarray(weights, dtype=float)[mask]
    if np.allclose(w, 0.0):
        w = np.ones_like(comp)
    score = np.average(comp, weights=w)
    return float(np.clip(score, 0.0, 1.0))


def _classify_regime(epr: float, flux_index: float, pe: float) -> str:
    if not math.isfinite(epr):
        return "unknown"
    if epr < 1e-3 and (math.isfinite(pe) and pe > 0.75):
        return "reversible"
    if epr > 0.1 and abs(flux_index) > 0.3:
        return "directional"
    if epr > 0.2:
        return "turbulent"
    return "mixed"


# ---------------------------------------------------------------------------
# Batch computation
# ---------------------------------------------------------------------------

def compute_igs_features(price: pd.Series, cfg: Optional[IGSConfig] = None) -> pd.DataFrame:
    """Compute IGS metrics on a price series.

    Parameters
    ----------
    price:
        Series indexed by timestamp containing strictly positive prices.
    cfg:
        Optional :class:`IGSConfig` overriding defaults.

    Returns
    -------
    pandas.DataFrame
        DataFrame aligned with ``price.index`` containing columns
        ``["epr", "flux_index", "tra", "pe", "regime_score"]``.
    """

    if price.empty:
        return pd.DataFrame(
            {
                "epr": pd.Series(dtype=float),
                "flux_index": pd.Series(dtype=float),
                "tra": pd.Series(dtype=float),
                "pe": pd.Series(dtype=float),
                "regime_score": pd.Series(dtype=float),
            },
            index=price.index,
        )

    configuration = cfg or IGSConfig()
    _ensure_positive_prices(price)

    returns = _log_returns(price)
    if configuration.detrend:
        window = max(5, configuration.window // 10)
        returns = returns - returns.rolling(window=window, min_periods=1).mean()

    result = pd.DataFrame(index=returns.index, columns=["epr", "flux_index", "tra", "pe", "regime_score"], dtype=float)
    values = returns.to_numpy()

    weights = configuration.regime_weights

    for end in range(configuration.window, len(values)):
        window_slice = values[end - configuration.window : end]
        valid = np.isfinite(window_slice)
        if np.count_nonzero(valid) < configuration.min_counts or np.count_nonzero(valid) < 2:
            continue
        clean_returns = window_slice[valid]
        states = _quantize_returns(clean_returns, configuration.n_states)
        if states.size < 2:
            continue
        transition, pi = _transition_matrix(states, configuration.n_states, configuration.eps)
        epr, flux = _entropy_production_rate(transition, pi, configuration.eps)
        flux_index = _flux_index(flux, configuration.normalize_flux)
        tra = _time_reversal_asymmetry(clean_returns)
        pe = _permutation_entropy(clean_returns, configuration.perm_emb_dim, configuration.perm_tau, configuration.eps)

        components = (
            math.log1p(epr),
            abs(flux_index),
            1.0 - pe if math.isfinite(pe) else float("nan"),
        )
        regime_score = _weighted_regime_score(components, weights)

        timestamp = returns.index[end]
        result.loc[timestamp, "epr"] = epr
        result.loc[timestamp, "flux_index"] = flux_index
        result.loc[timestamp, "tra"] = tra
        result.loc[timestamp, "pe"] = pe
        result.loc[timestamp, "regime_score"] = regime_score

    return result


# ---------------------------------------------------------------------------
# Directional signal helper
# ---------------------------------------------------------------------------

def igs_directional_signal(
    features: pd.DataFrame,
    *,
    epr_q: float = 0.7,
    flux_q: float = 0.6,
    regime_threshold: Optional[float] = None,
) -> pd.Series:
    """Generate a discrete directional signal from computed features."""

    required_columns = {"epr", "flux_index", "regime_score"}
    missing = required_columns.difference(features.columns)
    if missing:
        raise KeyError(f"features DataFrame is missing required columns: {sorted(missing)}")

    signal = pd.Series(0, index=features.index, dtype=int)
    mask = features["epr"].notna() & features["flux_index"].notna()
    if not mask.any():
        return signal

    quantile_threshold = features.loc[mask, "epr"].quantile(epr_q)
    flux_threshold = features.loc[mask, "flux_index"].abs().quantile(flux_q)
    gated = mask & (features["epr"] >= quantile_threshold) & (features["flux_index"].abs() >= flux_threshold)
    if regime_threshold is not None:
        gated &= features["regime_score"] >= regime_threshold

    signal[gated & (features["flux_index"] > 0.0)] = 1
    signal[gated & (features["flux_index"] < 0.0)] = -1
    return signal


# ---------------------------------------------------------------------------
# Streaming implementation
# ---------------------------------------------------------------------------


class IncrementalTRA:
    """Naïve incremental computation of time-reversal asymmetry."""

    def __init__(self, window: int) -> None:
        self.window = max(3, window)
        self._buffer: Deque[float] = deque(maxlen=self.window)

    def update(self, value: float) -> float:
        self._buffer.append(float(value))
        if len(self._buffer) < 3:
            return float("nan")
        arr = np.fromiter(self._buffer, dtype=float)
        return _time_reversal_asymmetry(arr)


class IncrementalPE:
    """Sliding permutation entropy estimator."""

    def __init__(self, dimension: int, tau: int, window: int, eps: float) -> None:
        self.dimension = dimension
        self.tau = tau
        self.window = max(window, dimension * tau + 1)
        self.eps = eps
        self._buffer: Deque[float] = deque(maxlen=self.window)

    def update(self, value: float) -> float:
        self._buffer.append(float(value))
        arr = np.fromiter(self._buffer, dtype=float)
        return _permutation_entropy(arr, self.dimension, self.tau, self.eps)


class StreamingIGS:
    """Incremental engine for IGS metrics."""

    def __init__(self, cfg: Optional[IGSConfig] = None) -> None:
        self.cfg = cfg or IGSConfig()
        self._returns: Deque[float] = deque(maxlen=self.cfg.window)
        self._states: Deque[int] = deque(maxlen=self.cfg.window)
        self._transition = np.zeros((self.cfg.n_states, self.cfg.n_states), dtype=float)
        self._state_counts = np.zeros(self.cfg.n_states, dtype=float)
        self._row_sums = np.zeros(self.cfg.n_states, dtype=float)
        self._last_price: Optional[float] = None
        self._tra = IncrementalTRA(min(self.cfg.window, self.cfg.tra_buffer_size))
        self._pe = IncrementalPE(self.cfg.perm_emb_dim, self.cfg.perm_tau, self.cfg.window, self.cfg.eps)

    def _remove_oldest_state(self) -> None:
        if not self._states:
            return
        oldest = self._states[0]
        successor = self._states[1] if len(self._states) > 1 else None
        self._states.popleft()
        self._state_counts[oldest] = max(0.0, self._state_counts[oldest] - 1.0)
        if successor is not None:
            self._transition[oldest, successor] = max(0.0, self._transition[oldest, successor] - 1.0)
            self._row_sums[oldest] = max(0.0, self._row_sums[oldest] - 1.0)

    def _quantize_latest(self, latest: float) -> int:
        if not self._returns:
            return self.cfg.n_states // 2
        arr = np.fromiter(self._returns, dtype=float)
        rank = np.sum(arr <= latest) / arr.size
        state = int(math.floor(rank * self.cfg.n_states))
        return int(np.clip(state, 0, self.cfg.n_states - 1))

    def update(self, timestamp: pd.Timestamp, price: float) -> Optional[IGSMetrics]:
        price_value = float(price)
        if price_value <= 0.0:
            raise ValueError("StreamingIGS requires strictly positive prices")
        if self._last_price is None:
            self._last_price = price_value
            return None

        ret = math.log(price_value) - math.log(self._last_price)
        self._last_price = price_value

        if len(self._returns) == self._returns.maxlen:
            self._returns.popleft()
        self._returns.append(ret)

        if len(self._states) == self._states.maxlen:
            self._remove_oldest_state()

        state = self._quantize_latest(ret)
        previous = self._states[-1] if self._states else None
        self._states.append(state)
        self._state_counts[state] += 1.0

        if previous is not None:
            self._transition[previous, state] += 1.0
            self._row_sums[previous] += 1.0

        tra = self._tra.update(ret)
        pe = self._pe.update(ret)

        transitions = float(np.sum(self._row_sums))
        if transitions < self.cfg.min_counts:
            return None

        transition_matrix = np.zeros_like(self._transition)
        for idx in range(self.cfg.n_states):
            denominator = self._row_sums[idx] + self.cfg.n_states * self.cfg.eps
            if denominator <= 0.0:
                transition_matrix[idx, :] = 1.0 / self.cfg.n_states
            else:
                transition_matrix[idx, :] = (self._transition[idx, :] + self.cfg.eps) / denominator

        if self.cfg.pi_method == "empirical":
            pi = self._state_counts.copy()
            total = pi.sum()
            if total <= self.cfg.eps:
                pi = np.full(self.cfg.n_states, 1.0 / self.cfg.n_states)
            else:
                pi = pi / (total + self.cfg.eps)
        else:
            # fall back to empirical; eigen option can be added later if needed
            pi = self._state_counts.copy()
            total = pi.sum()
            if total <= self.cfg.eps:
                pi = np.full(self.cfg.n_states, 1.0 / self.cfg.n_states)
            else:
                pi = pi / (total + self.cfg.eps)

        epr, flux = _entropy_production_rate(transition_matrix, pi, self.cfg.eps)
        flux_index = _flux_index(flux, self.cfg.normalize_flux)

        components = (
            math.log1p(epr),
            abs(flux_index),
            1.0 - pe if math.isfinite(pe) else float("nan"),
        )
        regime_score = _weighted_regime_score(components, self.cfg.regime_weights)
        regime = _classify_regime(epr, flux_index, pe)

        return IGSMetrics(
            timestamp=timestamp,
            epr=epr,
            flux_index=flux_index,
            tra=tra,
            pe=pe,
            regime_score=regime_score,
            regime=regime,
        )
