"""
Irreversibility-Gated Signal (IGS) — Hybrid Core
================================================
Features:
- Entropy Production Rate (EPR) on K-state Markov discretization of log-returns
- Probability flux tensor J and scalar FluxIndex in [-1, 1]
- Time-Reversal Asymmetry (TRA, third order) with exact O(1) rolling update
- Permutation Entropy (PE) with incremental multiset maintenance after warmup
- Composite regime_score = mean(log1p(EPR), |FluxIndex|, 1 - PE)

Streaming:
- O(1) updates for transition counts
- O(1) quantization via ZScoreQuantizer with rolling mean/std and normal quantiles
- O(log W) sliding rank quantizer with online order statistics
- Hysteretic K-adaptation with cooldown; O(W) rebuild only on change
- Asynchronous Prometheus emission (optional)
- Overload guard via max_update_ms for latency-aware degradation

Dependencies: numpy, pandas. Optional: prometheus_client.
"""

from __future__ import annotations
from dataclasses import dataclass
from collections import deque
from typing import Optional, Tuple, Deque, Dict, Any, Callable, List
import math
import logging
import threading
import queue
import time
from bisect import bisect_left, bisect_right
import numpy as np
import pandas as pd

try:
    from prometheus_client import Gauge  # type: ignore
except Exception:
    Gauge = None

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
    k_min: int = 5
    k_max: int = 15
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


def _ndtri(p: float) -> float:
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02, 1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02, 6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00, -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00]
    plow = 0.02425
    phigh = 1 - plow
    if p <= 0 or p >= 1:
        return float("nan")
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q + c[1])*q + c[2])*q + c[3])*q + c[4])*q + c[5]) / ((((d[0]*q + d[1])*q + d[2])*q + d[3])*q + 1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q + c[1])*q + c[2])*q + c[3])*q + c[4])*q + c[5]) / ((((d[0]*q + d[1])*q + d[2])*q + d[3])*q + 1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r + a[1])*r + a[2])*r + a[3])*r + a[4])*r + a[5]) * q / (((((b[0]*r + b[1])*r + b[2])*r + b[3])*r + b[4])*r + 1)


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
            self.sum_xy -= (old_cur ** 2) * old_prev
            self.sum_yx -= (old_prev ** 2) * old_cur
            self.n_pairs = max(0, self.n_pairs - 1)
            self.buf.popleft()
        if len(self.buf) >= 1:
            r_prev = self.buf[-1]
            self.sum_xy += (r_t ** 2) * r_prev
            self.sum_yx += (r_prev ** 2) * r_t
            self.n_pairs += 1
        self.buf.append(r_t)
        if self.n_pairs == 0:
            return float("nan")
        return (self.sum_xy / self.n_pairs) - (self.sum_yx / self.n_pairs)


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
        seq = arr[start: start + self.m * self.tau: self.tau]
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

    def _evict_oldest(self):
        if len(self.buf) < self.W:
            return
        old = self.buf.popleft()
        idx = bisect_left(self.sorted, old)
        if idx < len(self.sorted) and self.sorted[idx] == old:
            self.sorted.pop(idx)

    def _insert(self, x: float) -> None:
        ident = self._counter
        self._counter += 1
        item = (x, ident)
        idx = bisect_left(self.sorted, item)
        self.sorted.insert(idx, item)
        self.buf.append(item)

    def _state_from_value(self, x: float) -> int:
        n = len(self.sorted)
        if n == 0:
            return 0
        lo = bisect_left(self.sorted, (x, -math.inf))
        hi = bisect_right(self.sorted, (x, math.inf))
        avg_rank = ((lo + 1) + hi) / 2.0
        pct = avg_rank / n
        pct = min(max(pct, 0.0), 1.0)
        state = int(pct * self.K)
        if state >= self.K:
            state = self.K - 1
        return state

    def update_and_state(self, x: float) -> int:
        if len(self.buf) == self.W:
            self._evict_oldest()
        self._insert(x)
        return self._state_from_value(x)

    def state_for_value(self, x: float) -> int:
        return self._state_from_value(x)


def _make_quantizer(mode: str, window: int, n_states: int):
    normalized = mode.lower()
    if normalized == "zscore":
        return ZScoreQuantizer(window, n_states)
    if normalized == "rank":
        return RollingRankQuantizer(window, n_states)
    raise ValueError(f"Unsupported quantize_mode: {mode}")


def _returns_from_prices(price: pd.Series) -> pd.Series:
    if not isinstance(price, pd.Series):
        raise TypeError("price must be a pandas Series")
    price = price.where(price > 0, np.nan)
    return np.log(price).diff()
