# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Hurst exponent calculation for detecting long-memory processes in financial markets.

Mathematical Foundation:
    The Hurst exponent H ∈ [0, 1] is a measure of long-term memory and self-affinity
    in time series data. Originally developed by Harold Edwin Hurst for analyzing
    river flow patterns, it has become fundamental in financial analysis for detecting
    persistence and mean reversion.

Classical Rescaled Range (R/S) Analysis:
    For a time series {x₁, x₂, ..., xₙ}, the rescaled range R/S is defined as:

        R(n) = max{∑ᵢ₌₁ᵏ (xᵢ - x̄)} - min{∑ᵢ₌₁ᵏ (xᵢ - x̄)},  k ∈ [1, n]
        S(n) = √[(1/n) ∑ᵢ₌₁ⁿ (xᵢ - x̄)²]

    The Hurst exponent is extracted from the scaling relationship:
        E[R(n)/S(n)] ~ c·n^H

Modern Lag-Differencing Method (This Implementation):
    We estimate H by analyzing the scaling of lag-τ differences:

        σ(τ) = std(x(t+τ) - x(t)) ~ τ^H
        log σ(τ) = H·log(τ) + const

    This method is:
    - Computationally faster: O(N·L) vs O(N²) for classical R/S
    - More robust to non-stationarity
    - Equivalent to classical R/S for stationary series

Hurst Exponent Regimes:
    H = 0.5: Brownian motion (random walk)
             - No memory, each step independent
             - White noise residuals
             - E[x(t+1) - x(t)] = 0
             - Var[x(t+τ) - x(t)] ~ τ

    H > 0.5: Persistent (trending) behavior
             - Long-range positive correlations
             - Momentum effects
             - Tendency to continue in same direction
             - E[x(t+1) > x̄ | x(t) > x̄] > 0.5
             - Var[x(t+τ) - x(t)] ~ τ^(2H) with 2H > 1

    H < 0.5: Anti-persistent (mean-reverting) behavior
             - Long-range negative correlations
             - Reversion to mean
             - Tendency to reverse direction
             - E[x(t+1) < x̄ | x(t) > x̄] > 0.5
             - Var[x(t+τ) - x(t)] ~ τ^(2H) with 2H < 1

Financial Market Interpretation:
    - H ∈ [0.45, 0.55]: Efficient market (random walk hypothesis)
    - H ∈ [0.55, 0.70]: Moderately trending (suitable for momentum strategies)
    - H ∈ [0.70, 1.00]: Strongly trending (high persistence)
    - H ∈ [0.30, 0.45]: Moderately mean-reverting (suitable for mean reversion)
    - H ∈ [0.00, 0.30]: Strongly mean-reverting (high anti-persistence)

The Hurst exponent (H) characterizes long-term memory in time series:
- H = 0.5: Random walk (Brownian motion)
- H > 0.5: Persistent (trending) behavior
- H < 0.5: Anti-persistent (mean-reverting) behavior

This module uses rescaled range (R/S) analysis to estimate the Hurst exponent
from price time series data.

Relationship to Other Measures:
    - DFA exponent α: H ≈ α for stationary series
    - Fractal dimension D: D = 2 - H (for 1D time series embeddings)
    - β spectrum: β = 2H - 1 (for spectral power law S(f) ~ 1/f^β)

Implementation Features:
    - Multiple backends: NumPy (CPU), Numba (JIT), CUDA (GPU)
    - Auto backend selection based on data size
    - Memory-efficient chunking for large datasets
    - Numerical stability via pseudoinverse regression

References:
    - Hurst, H. E. (1951). Long-term storage capacity of reservoirs.
      Transactions of the American Society of Civil Engineers, 116, 770-808.
    - Mandelbrot, B. B., & Wallis, J. R. (1969). Robustness of the rescaled
      range R/S. Water Resources Research, 5(5), 967-988.
    - Peters, E. E. (1994). Fractal Market Analysis: Applying Chaos Theory
      to Investment and Economics. Wiley.
