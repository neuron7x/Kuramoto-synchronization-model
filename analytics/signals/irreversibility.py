# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""
Irreversibility-Gated Signal (IGS) — Hybrid Core
================================================
Features:
- Entropy Production Rate (EPR) on K-state Markov discretization of log-returns
- Probability flux tensor J and scalar FluxIndex in [-1, 1]
- Time-Reversal Asymmetry (TRA, third order) with exact O(1) rolling update
- Permutation Entropy (PE) with incremental multiset maintenance after warmup
- Composite regime_score computed as a weighted mean of log1p(EPR), |FluxIndex|, and (1 - PE)

Streaming:
- O(1) updates for transition counts
- Quantization via pluggable strategies (Z-score or sliding rank) with parity to the batch implementation
- Hysteretic K-adaptation with cooldown; O(W) rebuild only on change
- Asynchronous Prometheus emission (optional)
- Overload guard via max_update_ms for latency-aware degradation

Dependencies: numpy, pandas. Optional: prometheus_client.
"""

from __future__ import annotations

import logging
import math
import queue
import threading
import time
from bisect import bisect_left, bisect_right
from collections import deque
from dataclasses import dataclass
from typing import (
    Callable,
    ClassVar,
    Deque,
    Dict,
    List,
    Optional,
    Protocol,
    Sequence,
    Set,
    Tuple,
    runtime_checkable,
)

import numpy as np
import pandas as pd

try:
    import prometheus_client
except Exception:
    prometheus_client = None

logger = logging.getLogger(__name__)


@dataclass
class IGSConfig:
    window: int = 600
    n_states: int = 7
    min_counts: int = 50
    eps: float = 1e-12
    normalize_flux: bool = True
    detrend: bool = False
    quantize_mode: str = "zscore"
    perm_emb_dim: int = 5
    perm_tau: int = 1
    adapt_method: str = "off"
    k_min: Optional[int] = None
    k_max: Optional[int] = None
    adapt_threshold: float = 0.10
    adapt_persist: int = 3
    adapt_cooldown: int = 50
    adapt_step: int = 1
    instrument_label: Optional[str] = None
    prometheus_enabled: bool = False
    prometheus_async: bool = True
    max_update_ms: float = 0.0
    pi_method: str = "empirical"
    regime_weights: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    signal_epr_q: float = 0.7
    signal_flux_min: float = 0.0

    _ALLOWED_ADAPT_METHODS: ClassVar[Set[str]] = {"off", "entropy", "external"}
    _ALLOWED_QUANTIZE_MODES: ClassVar[Set[str]] = {"zscore", "rank", "sliding_rank"}
    _ALLOWED_PI_METHODS: ClassVar[Set[str]] = {"empirical", "stationary"}

    def __post_init__(self) -> None:
        if self.window < 3:
            raise ValueError("window must be >= 3")
        if self.n_states < 2:
            raise ValueError("n_states must be >= 2")
        if self.min_counts < 1:
            raise ValueError("min_counts must be >= 1")
        if self.min_counts > self.window:
            raise ValueError("min_counts must be <= window")
        if self.eps <= 0.0:
            raise ValueError("eps must be > 0")
        if self.perm_emb_dim < 3:
            raise ValueError("perm_emb_dim must be >= 3")
        if self.perm_tau < 1:
            raise ValueError("perm_tau must be >= 1")
        min_window_for_pe = (self.perm_emb_dim - 1) * self.perm_tau + 1
        if self.window < min_window_for_pe:
            raise ValueError(
                "window must be >= (perm_emb_dim - 1) * perm_tau + 1 to compute permutation entropy"
            )
        default_k_min = 5
        default_k_max = 15

        if self.k_min is None:
            inferred_k_min = min(default_k_min, self.n_states)
            self.k_min = max(2, inferred_k_min)

        if self.k_max is None:
            inferred_k_max = max(default_k_max, self.n_states)
            self.k_max = inferred_k_max

        if self.k_min < 2:
            raise ValueError("k_min must be >= 2")
        if self.k_min > self.k_max:
            raise ValueError("k_min must be <= k_max")
        if not (self.k_min <= self.n_states <= self.k_max):
            raise ValueError("n_states must satisfy k_min <= n_states <= k_max")
        if self.adapt_method not in self._ALLOWED_ADAPT_METHODS:
            raise ValueError(f"adapt_method must be one of {sorted(self._ALLOWED_ADAPT_METHODS)}")
        quantize_mode_normalized = self.quantize_mode.lower()
        if quantize_mode_normalized not in self._ALLOWED_QUANTIZE_MODES:
            raise ValueError(f"quantize_mode must be one of {sorted(self._ALLOWED_QUANTIZE_MODES)}")
        # Internally canonicalise sliding_rank to rank to simplify downstream checks.
        self.quantize_mode = (
            "rank" if quantize_mode_normalized == "sliding_rank" else quantize_mode_normalized
        )
        pi_method_normalized = self.pi_method.lower()
        if pi_method_normalized not in self._ALLOWED_PI_METHODS:
            raise ValueError(f"pi_method must be one of {sorted(self._ALLOWED_PI_METHODS)}")
        self.pi_method = pi_method_normalized

        weights = tuple(self.regime_weights)
        if len(weights) != 3:
            raise ValueError("regime_weights must contain exactly three elements")
        if any(w < 0 for w in weights):
            raise ValueError("regime_weights must be non-negative")
        if not any(w > 0 for w in weights):
            raise ValueError("regime_weights cannot be all zeros")
        self.regime_weights = weights

        if self.max_update_ms < 0:
            raise ValueError("max_update_ms must be >= 0")
        if not (0.0 < self.signal_epr_q < 1.0):
            raise ValueError("signal_epr_q must be in (0, 1)")
        if self.signal_flux_min < 0:
            raise ValueError("signal_flux_min must be >= 0")


@dataclass
class IGSMetrics:
    timestamp: pd.Timestamp
    epr: float
    flux_index: float
    tra: float
    pe: float
    regime_score: float
    regime: str
    n_states_used: int


def _safe_log(x: np.ndarray, eps: float) -> np.ndarray:
    return np.log(np.maximum(x, eps))


def _weighted_regime_score(components: Sequence[float], weights: Sequence[float]) -> float:
    """Compute a weighted mean of regime components while ignoring NaNs and zero weights."""

    values = np.asarray(list(components), dtype=float)
    w = np.asarray(list(weights), dtype=float)
    if values.shape != w.shape:
        raise ValueError("components and weights must have the same length")
    valid = np.isfinite(values) & np.isfinite(w) & (w > 0.0)
    if not np.any(valid):
        return float("nan")
    weights_normalised = w[valid]
    weights_normalised = weights_normalised / weights_normalised.sum()
    return float(np.dot(values[valid], weights_normalised))


def _ndtri(p: float) -> float:
    a = [
        -3.969683028665376e01,
        2.209460984245205e02,
        -2.759285104469687e02,
        1.383577518672690e02,
        -3.066479806614716e01,
        2.506628277459239e00,
    ]
    b = [
        -5.447609879822406e01,
        1.615858368580409e02,
        -1.556989798598866e02,
        6.680131188771972e01,
        -1.328068155288572e01,
    ]
    c = [
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e00,
        -2.549732539343734e00,
        4.374664141464968e00,
        2.938163982698783e00,
    ]
    d = [
        7.784695709041462e-03,
        3.224671290700398e-01,
        2.445134137142996e00,
        3.754408661907416e00,
    ]
    plow = 0.02425
    phigh = 1 - plow
    if p <= 0 or p >= 1:
        return float("nan")
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1
        )
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1
        )
    q = p - 0.5
    r = q * q
    return (
        (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5])
        * q
        / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
    )


class RollingMeanStd:
    def __init__(self, window: int):
        self.W = window
        self.buf: Deque[float] = deque(maxlen=window)
        self.sum = 0.0
        self.sumsq = 0.0

    def add(self, x: float):
        if len(self.buf) == self.W:
            x_old = self.buf[0]
            self.sum -= x_old
            self.sumsq -= x_old * x_old
            self.buf.popleft()
        self.buf.append(x)
        self.sum += x
        self.sumsq += x * x

    def stats(self) -> Tuple[float, float]:
        n = len(self.buf)
        if n == 0:
            return 0.0, 1.0
        mean = self.sum / n
        var = max(self.sumsq / n - mean * mean, 1e-12)
        std = math.sqrt(var)
        return mean, std


@runtime_checkable
class Quantizer(Protocol):
    K: int

    def update_and_state(self, x: float) -> int: ...

    def state_for_value(self, x: float) -> int: ...


class ZScoreQuantizer:
    def __init__(self, window: int, n_states: int):
        self.W = window
        self.K = n_states
        self.roll = RollingMeanStd(window)
        self.boundaries = np.array([_ndtri(i / n_states) for i in range(1, n_states)], dtype=float)

    def update_and_state(self, x: float) -> int:
        self.roll.add(x)
        mean, std = self.roll.stats()
        z = (x - mean) / (std if std > 1e-12 else 1.0)
        s = int(np.searchsorted(self.boundaries, z, side="right"))
        return int(np.clip(s, 0, self.K - 1))

    def state_for_value(self, x: float) -> int:
        mean, std = self.roll.stats()
        z = (x - mean) / (std if std > 1e-12 else 1.0)
        s = int(np.searchsorted(self.boundaries, z, side="right"))
        return int(np.clip(s, 0, self.K - 1))


class RollingRankQuantizer:
    def __init__(self, window: int, n_states: int):
        if window <= 0:
            raise ValueError("window must be positive")
        if n_states <= 0:
            raise ValueError("n_states must be positive")
        self.W = window
        self.K = n_states
        self.buf: Deque[Tuple[float, int]] = deque()
        self.sorted: List[Tuple[float, int]] = []
        self._counter = 0

    def _evict_oldest(self) -> None:
        if len(self.buf) < self.W:
            return
        old = self.buf.popleft()
        idx = bisect_left(self.sorted, old)
        if idx < len(self.sorted) and self.sorted[idx] == old:
            self.sorted.pop(idx)

    def _insert(self, x: float) -> Tuple[float, int]:
        ident = self._counter
        self._counter += 1
        item = (x, ident)
        idx = bisect_left(self.sorted, item)
        self.sorted.insert(idx, item)
        self.buf.append(item)
        return item

    def _state_from_value(self, x: float) -> int:
        n = len(self.sorted)
        if n == 0:
            return 0
        lo = bisect_left(self.sorted, (x, -math.inf))
        hi = bisect_right(self.sorted, (x, math.inf))
        avg_rank = ((lo + 1) + hi) / 2.0
        centered_rank = avg_rank - 0.5
        pct = centered_rank / n
        if n > 0:
            upper_bound = 1.0 - (0.5 / n)
        else:
            upper_bound = 0.0
        pct = min(max(pct, 0.0), upper_bound)
        state = int(pct * self.K)
        if state >= self.K:
            state = self.K - 1
        if state < 0:
            state = 0
        return state

    def update_and_state(self, x: float) -> int:
        if len(self.buf) == self.W:
            self._evict_oldest()
        self._insert(x)
        return self._state_from_value(x)

    def state_for_value(self, x: float) -> int:
        return self._state_from_value(x)


SlidingRankQuantizer = RollingRankQuantizer


def _make_quantizer(mode: str, window: int, n_states: int) -> Quantizer:
    normalized = mode.lower()
    if normalized == "zscore":
        return ZScoreQuantizer(window, n_states)
    if normalized in {"rank", "sliding_rank"}:
        return RollingRankQuantizer(window, n_states)
    raise ValueError(f"Unsupported quantize_mode: {mode}")


class RollingTRA:
    def __init__(self, window: int):
        if window < 3:
            raise ValueError("TRA window must be >= 3")
        self.W = window
        self.buf: Deque[float] = deque(maxlen=window)
        self.sum_xy = 0.0
        self.sum_yx = 0.0
        self.n_pairs = 0

    def update(self, r_t: float) -> float:
        if len(self.buf) == self.W and len(self.buf) >= 2:
            old_prev = self.buf[0]
            old_cur = self.buf[1]
            self.sum_xy -= (old_cur**2) * old_prev
            self.sum_yx -= (old_prev**2) * old_cur
            self.n_pairs = max(0, self.n_pairs - 1)
            self.buf.popleft()
        if len(self.buf) >= 1:
            r_prev = self.buf[-1]
            self.sum_xy += (r_t**2) * r_prev
            self.sum_yx += (r_prev**2) * r_t
            self.n_pairs += 1
        self.buf.append(r_t)
        if self.n_pairs == 0:
            return float("nan")
        return (self.sum_xy / self.n_pairs) - (self.sum_yx / self.n_pairs)

    def reset(self) -> None:
        self.buf.clear()
        self.sum_xy = 0.0
        self.sum_yx = 0.0
        self.n_pairs = 0


class RollingPermutationEntropy:
    def __init__(self, window: int, m: int = 5, tau: int = 1):
        if m < 3:
            raise ValueError("m >= 3 required")
        if tau < 1:
            raise ValueError("tau >= 1 required")
        self.W = window
        self.m = m
        self.tau = tau
        self.buf: Deque[float] = deque(maxlen=window)
        self.counts: Dict[Tuple[int, ...], int] = {}
        self.total = 0
        self.initialized = False

    def _pattern_at(self, arr: List[float], start: int) -> Tuple[int, ...]:
        seq = arr[start : start + self.m * self.tau : self.tau]
        order = tuple(np.argsort(seq, kind="mergesort"))
        return order

    def _rebuild(self, arr: List[float]):
        self.counts.clear()
        P = len(arr) - (self.m - 1) * self.tau
        if P <= 0:
            self.total = 0
            self.initialized = False
            return
        for s in range(P):
            pat = self._pattern_at(arr, s)
            self.counts[pat] = self.counts.get(pat, 0) + 1
        self.total = P
        self.initialized = True

    def _entropy(self) -> float:
        if self.total <= 0:
            return float("nan")
        c = np.array(list(self.counts.values()), dtype=float)
        p = c / c.sum()
        H = -np.sum(p * np.log(p + 1e-12))
        Hmax = math.log(math.factorial(self.m))
        return float(H / Hmax)

    def update(self, x: float) -> float:
        if len(self.buf) == self.W:
            if not self.initialized:
                self._rebuild(list(self.buf))
            P = self.W - (self.m - 1) * self.tau
            if P > 0:
                arr_old = list(self.buf)
                pat_old = self._pattern_at(arr_old, 0)
                cnt = self.counts.get(pat_old, 0)
                if cnt > 1:
                    self.counts[pat_old] = cnt - 1
                elif cnt == 1:
                    del self.counts[pat_old]
                self.total -= 1
            self.buf.popleft()
        self.buf.append(x)
        if len(self.buf) < self.W:
            self._rebuild(list(self.buf))
            return self._entropy()
        arr_new = list(self.buf)
        P = self.W - (self.m - 1) * self.tau
        if P <= 0:
            self.initialized = False
            return float("nan")
        pat_new = self._pattern_at(arr_new, P - 1)
        self.counts[pat_new] = self.counts.get(pat_new, 0) + 1
        self.total += 1
        return self._entropy()

    def reset(self) -> None:
        self.buf.clear()
        self.counts.clear()
        self.total = 0
        self.initialized = False


def _returns_from_prices(price: pd.Series) -> pd.Series:
    if not isinstance(price, pd.Series):
        raise TypeError("price must be a pandas Series")
    price = price.where(price > 0, np.nan)
    return np.log(price).diff()


def _stationary_distribution(P: np.ndarray, eps: float) -> np.ndarray:
    K = P.shape[0]
    A = np.vstack([P.T - np.eye(K), np.ones((1, K))])
    b = np.concatenate([np.zeros(K), np.array([1.0])])
    reg = max(eps, 1e-8)
    try:
        AtA = A.T @ A
        Atb = A.T @ b
        pi = np.linalg.solve(AtA + reg * np.eye(K), Atb)
    except np.linalg.LinAlgError:
        pi, *_ = np.linalg.lstsq(A, b, rcond=None)
    pi = np.maximum(pi, 0.0)
    s = float(pi.sum())
    if not np.isfinite(s) or s < eps:
        return np.full(K, 1.0 / K, dtype=float)
    return pi / s


def _transition_matrix(states: np.ndarray, n_states: int, eps: float, pi_method: str = "empirical"):
    T = np.zeros((n_states, n_states), dtype=float)
    for a, b in zip(states[:-1], states[1:]):
        T[a, b] += 1.0
    counts_out = T.sum(axis=1, keepdims=True)
    P = (T + eps) / (counts_out + n_states * eps)
    if pi_method == "stationary":
        pi = _stationary_distribution(P, eps)
    else:
        pi = T.sum(axis=1)
        if pi.sum() < eps:
            pi = np.full(n_states, 1.0 / n_states, dtype=float)
        else:
            pi = pi / (pi.sum() + eps)
    return P, pi


def _entropy_production(P: np.ndarray, pi: np.ndarray, eps: float):
    pij = np.maximum(pi[:, None] * P, eps)
    pji = np.maximum(pi[None, :] * P.T, eps)
    epr_matrix = pij * (_safe_log(pij, eps) - _safe_log(pji, eps))
    epr = float(np.nansum(epr_matrix))
    J = pij - pji
    return epr, J


def _net_flux_index(J: np.ndarray, normalize: bool = True):
    n = J.shape[0]
    idxs = np.arange(n)
    weight = idxs[None, :] - idxs[:, None]
    upper = np.triu_indices(n, k=1)
    num = float(np.sum(J[upper] * weight[upper]))
    den = float(np.sum(np.abs(J[upper] * weight[upper])) + 1e-12)
    x = num / den
    return float(np.clip(x, -1.0, 1.0)) if normalize else num


def _time_reversal_asymmetry_arr(r: np.ndarray) -> float:
    if len(r) < 3:
        return float("nan")
    a = float(np.mean(r[1:] ** 2 * r[:-1]))
    b = float(np.mean(r[:-1] ** 2 * r[1:]))
    return a - b


def _permutation_entropy_arr(x: np.ndarray, dim: int, tau: int, eps: float) -> float:
    n = len(x) - (dim - 1) * tau
    if dim < 3 or n <= 1:
        return float("nan")
    counts: Dict[Tuple[int, ...], int] = {}
    for i in range(n):
        window = x[i : i + dim * tau : tau]
        order = tuple(np.argsort(window, kind="mergesort"))
        counts[order] = counts.get(order, 0) + 1
    c = np.array(list(counts.values()), dtype=float)
    p = c / c.sum()
    H = -np.sum(p * np.log(p + eps))
    Hmax = math.log(math.factorial(dim))
    return float(H / Hmax)


def compute_igs_features(price: pd.Series, cfg: Optional[IGSConfig] = None) -> pd.DataFrame:
    cfg = cfg or IGSConfig()
    r = _returns_from_prices(price)
    if cfg.detrend:
        r = r - r.rolling(max(5, cfg.window // 10), min_periods=1).mean()
    n = len(r)
    out = {k: np.full(n, np.nan) for k in ["epr", "flux_index", "tra", "pe", "regime_score"]}
    if n == 0:
        return pd.DataFrame(out, index=r.index)

    r_values = r.to_numpy(dtype=float, copy=True)
    if n > 0 and (not np.isfinite(r_values[0])):
        first_price = price.iloc[0]
        if pd.notna(first_price) and first_price > 0:
            r_values[0] = 0.0

    quant_states = np.full(n, -1, dtype=int)
    pe_values = np.full(n, np.nan)
    last_invalid_positions = np.full(n, -1, dtype=int)
    seed_states = np.full(n, -1, dtype=int)

    def _fresh_quantizer() -> Quantizer:
        return _make_quantizer(cfg.quantize_mode, cfg.window, cfg.n_states)

    quantizer = _fresh_quantizer()
    pe_roll = RollingPermutationEntropy(cfg.window, cfg.perm_emb_dim, cfg.perm_tau)
    last_invalid_idx = -1
    seed_state_current: Optional[int] = None
    need_seed = False

    for idx, value in enumerate(r_values):
        price_curr = price.iloc[idx]
        price_prev = price.iloc[idx - 1] if idx > 0 else np.nan
        price_curr_pos = pd.notna(price_curr) and price_curr > 0
        price_prev_pos = pd.notna(price_prev) and price_prev > 0

        if not np.isfinite(value):
            if price_curr_pos and not price_prev_pos:
                seed_state_current = quantizer.update_and_state(0.0)
                seed_states[idx] = seed_state_current if seed_state_current is not None else -1
                last_invalid_positions[idx] = last_invalid_idx
                need_seed = False
                continue
            quantizer = _fresh_quantizer()
            pe_roll.reset()
            last_invalid_idx = idx
            last_invalid_positions[idx] = last_invalid_idx
            seed_states[idx] = -1
            seed_state_current = None
            need_seed = True
            continue

        if need_seed:
            seed_state_current = quantizer.update_and_state(0.0)
            need_seed = False
        state = quantizer.update_and_state(float(value))
        quant_states[idx] = state
        seed_states[idx] = seed_state_current if seed_state_current is not None else -1
        last_invalid_positions[idx] = last_invalid_idx
        if idx == 0 and last_invalid_idx == -1:
            continue
        pe_values[idx] = pe_roll.update(float(value))

    for t in range(n):
        start = max(0, t - cfg.window + 1)
        last_invalid = last_invalid_positions[t]
        if last_invalid >= 0:
            start = max(start, last_invalid + 1)
        if start > t:
            continue
        window_returns = r_values[start : t + 1]
        window_states = quant_states[start : t + 1]
        valid = np.isfinite(window_returns) & (window_states >= 0)
        valid_count = int(np.count_nonzero(valid))
        if valid_count == 0:
            continue
        rw = window_returns[valid]
        states = window_states[valid].astype(int)
        seed_state = seed_states[t]
        if seed_state >= 0 and last_invalid >= 0 and start == last_invalid + 1 and states.size >= 1:
            states = np.concatenate(([seed_state], states))
        if states.size < 2:
            continue
        transitions_count = states.size - 1
        if transitions_count < cfg.min_counts:
            continue
        P, pi = _transition_matrix(states, cfg.n_states, cfg.eps, cfg.pi_method)
        epr, J = _entropy_production(P, pi, cfg.eps)
        flux_idx = _net_flux_index(J, cfg.normalize_flux)
        tra = _time_reversal_asymmetry_arr(rw)
        pe = pe_values[t]
        epr_c = math.log1p(epr)
        flux_mag = abs(flux_idx)
        pe_inv = 1.0 - pe
        regime = _weighted_regime_score((epr_c, flux_mag, pe_inv), cfg.regime_weights)
        regime = float(np.clip(regime, 0.0, 1.0)) if np.isfinite(regime) else float("nan")
        out["epr"][t] = epr
        out["flux_index"][t] = flux_idx
        out["tra"][t] = tra
        out["pe"][t] = pe
        out["regime_score"][t] = regime
    return pd.DataFrame(out, index=r.index)


def igs_directional_signal(
    features: pd.DataFrame,
    epr_q: Optional[float] = None,
    flux_min: Optional[float] = None,
    cfg: Optional[IGSConfig] = None,
) -> pd.Series:
    """Build a directional long/short signal from pre-computed IGS features.

    Parameters
    ----------
    features:
        DataFrame returned by :func:`compute_igs_features` containing at least
        ``epr`` and ``flux_index`` columns.
    epr_q:
        Optional override for the quantile applied to the entropy production
        rate.  May be passed positionally for backwards compatibility.
        If omitted the value from ``cfg`` is used.
    flux_min:
        Optional override for the minimum absolute flux required to emit a
        signal.  May be passed positionally for backwards compatibility.
        If omitted the value from ``cfg`` is used.
    cfg:
        Configuration whose :class:`IGSConfig.signal_epr_q` and
        :class:`IGSConfig.signal_flux_min` provide the default thresholds.
        When ``None`` the defaults from :class:`IGSConfig` are used.
    """

    if isinstance(epr_q, IGSConfig) and cfg is None and flux_min is None:
        cfg = epr_q
        epr_q = None

    if isinstance(flux_min, IGSConfig) and cfg is None:
        cfg = flux_min
        flux_min = None

    cfg = cfg or IGSConfig()
    f = features
    s = pd.Series(0, index=f.index, dtype=int)
    valid = f["epr"].notna() & f["flux_index"].notna()
    if valid.any():
        epr_quantile = cfg.signal_epr_q if epr_q is None else epr_q
        flux_threshold = cfg.signal_flux_min if flux_min is None else flux_min
        thr = f.loc[valid, "epr"].quantile(epr_quantile)
        pos = valid & (f["epr"] >= thr) & (f["flux_index"] > +flux_threshold)
        neg = valid & (f["epr"] >= thr) & (f["flux_index"] < -flux_threshold)
        s[pos] = 1
        s[neg] = -1
    return s


def _entropy_signature(P: np.ndarray) -> float:
    K = P.shape[0]
    row_entropy = -np.sum(P * np.log(P + 1e-12), axis=1)
    return float(np.mean(row_entropy) / (math.log(K) + 1e-12))


class _KAdaptController:
    def __init__(
        self,
        cfg: IGSConfig,
        external_measure: Optional[Callable[[np.ndarray], float]] = None,
    ):
        self.cfg = cfg
        self.external_measure = external_measure
        self.prev_sig: Optional[float] = None
        self.persist_up = 0
        self.persist_dn = 0
        self.cooldown = 0

    def reset(self) -> None:
        self.prev_sig = None
        self.persist_up = 0
        self.persist_dn = 0
        self.cooldown = 0

    def maybe_update(self, K: int, P: np.ndarray) -> int:
        if self.cfg.adapt_method == "off":
            return K
        if self.cooldown > 0:
            self.cooldown -= 1
            return K
        if self.cfg.adapt_method == "entropy":
            sig = _entropy_signature(P)
        elif self.cfg.adapt_method == "external" and self.external_measure is not None:
            sig = float(self.external_measure(P))
        else:
            return K
        if self.prev_sig is None:
            self.prev_sig = sig
            return K
        delta = sig - self.prev_sig
        self.prev_sig = sig
        if delta > self.cfg.adapt_threshold:
            self.persist_up += 1
            self.persist_dn = 0
        elif delta < -self.cfg.adapt_threshold:
            self.persist_dn += 1
            self.persist_up = 0
        else:
            self.persist_up = max(0, self.persist_up - 1)
            self.persist_dn = max(0, self.persist_dn - 1)
            return K
        if self.persist_up >= self.cfg.adapt_persist and K < self.cfg.k_max:
            self.persist_up = 0
            self.cooldown = self.cfg.adapt_cooldown
            return min(self.cfg.k_max, K + self.cfg.adapt_step)
        if self.persist_dn >= self.cfg.adapt_persist and K > self.cfg.k_min:
            self.persist_dn = 0
            self.cooldown = self.cfg.adapt_cooldown
            return max(self.cfg.k_min, K - self.cfg.adapt_step)
        return K


class _MetricsEmitter:
    def __init__(self, prometheus_enabled: bool, prometheus_async: bool, label: str):
        gauge_factory = (
            getattr(prometheus_client, "Gauge", None) if prometheus_client is not None else None
        )
        self.enabled = bool(prometheus_enabled and gauge_factory is not None)
        self.async_enabled = bool(prometheus_async and self.enabled)
        self.label = label
        if not self.enabled:
            self.g_epr = self.g_flux = self.g_regime = self.g_k = None
            self.q = None
            return

        self.g_epr = gauge_factory("igs_epr", "IGS EPR", ["instrument"])
        self.g_flux = gauge_factory("igs_flux_index", "IGS Flux Index", ["instrument"])
        self.g_regime = gauge_factory("igs_regime_score", "IGS Regime Score", ["instrument"])
        self.g_k = gauge_factory("igs_states_k", "IGS number of states K", ["instrument"])
        self.q: Optional["queue.Queue[Tuple[str, float]]"] = None

        if self.async_enabled:
            self.q = queue.Queue(maxsize=10000)
            t = threading.Thread(target=self._worker, daemon=True)
            t.start()
            self.q.put(("k", float("nan")))
        else:
            self._set_gauge("k", float("nan"))

    def _set_gauge(self, name: str, value: float) -> None:
        try:
            if name == "epr":
                self.g_epr.labels(self.label).set(value)
            elif name == "flux":
                self.g_flux.labels(self.label).set(value)
            elif name == "regime":
                self.g_regime.labels(self.label).set(value)
            elif name == "k":
                self.g_k.labels(self.label).set(value)
        except Exception:
            pass

    def _worker(self) -> None:
        while True:
            if self.q is None:
                break
            try:
                name, value = self.q.get()
                self._set_gauge(name, value)
            except Exception:
                pass

    def emit(self, epr: float, flux: float, regime: float, K: int) -> None:
        if not self.enabled:
            return

        items = [
            ("epr", float(epr)),
            ("flux", float(flux)),
            ("regime", float(regime)),
            ("k", float(K)),
        ]

        if self.async_enabled and self.q is not None:
            for item in items:
                try:
                    self.q.put_nowait(item)
                except queue.Full:
                    break
        else:
            for name, value in items:
                self._set_gauge(name, value)


class StreamingIGS:
    """
    Streaming IGS engine.
    update(timestamp, price) -> IGSMetrics | None
    """

    def __init__(
        self,
        cfg: Optional[IGSConfig] = None,
        external_adaptation_measure: Optional[Callable[[np.ndarray], float]] = None,
    ):
        self.cfg = cfg or IGSConfig()
        self.K = int(self.cfg.n_states)
        self.returns: Deque[float] = deque(maxlen=self.cfg.window)
        self.states: Deque[int] = deque(maxlen=self.cfg.window)
        self.T = np.zeros((self.K, self.K), dtype=float)
        self.row_sums = np.zeros(self.K, dtype=float)
        self.prev_state: Optional[int] = None
        self.last_price: Optional[float] = None
        self.last_timestamp: Optional[pd.Timestamp] = None
        self.tra_roll = RollingTRA(self.cfg.window)
        self.pe_roll = RollingPermutationEntropy(
            self.cfg.window, self.cfg.perm_emb_dim, self.cfg.perm_tau
        )
        self.quant = self._build_quantizer(self.K)
        self.k_adapt = _KAdaptController(self.cfg, external_measure=external_adaptation_measure)
        label = self.cfg.instrument_label or "unknown"
        self.metrics = _MetricsEmitter(
            self.cfg.prometheus_enabled, self.cfg.prometheus_async, label
        )

    def _build_quantizer(self, n_states: int) -> Quantizer:
        return _make_quantizer(self.cfg.quantize_mode, self.cfg.window, n_states)

    def _rebuild_counters_after_K_change(self):
        arr = list(self.returns)
        self.quant = self._build_quantizer(self.K)
        self.states = deque(maxlen=self.cfg.window)
        self.T = np.zeros((self.K, self.K), dtype=float)
        self.row_sums = np.zeros(self.K, dtype=float)
        self.prev_state = None
        if not arr:
            return
        prev_state: Optional[int] = None
        for value in arr:
            if not np.isfinite(value):
                self.states.append(-1)
                prev_state = None
                continue
            state = self.quant.update_and_state(float(value))
            self.states.append(state)
            if prev_state is not None:
                self.T[prev_state, state] += 1.0
                self.row_sums[prev_state] += 1.0
            prev_state = state
        self.prev_state = prev_state if (prev_state is not None and prev_state >= 0) else None

    def _handle_price_gap(self) -> None:
        self.last_price = None
        self.last_timestamp = None
        self.prev_state = None
        self.returns.clear()
        self.states.clear()
        self.T.fill(0.0)
        self.row_sums.fill(0.0)
        self.tra_roll.reset()
        self.pe_roll.reset()
        self.quant = self._build_quantizer(self.K)
        self.k_adapt.reset()

    def update(self, timestamp: pd.Timestamp, price: float) -> Optional[IGSMetrics]:
        if self.last_timestamp is not None:
            try:
                is_non_monotonic = timestamp <= self.last_timestamp
            except TypeError:
                logger.warning(
                    "StreamingIGS received timezone-mismatched timestamps %s and %s; resetting state",
                    timestamp,
                    self.last_timestamp,
                )
                self._handle_price_gap()
                return None
            if is_non_monotonic:
                logger.warning(
                    "StreamingIGS received non-monotonic timestamp %s <= %s; resetting state",
                    timestamp,
                    self.last_timestamp,
                )
                self._handle_price_gap()
                return None
        if price is None or not (price > 0):
            self._handle_price_gap()
            return None
        t0 = time.perf_counter()
        if self.last_price is None:
            self.last_price = float(price)
            self.last_timestamp = timestamp
            self.returns.append(0.0)
            s0 = self.quant.update_and_state(0.0)
            self.states.append(s0)
            self.prev_state = s0
            return None
        ret = math.log(float(price)) - math.log(self.last_price)
        self.last_price = float(price)
        self.last_timestamp = timestamp
        if len(self.returns) == self.returns.maxlen and len(self.states) >= 2:
            old_prev = self.states[0]
            old_state = self.states[1]
            if old_prev >= 0 and old_state >= 0:
                self.T[old_prev, old_state] = max(0.0, self.T[old_prev, old_state] - 1.0)
                self.row_sums[old_prev] = max(0.0, self.row_sums[old_prev] - 1.0)
        tra = self.tra_roll.update(ret)
        self.returns.append(ret)
        new_state = self.quant.update_and_state(ret)
        if self.prev_state is not None:
            self.T[self.prev_state, new_state] += 1.0
            self.row_sums[self.prev_state] += 1.0
        self.states.append(new_state)
        self.prev_state = new_state
        pe_val = self.pe_roll.update(ret)
        if int(np.sum(self.row_sums)) < self.cfg.min_counts:
            return None
        P = np.zeros_like(self.T)
        for i in range(self.K):
            denom = self.row_sums[i] + self.K * self.cfg.eps
            P[i, :] = (self.T[i, :] + self.cfg.eps) / denom if denom > 0 else (1.0 / self.K)
        if self.cfg.pi_method == "stationary":
            pi = _stationary_distribution(P, self.cfg.eps)
        else:
            pi = self.row_sums.copy()
            s = float(pi.sum())
            pi = pi / (s + self.cfg.eps) if s >= self.cfg.eps else np.full(self.K, 1.0 / self.K)
        epr, J = _entropy_production(P, pi, self.cfg.eps)
        flux_index = _net_flux_index(J, self.cfg.normalize_flux)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        degrade = (self.cfg.max_update_ms > 0.0) and (elapsed_ms > self.cfg.max_update_ms)
        pe = float("nan") if degrade else pe_val
        epr_c = math.log1p(epr)
        flux_mag = abs(flux_index)
        pe_inv = 1.0 - pe
        regime_score = _weighted_regime_score((epr_c, flux_mag, pe_inv), self.cfg.regime_weights)
        regime_score = (
            float(np.clip(regime_score, 0.0, 1.0)) if np.isfinite(regime_score) else float("nan")
        )
        regime_name = _classify_regime_simple(epr, flux_index, pe)
        self.metrics.emit(epr, flux_index, regime_score, self.K)
        if not degrade:
            new_K = self.k_adapt.maybe_update(self.K, P)
            if new_K != self.K:
                self.K = new_K
                self._rebuild_counters_after_K_change()
        return IGSMetrics(
            timestamp=timestamp,
            epr=epr,
            flux_index=flux_index,
            tra=tra,
            pe=pe,
            regime_score=regime_score,
            regime=regime_name,
            n_states_used=self.K,
        )


def _classify_regime_simple(epr: float, flux: float, pe: float) -> str:
    try:
        if epr < 1e-3 and (not np.isnan(pe) and pe > 0.7):
            return "reversible"
        if abs(flux) > 0.3 and epr > 1e-2:
            return "directional"
        if epr > 0.1:
            return "turbulent"
    except Exception:
        pass
    return "mixed"


__all__ = [
    "IGSConfig",
    "IGSMetrics",
    "compute_igs_features",
    "igs_directional_signal",
    "StreamingIGS",
    "RollingTRA",
    "RollingPermutationEntropy",
    "ZScoreQuantizer",
    "RollingRankQuantizer",
    "SlidingRankQuantizer",
    "Quantizer",
]