def _transition_matrix(states: np.ndarray, n_states: int, eps: float):
    T = np.zeros((n_states, n_states), dtype=float)
    for a, b in zip(states[:-1], states[1:]):
        T[a, b] += 1.0
    counts_out = T.sum(axis=1, keepdims=True)
    P = (T + eps) / (counts_out + n_states * eps)
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
    weight = (idxs[None, :] - idxs[:, None])
    upper = np.triu_indices(n, k=1)
    num = float(np.sum(J[upper] * weight[upper]))
    den = float(np.sum(np.abs(J[upper] * weight[upper])) + 1e-12)
    x = num / den
    return float(np.clip(x, -1.0, 1.0)) if normalize else num


def _time_reversal_asymmetry_arr(r: np.ndarray) -> float:
    if len(r) < 3:
        return float("nan")
    a = float(np.mean(r[1:]**2 * r[:-1]))
    b = float(np.mean(r[:-1]**2 * r[1:]))
    return a - b


def _permutation_entropy_arr(x: np.ndarray, dim: int, tau: int, eps: float) -> float:
    n = len(x) - (dim - 1) * tau
    if dim < 3 or n <= 1:
        return float("nan")
    counts: Dict[Tuple[int, ...], int] = {}
    for i in range(n):
        window = x[i: i + dim * tau: tau]
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
    r_values = r.to_numpy()

    quant_states = np.full(n, -1, dtype=int)
    quant = _make_quantizer(cfg.quantize_mode, cfg.window, cfg.n_states)
    for idx, value in enumerate(r_values):
        if not np.isfinite(value):
            continue
        quant_states[idx] = quant.update_and_state(float(value))

    for t in range(cfg.window, n):
        start = t - cfg.window
        window_returns = r_values[start:t]
        window_states = quant_states[start:t]
        valid = np.isfinite(window_returns) & (window_states >= 0)
        if np.count_nonzero(valid) < cfg.min_counts:
            continue
        rw = window_returns[valid]
        states = window_states[valid].astype(int)
        if states.size < 2:
            continue
        P, pi = _transition_matrix(states, cfg.n_states, cfg.eps)
        epr, J = _entropy_production(P, pi, cfg.eps)
        flux_idx = _net_flux_index(J, cfg.normalize_flux)
        tra = _time_reversal_asymmetry_arr(rw)
        pe = _permutation_entropy_arr(rw, cfg.perm_emb_dim, cfg.perm_tau, cfg.eps)
        epr_c = math.log1p(epr)
        flux_mag = abs(flux_idx)
        pe_inv = 1.0 - pe if not np.isnan(pe) else np.nan
        regime = float(np.nanmean([epr_c, flux_mag, pe_inv]))
        regime = float(np.clip(regime, 0.0, 1.0))
        out["epr"][t] = epr
        out["flux_index"][t] = flux_idx
        out["tra"][t] = tra
        out["pe"][t] = pe
        out["regime_score"][t] = regime
    return pd.DataFrame(out, index=r.index)


def igs_directional_signal(features: pd.DataFrame, epr_q: float = 0.7, flux_min: float = 0.0) -> pd.Series:
    f = features
    s = pd.Series(0, index=f.index, dtype=int)
    valid = f["epr"].notna() & f["flux_index"].notna()
    if valid.any():
        thr = f.loc[valid, "epr"].quantile(epr_q)
        pos = valid & (f["epr"] >= thr) & (f["flux_index"] > +flux_min)
        neg = valid & (f["epr"] >= thr) & (f["flux_index"] < -flux_min)
        s[pos] = 1
        s[neg] = -1
    return s


def _entropy_signature(P: np.ndarray) -> float:
    K = P.shape[0]
    row_entropy = -np.sum(P * np.log(P + 1e-12), axis=1)
    return float(np.mean(row_entropy) / (math.log(K) + 1e-12))


class _KAdaptController:
    def __init__(self, cfg: IGSConfig, external_measure: Optional[Callable[[np.ndarray], float]] = None):
        self.cfg = cfg
        self.external_measure = external_measure
        self.prev_sig: Optional[float] = None
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


class _AsyncMetrics:
    def __init__(self, enabled: bool, label: str):
        self.enabled = enabled and (Gauge is not None)
        if not self.enabled:
            self.g_epr = self.g_flux = self.g_regime = self.g_k = None
            self.q = None
            return
        self.g_epr = Gauge("igs_epr", "IGS EPR", ["instrument"])
        self.g_flux = Gauge("igs_flux_index", "IGS Flux Index", ["instrument"])
        self.g_regime = Gauge("igs_regime_score", "IGS Regime Score", ["instrument"])
        self.g_k = Gauge("igs_states_k", "IGS number of states K", ["instrument"])
        self.q: "queue.Queue[Tuple[str, float]]" = queue.Queue(maxsize=10000)
        self.label = label
        t = threading.Thread(target=self._worker, daemon=True)
        t.start()
        self.q.put(("k", float("nan")))

    def _worker(self):
        while True:
            try:
                name, value = self.q.get()
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

    def emit(self, epr: float, flux: float, regime: float, K: int):
        if not self.enabled:
            return
        for item in [("epr", float(epr)), ("flux", float(flux)), ("regime", float(regime)), ("k", float(K))]:
            try:
                self.q.put_nowait(item)
            except queue.Full:
                break


