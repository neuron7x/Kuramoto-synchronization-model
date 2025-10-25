"""Lightweight indicator helpers powering portfolio strategies."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Literal

import numpy as np

from .hurst import hurst_exponent
from .kuramoto import compute_phase


def _as_float_array(values: Iterable[float]) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.ndim != 1:
        raise ValueError("Input series must be one-dimensional")
    return array


def _fill_missing(series: np.ndarray) -> np.ndarray:
    if series.size == 0:
        return series
    mask = np.isfinite(series)
    if not mask.any():
        return np.zeros_like(series)
    if mask.all():
        return series
    idx = np.flatnonzero(mask)
    filled = np.interp(np.arange(series.size), idx, series[mask])
    return filled


def _rolling_sum(values: np.ndarray, window: int) -> np.ndarray:
    if window <= 0:
        raise ValueError("window must be positive")
    if values.size == 0:
        return np.empty(0, dtype=values.dtype)
    cumulative = np.cumsum(values)
    padded = np.empty(values.size + 1, dtype=values.dtype)
    padded[0] = values.dtype.type(0)
    padded[1:] = cumulative
    indices = np.arange(values.size)
    start = np.maximum(indices - window + 1, 0)
    return padded[indices + 1] - padded[start]


class _HurstBufferPool:
    """Reuse temporary buffers required by the Hurst exponent kernel."""

    __slots__ = ("_scratch", "_tau")

    def __init__(self) -> None:
        self._scratch: np.ndarray | None = None
        self._tau: np.ndarray | None = None

    def scratch(self, size: int) -> np.ndarray:
        if size <= 0:
            return np.empty(0, dtype=float)
        scratch = self._scratch
        if scratch is None or scratch.size < size:
            scratch = np.empty(size, dtype=float)
            self._scratch = scratch
        return scratch

    def tau(self, size: int) -> np.ndarray:
        if size <= 0:
            return np.empty(0, dtype=float)
        tau = self._tau
        if tau is None or tau.size != size:
            tau = np.empty(size, dtype=float)
            self._tau = tau
        return tau


@dataclass(slots=True)
class KuramotoIndicator:
    """Compute rolling Kuramoto-style synchronisation scores."""

    window: int = 200
    coupling: float = 1.0

    def __post_init__(self) -> None:
        if self.window <= 0:
            raise ValueError("window must be positive")
        if self.coupling <= 0:
            raise ValueError("coupling must be positive")

    def compute(self, prices: Iterable[float]) -> np.ndarray:
        raw = _as_float_array(prices)
        if raw.size == 0:
            return np.empty(0, dtype=float)
        if not np.isfinite(raw).any():
            return np.zeros_like(raw, dtype=float)
        series = _fill_missing(raw)
        phases = compute_phase(series)
        complex_phase = np.exp(1j * phases)
        totals = _rolling_sum(complex_phase, self.window)
        counts = np.minimum(np.arange(1, series.size + 1), self.window)
        min_samples = min(self.window, 10)
        mask = counts >= min_samples
        result = np.zeros_like(series, dtype=float)
        if mask.any():
            order = np.abs(totals[mask]) / counts[mask]
            result[mask] = np.clip(self.coupling * order, 0.0, 1.0)
        return result


@dataclass(slots=True)
class HurstIndicator:
    """Rolling Hurst exponent estimator."""

    window: int = 100
    min_lag: int = 2
    max_lag: int | None = None
    backend: Literal["cpu", "auto", "numpy", "numba", "cuda", "gpu"] = "auto"
    _buffers: _HurstBufferPool = field(
        init=False, repr=False, default_factory=_HurstBufferPool
    )

    def __post_init__(self) -> None:
        if self.window <= 0:
            raise ValueError("window must be positive")
        if self.min_lag <= 0:
            raise ValueError("min_lag must be positive")
        if self.max_lag is not None and self.max_lag <= self.min_lag:
            raise ValueError("max_lag must exceed min_lag")
        supported = {"cpu", "auto", "numpy", "numba", "cuda", "gpu"}
        if self.backend not in supported:
            raise ValueError(f"Unsupported backend '{self.backend}'")

    def compute(self, prices: Iterable[float]) -> np.ndarray:
        series = _as_float_array(prices)
        if series.size == 0:
            return np.empty(0, dtype=float)
        series = _fill_missing(series)
        result = np.full(series.size, 0.5, dtype=float)
        buffer_pool = self._buffers
        for idx in range(series.size):
            start = max(0, idx - self.window + 1)
            window_slice = series[start : idx + 1]
            available = window_slice.size // 2
            if available <= self.min_lag:
                continue
            max_lag = available
            if self.max_lag is not None:
                max_lag = min(max_lag, self.max_lag)
            scratch = buffer_pool.scratch(window_slice.size)
            tau = buffer_pool.tau(max_lag - self.min_lag + 1)
            value = hurst_exponent(
                window_slice,
                min_lag=self.min_lag,
                max_lag=max_lag,
                scratch=scratch,
                tau_buffer=tau,
                backend=self.backend,
            )
            result[idx] = float(np.clip(value, 0.0, 1.0))
        return result


@dataclass(slots=True)
class VPINIndicator:
    """Volume-synchronised probability of informed trading."""

    bucket_size: int = 50
    threshold: float = 0.8

    def __post_init__(self) -> None:
        if self.bucket_size <= 0:
            raise ValueError("bucket_size must be positive")
        if self.threshold <= 0:
            raise ValueError("threshold must be positive")

    def compute(self, volume_data: Iterable[Iterable[float]]) -> np.ndarray:
        array = np.asarray(volume_data, dtype=float)
        if array.size == 0:
            return np.empty(0, dtype=float)
        if array.ndim != 2 or array.shape[1] < 3:
            raise ValueError(
                "volume_data must have columns [volume, buy_volume, sell_volume]"
            )
        total = np.clip(
            np.nan_to_num(array[:, 0], nan=0.0, posinf=0.0, neginf=0.0), 0.0, None
        )
        buy = np.clip(
            np.nan_to_num(array[:, 1], nan=0.0, posinf=0.0, neginf=0.0), 0.0, None
        )
        sell = np.clip(
            np.nan_to_num(array[:, 2], nan=0.0, posinf=0.0, neginf=0.0), 0.0, None
        )
        imbalance = np.abs(buy - sell)
        total_sums = _rolling_sum(total, self.bucket_size)
        imb_sums = _rolling_sum(imbalance, self.bucket_size)
        result = np.zeros(total.size, dtype=float)
        valid = total_sums > 0.0
        if np.any(valid):
            ratios = imb_sums[valid] / total_sums[valid]
            result[valid] = np.clip(ratios, 0.0, 1.0)
        return result
