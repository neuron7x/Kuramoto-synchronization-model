"""Lightweight indicator helpers powering portfolio strategies."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Literal

import numpy as np

from ..utils.logging import get_logger
from ..utils.metrics import get_metrics_collector
from .hurst import hurst_exponent
from .kuramoto import compute_phase

try:  # pragma: no cover - optional GPU dependency
    import cupy as cp
except Exception:  # pragma: no cover - executed on CPU-only environments
    cp = None

try:  # pragma: no cover - optional acceleration
    from numba import cuda, njit, prange
except Exception:  # pragma: no cover - executed when numba missing
    cuda = None
    njit = None
    prange = range


_GPU_ROLLING_THRESHOLD = 32_768
_CUDA_FLOAT_DTYPES = {np.dtype(np.float32), np.dtype(np.float64)}

_logger = get_logger(__name__)
_metrics = get_metrics_collector()


_WEIGHTING_MODES = {"none", "linear", "sqrt", "log"}


def _prepare_weight_series(
    values: Iterable[float], *, expected_size: int, mode: str
) -> np.ndarray:
    series = np.array(values, dtype=float, copy=True)
    if series.ndim != 1:
        raise ValueError("volumes must be one-dimensional")
    if series.size != expected_size:
        raise ValueError("volumes length must match prices length")

    series = np.nan_to_num(series, nan=0.0, posinf=0.0, neginf=0.0)
    np.clip(series, 0.0, None, out=series)

    if mode == "sqrt":
        np.sqrt(series, out=series, where=series >= 0.0)
    elif mode == "log":
        np.log1p(series, out=series)
    elif mode != "linear":
        raise ValueError(f"Unsupported weighting mode '{mode}'")

    return series


def _apply_exponential_smoothing(
    values: np.ndarray, valid: np.ndarray, alpha: float
) -> np.ndarray:
    if not (0.0 < alpha < 1.0) or values.size == 0:
        return values

    smoothed = values.copy()
    state = 0.0
    has_state = False

    for idx in range(smoothed.size):
        if not valid[idx]:
            continue
        if not has_state:
            state = smoothed[idx]
            has_state = True
        else:
            state = alpha * smoothed[idx] + (1.0 - alpha) * state
        smoothed[idx] = state

    return smoothed


def _numba_available() -> bool:
    return njit is not None


def _cuda_available() -> bool:
    if cuda is None:
        return False
    try:  # pragma: no cover - hardware dependent
        return bool(cuda.is_available())
    except Exception:
        return False


if cuda is not None:  # pragma: no cover - compiled when CUDA present

    @cuda.jit
    def _rolling_sum_cuda_kernel(values, window, out):
        idx = cuda.grid(1)
        if idx >= values.size:
            return
        start = idx - window + 1
        if start < 0:
            start = 0
        acc = 0.0
        for j in range(start, idx + 1):
            acc += values[j]
        out[idx] = acc

else:  # pragma: no cover - executed without CUDA

    def _rolling_sum_cuda_kernel(*_: object) -> None:
        raise RuntimeError("CUDA backend unavailable")


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


def _rolling_sum(
    values: np.ndarray,
    window: int,
    *,
    backend: Literal["auto", "cpu", "gpu"] = "auto",
) -> np.ndarray:
    if window <= 0:
        raise ValueError("window must be positive")
    if values.size == 0:
        return np.empty(0, dtype=values.dtype)

    array = np.asarray(values)
    if array.ndim != 1:
        raise ValueError("values must be one-dimensional")

    use_cupy = False
    use_cuda = False
    if backend == "gpu":
        use_cupy = cp is not None
        use_cuda = not use_cupy and _cuda_available()
    elif backend == "auto":
        if cp is not None and array.size >= _GPU_ROLLING_THRESHOLD:
            use_cupy = True
        elif _cuda_available() and array.dtype in _CUDA_FLOAT_DTYPES:
            use_cuda = True

    if use_cupy:
        try:  # pragma: no cover - exercised only when CuPy available
            device_values = cp.asarray(array)
            cumulative = cp.cumsum(device_values)
            padded = cp.empty(device_values.size + 1, dtype=device_values.dtype)
            padded[0] = device_values.dtype.type(0)
            padded[1:] = cumulative
            indices = cp.arange(device_values.size, dtype=cp.int64)
            start = cp.maximum(indices - window + 1, 0)
            result = padded[indices + 1] - padded[start]
            return cp.asnumpy(result)
        except Exception:
            use_cupy = False

    if use_cuda and array.dtype in _CUDA_FLOAT_DTYPES:
        try:  # pragma: no cover - requires CUDA runtime
            device_values = cuda.to_device(array.astype(array.dtype))
            device_out = cuda.device_array_like(device_values)
            threads = 256
            blocks = (array.size + threads - 1) // threads
            _rolling_sum_cuda_kernel[blocks, threads](
                device_values, int(window), device_out
            )
            cuda.synchronize()
            return device_out.copy_to_host()
        except Exception:
            use_cuda = False

    cumulative = np.cumsum(array)
    padded = np.empty(array.size + 1, dtype=array.dtype)
    padded[0] = array.dtype.type(0)
    padded[1:] = cumulative
    indices = np.arange(array.size)
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


if _numba_available():  # pragma: no cover - compiled at import time

    @njit(cache=True, fastmath=True)
    def _hurst_from_window(
        series: np.ndarray,
        start: int,
        stop: int,
        min_lag: int,
        max_lag_cap: int,
    ) -> float:
        length = stop - start
        if length <= min_lag * 2:
            return 0.5

        local_max_lag = max_lag_cap
        if local_max_lag <= 0 or local_max_lag > length // 2:
            local_max_lag = length // 2
        if local_max_lag <= min_lag:
            return 0.5

        lag_count = local_max_lag - min_lag + 1
        sum_x = 0.0
        sum_y = 0.0
        sum_xx = 0.0
        sum_xy = 0.0
        count = 0

        for offset in range(lag_count):
            lag = min_lag + offset
            sample_count = length - lag
            if sample_count <= 0:
                continue
            acc = 0.0
            acc_sq = 0.0
            for idx in range(sample_count):
                diff = series[start + idx + lag] - series[start + idx]
                acc += diff
                acc_sq += diff * diff
            inv = 1.0 / sample_count
            mean = acc * inv
            variance = acc_sq * inv - mean * mean
            if variance <= 0.0:
                continue
            tau = np.sqrt(variance)
            x = np.log(lag)
            y = np.log(tau)
            sum_x += x
            sum_y += y
            sum_xx += x * x
            sum_xy += x * y
            count += 1

        if count < 2:
            return 0.5
        denom = count * sum_xx - sum_x * sum_x
        if denom <= 0.0:
            return 0.5
        slope = (count * sum_xy - sum_x * sum_y) / denom
        if slope < 0.0:
            slope = 0.0
        elif slope > 1.0:
            slope = 1.0
        return slope

    @njit(parallel=True, cache=True, fastmath=True)
    def _rolling_hurst_numba(
        series: np.ndarray,
        window: int,
        min_lag: int,
        max_lag_cap: int,
        min_samples: int,
    ) -> np.ndarray:
        n = series.size
        result = np.empty(n, dtype=np.float64)
        for idx in prange(n):
            start = idx - window + 1
            if start < 0:
                start = 0
            stop = idx + 1
            length = stop - start
            if length < min_samples:
                result[idx] = 0.5
                continue
            value = _hurst_from_window(series, start, stop, min_lag, max_lag_cap)
            if value < 0.0:
                value = 0.0
            elif value > 1.0:
                value = 1.0
            result[idx] = value
        return result

else:  # pragma: no cover - executed when numba missing

    def _rolling_hurst_numba(
        series: np.ndarray,
        window: int,
        min_lag: int,
        max_lag_cap: int,
        min_samples: int,
    ) -> np.ndarray:
        raise RuntimeError("Numba is not available")


@dataclass(slots=True)
class KuramotoIndicator:
    """Compute rolling Kuramoto-style synchronisation scores.

    The ``backend`` parameter controls whether rolling statistics are evaluated
    using vectorised NumPy (``"cpu"``), CuPy GPU acceleration (``"gpu"`` when
    available) or an automatic heuristic that selects GPU execution for large
    arrays when CuPy is present. The GPU path leverages device-side prefix sums
    for memory-bandwidth-bound workloads while preserving numerical parity with
    the CPU implementation.
    """

    window: int = 200
    coupling: float = 1.0
    backend: Literal["auto", "cpu", "gpu"] = "auto"
    min_samples: int = 10
    smoothing: float = 0.0
    volume_weighting: Literal["none", "linear", "sqrt", "log"] = "none"

    def __post_init__(self) -> None:
        if self.window <= 0:
            raise ValueError("window must be positive")
        if self.coupling <= 0:
            raise ValueError("coupling must be positive")
        if self.backend not in {"auto", "cpu", "gpu"}:
            raise ValueError(f"Unsupported backend '{self.backend}'")
        if self.min_samples <= 0:
            raise ValueError("min_samples must be positive")
        if not (0.0 <= self.smoothing < 1.0):
            raise ValueError("smoothing must be within [0, 1)")
        if self.volume_weighting not in _WEIGHTING_MODES:
            raise ValueError(f"Unsupported volume_weighting '{self.volume_weighting}'")

    def compute(
        self, prices: Iterable[float], volumes: Iterable[float] | None = None
    ) -> np.ndarray:
        with _metrics.measure_indicator_compute("kuramoto_indicator") as ctx:
            raw = _as_float_array(prices)
            diagnostics: dict[str, float | dict[str, float]] = {
                "sample_size": float(raw.size),
                "window": float(self.window),
            }
            ratios: dict[str, float] = {}
            if raw.size:
                ratios["input_finite"] = float(np.mean(np.isfinite(raw)))
            else:
                ratios["input_finite"] = 0.0
            diagnostics["ratios"] = ratios
            if raw.size == 0:
                ctx["value"] = 0.0
                ratios.setdefault("valid_windows", 0.0)
                ratios.setdefault("saturation", 0.0)
                ctx["diagnostics"] = diagnostics
                return np.empty(0, dtype=float)
            if not np.isfinite(raw).any():
                ctx["value"] = 0.0
                ratios["valid_windows"] = 0.0
                ratios["saturation"] = 0.0
                ctx["diagnostics"] = diagnostics
                return np.zeros_like(raw, dtype=float)

            series = _fill_missing(raw)
            phases = compute_phase(series)
            complex_phase = np.exp(1j * phases)

            min_samples = min(self.window, self.min_samples)
            counts = np.minimum(np.arange(1, series.size + 1), self.window)
            base_mask = counts >= min_samples

            weight_series: np.ndarray | None = None
            if self.volume_weighting != "none":
                if volumes is None:
                    raise ValueError(
                        "volumes must be provided when volume_weighting is enabled"
                    )
                weight_series = _prepare_weight_series(
                    volumes, expected_size=series.size, mode=self.volume_weighting
                )

            if weight_series is not None:
                totals = _rolling_sum(
                    complex_phase * weight_series, self.window, backend=self.backend
                )
                denominators = _rolling_sum(
                    weight_series, self.window, backend=self.backend
                )
                valid = base_mask & (denominators > 0.0)
                result = np.zeros_like(series, dtype=float)
                if valid.any():
                    order = np.abs(totals[valid]) / denominators[valid]
                    result[valid] = np.clip(self.coupling * order, 0.0, 1.0)
                ratios["valid_windows"] = float(np.mean(valid)) if valid.size else 0.0
                denom_positive = denominators > 0.0
                ratios["weight_positive"] = (
                    float(np.mean(denom_positive)) if denom_positive.size else 0.0
                )
            else:
                totals = _rolling_sum(complex_phase, self.window, backend=self.backend)
                valid = base_mask
                result = np.zeros_like(series, dtype=float)
                if valid.any():
                    order = np.abs(totals[valid]) / counts[valid]
                    result[valid] = np.clip(self.coupling * order, 0.0, 1.0)
                ratios["valid_windows"] = float(np.mean(valid)) if valid.size else 0.0

            if self.smoothing > 0.0:
                result = _apply_exponential_smoothing(result, valid, self.smoothing)

            if result.size:
                boundary = (result <= 1e-12) | (result >= 1.0 - 1e-12)
                ratios["saturation"] = float(np.mean(boundary))
            else:
                ratios.setdefault("saturation", 0.0)

            ctx["value"] = float(result[-1]) if result.size else 0.0
            ctx["diagnostics"] = diagnostics
            return result


@dataclass(slots=True)
class HurstIndicator:
    """Rolling Hurst exponent estimator.

    The indicator now ships with a Numba-parallel rolling kernel that reuses
    the rescaled range computation from :func:`core.indicators.hurst.hurst_exponent`
    while avoiding Python-level loops. When the backend is ``"auto"`` or
    ``"numba"`` and Numba is available the accelerated path is used; otherwise
    the implementation falls back to the original per-window evaluation which
    still honours ``backend`` selections such as ``"cuda"`` for GPU execution.
    """

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
        series = _fill_missing(series).astype(np.float64)

        use_numba = (
            _numba_available()
            and self.backend in {"auto", "numba"}
            and series.size >= max(self.window, self.min_lag * 4)
        )
        if use_numba:
            max_lag_cap = self.max_lag if self.max_lag is not None else -1
            min_samples = max(self.min_lag * 2 + 2, self.min_lag + 3)
            try:
                accelerated = _rolling_hurst_numba(
                    series,
                    int(self.window),
                    int(self.min_lag),
                    int(max_lag_cap),
                    int(min_samples),
                )
                return accelerated.astype(float)
            except Exception:  # pragma: no cover - defensive fallback
                use_numba = False

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
    """Volume-synchronised probability of informed trading.

    When ``backend`` is set to ``"gpu"`` and CuPy is installed the indicator
    executes the rolling bucket aggregation on the GPU. The default ``"auto"``
    mode picks the GPU path for sufficiently large inputs, otherwise falling
    back to the vectorised NumPy implementation.
    """

    bucket_size: int = 50
    threshold: float = 0.8
    backend: Literal["auto", "cpu", "gpu"] = "auto"
    smoothing: float = 0.0
    min_volume: float = 1e-9
    use_signed_imbalance: bool = False

    def __post_init__(self) -> None:
        if self.bucket_size <= 0:
            raise ValueError("bucket_size must be positive")
        if self.threshold <= 0:
            raise ValueError("threshold must be positive")
        if self.backend not in {"auto", "cpu", "gpu"}:
            raise ValueError(f"Unsupported backend '{self.backend}'")
        if not (0.0 <= self.smoothing < 1.0):
            raise ValueError("smoothing must be within [0, 1)")
        if self.min_volume < 0.0:
            raise ValueError("min_volume must be non-negative")

    def compute(self, volume_data: Iterable[Iterable[float]]) -> np.ndarray:
        with _metrics.measure_indicator_compute("vpin_indicator") as ctx:
            array = np.asarray(volume_data, dtype=float)
            row_count = int(array.shape[0]) if array.ndim >= 1 else 0
            diagnostics: dict[str, float | dict[str, float]] = {
                "sample_size": float(max(row_count, 0)),
                "window": float(self.bucket_size),
            }
            ratio_metrics: dict[str, float] = {}
            if array.size:
                ratio_metrics["input_finite"] = float(np.mean(np.isfinite(array)))
            else:
                ratio_metrics["input_finite"] = 0.0
            diagnostics["ratios"] = ratio_metrics
            if array.size == 0:
                ctx["value"] = 0.0
                ratio_metrics.setdefault("valid_windows", 0.0)
                ratio_metrics.setdefault("saturation", 0.0)
                ctx["diagnostics"] = diagnostics
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

            if self.use_signed_imbalance:
                imbalance = buy - sell
            else:
                imbalance = np.abs(buy - sell)

            total_sums = _rolling_sum(total, self.bucket_size, backend=self.backend)
            imb_sums = _rolling_sum(imbalance, self.bucket_size, backend=self.backend)
            result = np.zeros(total.size, dtype=float)

            valid = total_sums > self.min_volume
            if np.any(valid):
                computed_ratios = imb_sums[valid] / total_sums[valid]
                if self.use_signed_imbalance:
                    result[valid] = np.clip(computed_ratios, -1.0, 1.0)
                else:
                    result[valid] = np.clip(np.abs(computed_ratios), 0.0, 1.0)
            ratio_metrics["valid_windows"] = (
                float(np.mean(valid)) if valid.size else 0.0
            )
            if total.size:
                ratio_metrics["positive_volume"] = float(
                    np.mean(total > self.min_volume)
                )

            if self.smoothing > 0.0:
                result = _apply_exponential_smoothing(result, valid, self.smoothing)

            if result.size:
                saturation_mask = np.abs(result) >= (1.0 - 1e-12)
                ratio_metrics["saturation"] = float(np.mean(saturation_mask))
            else:
                ratio_metrics.setdefault("saturation", 0.0)

            ctx["value"] = float(result[-1]) if result.size else 0.0
            ctx["diagnostics"] = diagnostics
            return result