class StreamingIGS:
    """
    Streaming IGS engine.
    update(timestamp, price) -> IGSMetrics | None
    """
    def __init__(self, cfg: Optional[IGSConfig] = None, external_adaptation_measure: Optional[Callable[[np.ndarray], float]] = None):
        self.cfg = cfg or IGSConfig()
        self.K = int(self.cfg.n_states)
        self.returns: Deque[float] = deque(maxlen=self.cfg.window)
        self.states: Deque[int] = deque(maxlen=self.cfg.window)
        self.T = np.zeros((self.K, self.K), dtype=float)
        self.row_sums = np.zeros(self.K, dtype=float)
        self.prev_state: Optional[int] = None
        self.last_price: Optional[float] = None
        self.tra_roll = RollingTRA(self.cfg.window)
        self.pe_roll = RollingPermutationEntropy(self.cfg.window, self.cfg.perm_emb_dim, self.cfg.perm_tau)
        self.quant = _make_quantizer(self.cfg.quantize_mode, self.cfg.window, self.K)
        self.k_adapt = _KAdaptController(self.cfg, external_measure=external_adaptation_measure)
        label = self.cfg.instrument_label or "unknown"
        self.metrics_async = _AsyncMetrics(self.cfg.prometheus_enabled and self.cfg.prometheus_async, label)

    def _rebuild_counters_after_K_change(self):
        K = self.K
        arr = list(self.returns)
        self.quant = _make_quantizer(self.cfg.quantize_mode, self.cfg.window, K)
        if not arr:
            self.states = deque(maxlen=self.cfg.window)
            self.T = np.zeros((K, K), dtype=float)
            self.row_sums = np.zeros(K, dtype=float)
            self.prev_state = None
            return
        new_states: List[int] = []
        for value in arr:
            if np.isfinite(value):
                new_states.append(self.quant.update_and_state(float(value)))
            else:
                new_states.append(-1)
        self.states = deque(new_states, maxlen=self.cfg.window)
        self.T = np.zeros((K, K), dtype=float)
        self.row_sums = np.zeros(K, dtype=float)
        for a, b in zip(new_states[:-1], new_states[1:]):
            if a >= 0 and b >= 0:
                self.T[a, b] += 1.0
                self.row_sums[a] += 1.0
        last_state = self.states[-1] if len(self.states) else None
        self.prev_state = last_state if (last_state is not None and last_state >= 0) else None

    def update(self, timestamp: pd.Timestamp, price: float) -> Optional[IGSMetrics]:
        if price is None or not (price > 0):
            return None
        t0 = time.perf_counter()
        if self.last_price is None:
            self.last_price = float(price)
            self.returns.append(0.0)
            s0 = self.quant.update_and_state(0.0)
            self.states.append(s0)
            self.prev_state = s0
            return None
        ret = math.log(float(price)) - math.log(self.last_price)
        self.last_price = float(price)
        if len(self.returns) == self.returns.maxlen and len(self.states) >= 2:
            old_prev = self.states[0]
            old_state = self.states[1]
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
        if int(np.sum(self.row_sums)) < self.cfg.min_counts:
            return None
        P = np.zeros_like(self.T)
        for i in range(self.K):
            denom = self.row_sums[i] + self.K * self.cfg.eps
            P[i, :] = (self.T[i, :] + self.cfg.eps) / denom if denom > 0 else (1.0 / self.K)
        pi = self.row_sums.copy()
        s = float(pi.sum())
        pi = pi / (s + self.cfg.eps) if s >= self.cfg.eps else np.full(self.K, 1.0 / self.K)
        epr, J = _entropy_production(P, pi, self.cfg.eps)
        flux_index = _net_flux_index(J, self.cfg.normalize_flux)
        pe_val = self.pe_roll.update(ret)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        degrade = (self.cfg.max_update_ms > 0.0) and (elapsed_ms > self.cfg.max_update_ms)
        pe = float("nan") if degrade else pe_val
        epr_c = math.log1p(epr)
        flux_mag = abs(flux_index)
        pe_inv = 1.0 - pe if not np.isnan(pe) else 0.0
        regime_score = float(np.mean([epr_c, flux_mag, pe_inv]))
        regime_score = float(np.clip(regime_score, 0.0, 1.0))
        regime_name = _classify_regime_simple(epr, flux_index, pe)
        self.metrics_async.emit(epr, flux_index, regime_score, self.K)
        if not degrade:
            K_before = self.K
            self.K = self.k_adapt.maybe_update(self.K, P)
            if self.K != K_before:
                self._rebuild_counters_after_K_change()
        return IGSMetrics(timestamp=timestamp, epr=epr, flux_index=flux_index, tra=tra, pe=pe, regime_score=regime_score, regime=regime_name, n_states_used=self.K)


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
]