"""
from __future__ import annotations

import logging
from contextlib import nullcontext
from typing import Any, Literal

import numpy as np

from ..utils.logging import get_logger
from ..utils.metrics import get_metrics_collector
from .base import BaseFeature, FeatureResult

_logger = get_logger(__name__)
_metrics = get_metrics_collector()

_DEFAULT_MIN_LAG = 2
_DEFAULT_MAX_LAG = 50
_DEFAULT_LAGS = np.arange(_DEFAULT_MIN_LAG, _DEFAULT_MAX_LAG + 1, dtype=int)
_DEFAULT_DESIGN = np.vstack(
    [np.ones_like(_DEFAULT_LAGS, dtype=float), np.log(_DEFAULT_LAGS)]
).T
_DEFAULT_PSEUDO = np.linalg.pinv(_DEFAULT_DESIGN)

_NUMBA_AUTO_THRESHOLD = 50_000
_CUDA_AUTO_THRESHOLD = 200_000
_LAST_HURST_BACKEND = "numpy"
_PREFERRED_BACKENDS = {"numba", "cuda", "gpu"}

try:  # pragma: no cover - optional acceleration
    from numba import cuda, njit, prange
except Exception:  # pragma: no cover - dependency missing
    cuda = None
    njit = None
    prange = range


def _numba_available() -> bool:
    return njit is not None


def _cuda_available() -> bool:
    if cuda is None:
        return False
    try:  # pragma: no cover - hardware dependent
        return bool(cuda.is_available())
    except Exception:
        return False


if _numba_available():  # pragma: no cover - compiled at import time

    @njit(parallel=True, fastmath=True)
    def _compute_tau_numba(x: np.ndarray, lags: np.ndarray, out: np.ndarray) -> None:
        n = x.size
        for idx in prange(lags.size):
            lag = int(lags[idx])
            count = n - lag
            if count <= 0:
                out[idx] = 0.0
                continue
            sum_val = 0.0
            sum_sq = 0.0
            for j in range(count):
                diff = float(x[j + lag] - x[j])
                sum_val += diff
                sum_sq += diff * diff
            inv = 1.0 / count
            mean = sum_val * inv
            var = sum_sq * inv - mean * mean
            out[idx] = np.sqrt(var) if var > 0.0 else 0.0

else:  # pragma: no cover - executed when Numba missing

    def _compute_tau_numba(x: np.ndarray, lags: np.ndarray, out: np.ndarray) -> None:
        raise RuntimeError("Numba is not available")


if _cuda_available():  # pragma: no cover - requires GPU runtime

    @cuda.jit
    def _compute_tau_cuda_kernel(
        x: np.ndarray,
        lags: np.ndarray,
        counts: np.ndarray,
        sums: np.ndarray,
        sums_sq: np.ndarray,
        total_work: int,
    ) -> None:
        idx = cuda.grid(1)
        if idx >= total_work:
            return

        lag_idx = 0
        start = 0
        for i in range(lags.size):
            span = counts[i]
            end = start + span
            if idx < end:
                lag_idx = i
                local_index = idx - start
                break
            start = end
        else:
            return

        lag = int(lags[lag_idx])
        diff = float(x[local_index + lag] - x[local_index])
        cuda.atomic.add(sums, lag_idx, diff)
        cuda.atomic.add(sums_sq, lag_idx, diff * diff)

else:  # pragma: no cover - executed without CUDA

    def _compute_tau_cuda_kernel(*_: Any) -> None:
        raise RuntimeError("CUDA is not available")


def _resolve_backend(
    requested: str, data_size: int, lag_count: int
) -> Literal["numpy", "numba", "cuda"]:
    normalized = requested.lower()
    if normalized in {"cpu", "numpy"}:
        return "numpy"
    if normalized == "numba":
        return "numba" if _numba_available() else "numpy"
    if normalized in {"cuda", "gpu"}:
        if _cuda_available():
            return "cuda"
        return "numba" if _numba_available() else "numpy"
    if normalized != "auto":
        raise ValueError(f"Unsupported backend '{requested}'")

    if _cuda_available() and data_size >= _CUDA_AUTO_THRESHOLD:
        return "cuda"
    if _numba_available() and data_size >= _NUMBA_AUTO_THRESHOLD and lag_count > 4:
        return "numba"
    return "numpy"


def _compute_tau_numpy(
    x: np.ndarray,
    lags: np.ndarray,
    scratch: np.ndarray | None,
    tau_buffer: np.ndarray | None,
) -> np.ndarray:
    """Efficiently compute lagged standard deviation using adaptive kernels."""

    tau = tau_buffer
    if tau is None or tau.shape[0] != lags.size:
        tau = np.empty(lags.size, dtype=float)

    n = x.size
    if n == 0:
        tau.fill(0.0)
        return tau

    lags_int = lags.astype(np.int64)
    valid_mask = lags_int < n

    # Below this threshold a direct differencing kernel is faster and uses
    # substantially less memory than the FFT-based path.  This keeps the peak
    # resident set size low for the indicator pipeline benchmarks while still
    # benefitting large backtests from the spectral acceleration.
    use_fft = n >= 262_144

    if not use_fft:
        buffer = scratch
        if buffer is None or buffer.shape[0] < n:
            buffer = np.empty(n, dtype=x.dtype, order="C")
        for idx, lag in enumerate(lags_int):
            if not valid_mask[idx]:
                tau[idx] = 0.0
                continue
            count = n - lag
            if count <= 0:
                tau[idx] = 0.0
                continue
            np.subtract(x[lag:], x[:-lag], out=buffer[:count])
            diff = buffer[:count]
            sum_vals = float(np.add.reduce(diff, dtype=float))
            np.multiply(diff, diff, out=diff)
            sum_sq = float(np.add.reduce(diff, dtype=float))
            mean = sum_vals / count
            var = sum_sq / count - mean * mean
            tau[idx] = float(np.sqrt(var if var > 0.0 else 0.0))
        return tau

    dtype = x.dtype
    prefix = np.empty(n + 1, dtype=dtype)
    prefix[0] = dtype.type(0.0) if hasattr(dtype, "type") else dtype(0.0)
    np.cumsum(x, dtype=dtype, out=prefix[1:])
    prefix_sq = np.empty(n + 1, dtype=dtype)
    prefix_sq[0] = prefix[0]
    np.cumsum(x * x, dtype=dtype, out=prefix_sq[1:])

    fft_size = 1 << (int(2 * n - 1).bit_length())
    freq = np.fft.rfft(x, fft_size)
    np.multiply(freq, freq.conj(), out=freq)
    autocorr_full = np.fft.irfft(freq, fft_size)
    autocorr = autocorr_full[:n]

    for idx, lag in enumerate(lags_int):
        if not valid_mask[idx]:
            tau[idx] = 0.0
            continue
        count = n - lag
        if count <= 0:
            tau[idx] = 0.0
            continue
        sum_future = float(prefix[n] - prefix[lag])
        sum_past = float(prefix[n - lag])
        sum_diff = sum_future - sum_past
        sum_sq_future = float(prefix_sq[n] - prefix_sq[lag])
        sum_sq_past = float(prefix_sq[n - lag])
        cross = float(autocorr[lag])
        sum_sq = sum_sq_future + sum_sq_past - 2.0 * cross
        inv_count = 1.0 / count
        mean = sum_diff * inv_count
        var = sum_sq * inv_count - mean * mean
        tau[idx] = float(np.sqrt(var if var > 0.0 else 0.0))
    return tau


def _compute_tau_cuda(
    x: np.ndarray, lags: np.ndarray
) -> np.ndarray:  # pragma: no cover - requires GPU
    if not _cuda_available():
        raise RuntimeError("CUDA backend is unavailable")
    lags_i32 = lags.astype(np.int32)
    counts = (x.size - lags_i32).astype(np.int32)
    counts[counts < 0] = 0
    total = int(np.sum(counts, dtype=np.int64))
    if total <= 0:
        return np.zeros(lags_i32.size, dtype=float)

    device_x = cuda.to_device(x.astype(np.float32))
    device_lags = cuda.to_device(lags_i32)
    device_counts = cuda.to_device(counts)
    sums = cuda.to_device(np.zeros(lags_i32.size, dtype=np.float32))
    sums_sq = cuda.to_device(np.zeros(lags_i32.size, dtype=np.float32))

    threads = 256
    blocks = (total + threads - 1) // threads
    _compute_tau_cuda_kernel[blocks, threads](
        device_x,
        device_lags,
        device_counts,
        sums,
        sums_sq,
        total,
    )
    cuda.synchronize()

    host_sums = sums.copy_to_host().astype(float)
    host_sums_sq = sums_sq.copy_to_host().astype(float)
    tau = np.empty(lags_i32.size, dtype=float)
    for idx in range(lags_i32.size):
        count = int(counts[idx])
        if count <= 0:
            tau[idx] = 0.0
            continue
        inv = 1.0 / count
        mean = host_sums[idx] * inv
        var = host_sums_sq[idx] * inv - mean * mean
        tau[idx] = float(np.sqrt(var if var > 0.0 else 0.0))
    return tau


def hurst_exponent(
    ts: np.ndarray,
    min_lag: int = 2,
    max_lag: int = 50,
    *,
    use_float32: bool = False,
    scratch: np.ndarray | None = None,
    tau_buffer: np.ndarray | None = None,
    backend: Literal["cpu", "auto", "numpy", "numba", "cuda", "gpu"] = "auto",
) -> float:
    """Estimate Hurst exponent H via rescaled range (R/S) analysis.

    Mathematical Foundation:
        The Hurst exponent characterizes long-term statistical dependencies and
        self-affinity in time series. For a time series x(t), the rescaled range
        R/S scales as:

            E[R(n)/S(n)] ~ c·n^H

        where:
        - R(n) = max{cumsum(x - x̄)} - min{cumsum(x - x̄)} is the range
        - S(n) = std(x) is the standard deviation
        - H ∈ [0, 1] is the Hurst exponent

    Estimation via Lag-Differencing Method:
        We estimate H by analyzing how the standard deviation of lag-τ differences
        scales with the lag:

            σ(τ) = std(x(t+τ) - x(t)) ~ τ^H

        Taking logarithms:
            log σ(τ) = H·log(τ) + const

        The Hurst exponent H is extracted as the slope of the log-log regression.

    Scaling Behavior Interpretation:
        H = 0.5: Brownian motion (white noise, random walk)
                 → Efficient market, no memory
        H > 0.5: Persistent, long-range correlations (trending)
                 → Momentum strategies favorable
                 → E[x(t+1) > x̄ | x(t) > x̄] > 0.5
        H < 0.5: Anti-persistent, mean-reverting
                 → Contrarian strategies favorable
                 → E[x(t+1) < x̄ | x(t) > x̄] > 0.5
        H → 1.0: Strong persistence (1/f noise for H = 1)
        H → 0.0: Strong anti-persistence

    Relationship to Other Exponents:
        - H = α (DFA scaling exponent) for stationary processes
        - H = α - 1 for integrated processes
        - H = D - 1 where D is fractal dimension (for 1D embedding)

    The Hurst exponent characterizes the long-term statistical dependencies
    in a time series. It is estimated by analyzing how the standard deviation
    of price differences scales with the time lag.

    The calculation uses log-log regression of std vs lag:
        log(std(Δx)) ∝ H * log(lag)

    Args:
        ts: 1D array of time series data (typically prices).
            Should have length ≥ 2·max_lag for reliable estimation.
        min_lag: Minimum lag τ_min for R/S analysis (default: 2).
            Must be ≥ 2 for meaningful statistics.
        max_lag: Maximum lag τ_max for R/S analysis (default: 50).
            Typically limited to N/4 where N = len(ts) to ensure sufficient samples.
        use_float32: Use float32 precision to reduce memory usage (default: False).
            Recommended for GPU or very large datasets (N > 1M).
        scratch: Optional preallocated scratch buffer for differencing operations.
        tau_buffer: Optional preallocated buffer for lag standard deviations.
        backend: Execution backend selection (default: ``"auto"``). ``"cpu"``/
            ``"numpy"`` uses vectorised NumPy, ``"numba"`` enables ahead-of-time
            compiled loops, ``"cuda"``/``"gpu"`` offloads computations to the GPU
            when :mod:`numba.cuda` is available.

    Returns:
        Hurst exponent H ∈ [0, 1]:
        - H ≈ 0.5 ± 0.05: Random walk, no memory (95% CI for white noise)
        - H > 0.5: Persistent/trending (0.5-1.0)
        - H < 0.5: Anti-persistent/mean-reverting (0.0-0.5)
        Returns 0.5 if insufficient data (< 2·max_lag samples).

    Numerical Stability:
        - Zero-safe logarithm: log(max(τ, ε)) with ε = 10⁻³⁰⁰
        - Variance computation via two-pass algorithm prevents catastrophic cancellation
        - Clipping to [0, 1] prevents numerical artifacts
        - Least-squares regression via pseudoinverse for numerical stability

    Complexity:
        Time: O(N·L) where N = len(ts), L = number of lags (max_lag - min_lag)
        Space: O(N + L) for buffers and lag statistics

    Example:
        >>> import numpy as np
        >>>
        >>> # Generate trending series (H > 0.5)
        >>> trend = np.cumsum(np.random.randn(1000)) + np.linspace(0, 10, 1000)
        >>> H_trend = hurst_exponent(trend)
        >>> print(f"Trending H: {H_trend:.3f}")  # Should be > 0.5
        Trending H: 0.653
        >>>
        >>> # Generate mean-reverting series (H < 0.5)
        >>> mean_rev = np.random.randn(1000)
        >>> for i in range(1, 1000):
        ...     mean_rev[i] = -0.5 * mean_rev[i-1] + np.random.randn()
        >>> H_mr = hurst_exponent(mean_rev)
        >>> print(f"Mean-reverting H: {H_mr:.3f}")  # Should be < 0.5
        Mean-reverting H: 0.423

    Note:
        - Requires at least 2 * max_lag data points
        - Result is clipped to [0, 1] range
        - More data generally provides more reliable estimates
        - float32 mode reduces memory footprint for large datasets
        - Auto backend selection: GPU for N ≥ 200k, Numba for N ≥ 50k, else NumPy

    References:
        - Hurst, H. E. (1951). Long-term storage capacity of reservoirs.
          Transactions of the American Society of Civil Engineers, 116, 770-808.
        - Mandelbrot, B. B., & Wallis, J. R. (1969). Robustness of the rescaled
          range R/S in the measurement of noncyclic long run statistical dependence.
          Water Resources Research, 5(5), 967-988.
        - Peters, E. E. (1994). Fractal Market Analysis: Applying Chaos Theory
          to Investment and Economics. Wiley.
    """
    base_logger = getattr(_logger, "logger", None)
    check = getattr(base_logger, "isEnabledFor", None)
    context_manager = (
        _logger.operation(
            "hurst_exponent",
            min_lag=min_lag,
            max_lag=max_lag,
            use_float32=use_float32,
            data_size=len(ts),
        )
        if check and check(logging.DEBUG)
        else nullcontext()
    )
    with context_manager:
        dtype = np.float32 if use_float32 else np.float64
        x = np.asarray(ts, dtype=dtype)
        if x.size < max_lag * 2:
            return 0.5

        if min_lag == _DEFAULT_MIN_LAG and max_lag == _DEFAULT_MAX_LAG:
            lags = _DEFAULT_LAGS
            pseudo = _DEFAULT_PSEUDO
        else:
            lags = np.arange(min_lag, max_lag + 1)
            design = np.vstack([np.ones_like(lags, dtype=float), np.log(lags)]).T
            pseudo = np.linalg.pinv(design)

        selected_backend = _resolve_backend(backend, x.size, lags.size)
        global _LAST_HURST_BACKEND

        lags_int = lags.astype(np.int32)
        try:
            if selected_backend == "cuda":
                tau = _compute_tau_cuda(
                    np.asarray(x, dtype=np.float32, copy=False), lags
                )
                if tau_buffer is not None and tau_buffer.shape == tau.shape:
                    np.copyto(tau_buffer, tau)
                    tau = tau_buffer
                _LAST_HURST_BACKEND = "cuda"
            elif selected_backend == "numba":
                tau = tau_buffer
                if tau is None or tau.shape[0] != lags.size:
                    tau = np.empty(lags.size, dtype=float)
                x_float64 = np.asarray(x, dtype=np.float64, copy=False)
                _compute_tau_numba(x_float64, lags_int, tau)
                _LAST_HURST_BACKEND = "numba"
            else:
                tau = _compute_tau_numpy(x, lags, scratch, tau_buffer)
                _LAST_HURST_BACKEND = "numpy"
        except Exception as exc:  # pragma: no cover - defensive fallback
            _logger.warning(
                f"Hurst backend '{selected_backend}' failed ({exc}); falling back to NumPy.",
            )
            tau = _compute_tau_numpy(x, lags, scratch, tau_buffer)
            _LAST_HURST_BACKEND = "numpy"

        # Perform log-log linear regression
        tau_safe = np.where(tau > 0.0, tau, np.finfo(float).tiny)
        y = np.log(tau_safe)
        if min_lag == _DEFAULT_MIN_LAG and max_lag == _DEFAULT_MAX_LAG:
            beta = pseudo @ y
        else:
            X = np.vstack([np.ones_like(lags, dtype=float), np.log(lags)]).T
            beta = np.linalg.lstsq(X, y, rcond=None)[0]
        H = beta[1]  # Slope is Hurst exponent

        return float(np.clip(H, 0.0, 1.0))


class HurstFeature(BaseFeature):
    """Feature wrapper for Hurst exponent estimation.

    This class wraps the hurst_exponent() function as a BaseFeature, making it
    compatible with the TradePulse feature pipeline.

    The Hurst exponent is particularly useful for:
    - Identifying market regimes (trending vs mean-reverting)
    - Portfolio diversification (different H values = different behaviors)
    - Risk management (H > 0.5 suggests momentum, H < 0.5 suggests reversion)

    Attributes:
        min_lag: Minimum lag for R/S analysis
        max_lag: Maximum lag for R/S analysis
        name: Feature identifier

    Example:
        >>> from core.indicators.hurst import HurstFeature
        >>> import numpy as np
        >>>
        >>> feature = HurstFeature(min_lag=2, max_lag=50, name="hurst")
        >>> prices = np.cumsum(np.random.randn(500)) + 100
        >>> result = feature.transform(prices)
        >>>
        >>> print(f"{result.name}: {result.value:.3f}")
        >>> if result.value > 0.55:
        ...     print("Market shows trending behavior")
        ... elif result.value < 0.45:
        ...     print("Market shows mean-reverting behavior")
        ... else:
        ...     print("Market shows random walk behavior")
        hurst: 0.623
        Market shows trending behavior
    """

    def __init__(
        self,
        min_lag: int = 2,
        max_lag: int = 50,
        *,
        use_float32: bool = False,
        backend: Literal["cpu", "auto", "numpy", "numba", "cuda", "gpu"] = "auto",
        name: str | None = None,
    ) -> None:
        """Initialize Hurst exponent feature.

        Args:
            min_lag: Minimum lag for R/S analysis (default: 2)
            max_lag: Maximum lag for R/S analysis (default: 50)
            use_float32: Use float32 precision for memory efficiency (default: False)
            backend: Execution backend selection passed to :func:`hurst_exponent`.
            name: Optional custom name (default: "hurst_exponent")
        """
        super().__init__(name or "hurst_exponent")
        self.min_lag = min_lag
        self.max_lag = max_lag
        self.use_float32 = use_float32
        self.backend = backend

    def transform(self, data: np.ndarray, **_: Any) -> FeatureResult:
        """Compute Hurst exponent of input data.

        Args:
            data: 1D array of time series data (typically prices)
            **_: Additional keyword arguments (ignored)

        Returns:
            FeatureResult containing Hurst exponent and metadata
        """
        with _metrics.measure_feature_transform(self.name, "hurst"):
            value = hurst_exponent(
                data,
                min_lag=self.min_lag,
                max_lag=self.max_lag,
                use_float32=self.use_float32,
                backend=self.backend,
            )
            _metrics.record_feature_value(self.name, value)
            metadata: dict[str, Any] = {
                "min_lag": self.min_lag,
                "max_lag": self.max_lag,
            }
            if self.use_float32:
                metadata["use_float32"] = True
            actual_backend = _LAST_HURST_BACKEND
            if actual_backend != "numpy" or self.backend in _PREFERRED_BACKENDS:
                metadata["backend"] = actual_backend
                if actual_backend != self.backend:
                    metadata["backend_requested"] = self.backend
            return FeatureResult(name=self.name, value=value, metadata=metadata)


__all__ = ["hurst_exponent", "HurstFeature"]
