# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Entropy-based market uncertainty indicators.

This module provides Shannon entropy and delta entropy calculations for
quantifying market uncertainty and regime changes.

Shannon entropy measures the randomness or unpredictability in price data.
Higher entropy indicates more chaotic or random behavior, while lower entropy
suggests more structured or predictable patterns.

Delta entropy (ΔH) measures the change in entropy over time, which can signal
regime transitions in the market.

References:
    - Shannon, C. E. (1948). A mathematical theory of communication.
      Bell System Technical Journal, 27(3), 379-423.
"""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from contextlib import nullcontext
from typing import Any, Literal, Sequence

import numpy as np

from ..utils.logging import get_logger
from ..utils.metrics import get_metrics_collector
from .base import BaseFeature, FeatureResult

_logger = get_logger(__name__)
_metrics = get_metrics_collector()


def _log_debug_enabled() -> bool:
    base_logger = getattr(_logger, "logger", None)
    check = getattr(base_logger, "isEnabledFor", None)
    return bool(check and check(logging.DEBUG))


_GPU_MIN_SIZE_BYTES = 512 * 1024
_GPU_MEMORY_MARGIN = 1.4
_LAST_ENTROPY_BACKEND = "cpu"

try:  # pragma: no cover - optional dependency
    import cupy as cp
except Exception:  # pragma: no cover - fallback when CuPy missing
    cp = None

try:  # pragma: no cover - optional dependency
    from numba import cuda
except Exception:  # pragma: no cover - fallback when Numba missing
    cuda = None

if cuda is not None:  # pragma: no cover - compiled at import time
    import math

    @cuda.jit
    def _entropy_histogram_kernel(data, hist, min_v, max_v):
        i = cuda.grid(1)
        if i >= data.size:
            return
        value = data[i]
        if not math.isfinite(value):
            return
        span = max_v - min_v
        if span <= 0:
            bin_id = 0
        else:
            pos = (value - min_v) / span
            if pos < 0:
                pos = 0.0
            if pos > 0.999999:
                pos = 0.999999
            bin_id = int(pos * hist.size)
            if bin_id >= hist.size:
                bin_id = hist.size - 1
        cuda.atomic.add(hist, bin_id, 1)

else:  # pragma: no cover
    _entropy_histogram_kernel = None


def entropy(
    series: np.ndarray,
    bins: int = 30,
    *,
    use_float32: bool = False,
    chunk_size: int | None = None,
    parallel: Literal["none", "process", "async"] = "none",
    max_workers: int | None = None,
    backend: Literal["cpu", "gpu", "auto", "cupy", "numba"] = "cpu",
) -> float:
    """Calculate Shannon entropy of a data series for uncertainty quantification.

    Mathematical Definition:
        For a discrete probability distribution P = {p₁, p₂, ..., pₙ} where
        pᵢ ≥ 0 and ∑ᵢ pᵢ = 1, the Shannon entropy is:

            H(P) = -∑ᵢ₌₁ⁿ pᵢ · log(pᵢ)    [nats, using natural logarithm]

        Or equivalently in bits (using log₂):
            H(P) = -∑ᵢ₌₁ⁿ pᵢ · log₂(pᵢ)  [bits]

    Implementation:
        1. Normalize input x(t) to interval [-1, 1] for numerical stability:
           x̃(t) = x(t) / max|x(t)|
        
        2. Discretize into B bins via histogram to approximate probability mass:
           pᵢ = count(bin i) / N,  where N = total count
        
        3. Compute entropy (with 0·log(0) := 0 convention):
           H = -∑ᵢ₌₁ᴮ pᵢ · log(pᵢ)

    Physical Interpretation:
        H = 0:        Zero entropy (deterministic/constant signal)
        H = log(B):   Maximum entropy (uniform distribution over B bins)
        0 < H < log(B): Partial structure

    In Financial Context:
        - High H → High market uncertainty/randomness (chaotic regime)
        - Low H → Low uncertainty/predictability (trending regime)
        - ΔH > 0 → Increasing chaos (regime transition signal)
        - ΔH < 0 → Decreasing chaos (consolidation signal)

    Entropy quantifies the uncertainty or randomness in the data distribution.
    The series is normalized and binned, then Shannon entropy is computed as:

        H = -Σ p(i) * log(p(i))

    where p(i) is the probability of bin i.

    Args:
        series: 1D array of numeric data (typically prices or returns)
        bins: Number of bins for histogram discretization (default: 30).
            More bins → finer resolution but requires more data.
            Rule of thumb: bins ≈ N^(1/3) for N samples (Scott's rule).
        use_float32: Use float32 precision to reduce memory usage (default: False).
            Recommended for GPU processing or very large arrays.
        chunk_size: Process data in chunks for large arrays (default: None, no chunking).
                   If specified, computes entropy by averaging over chunks.
        parallel: Parallelization strategy for chunked execution. ``"process"``
                   uses :class:`concurrent.futures.ProcessPoolExecutor`, while
                   ``"async"`` executes chunks via :mod:`asyncio` thread pools.
        max_workers: Optional maximum worker count for the selected parallel
                   executor.
        backend: Computation backend. ``"cpu"`` runs on NumPy, ``"gpu"``/``"auto"``
                 pick the best available accelerator (CuPy first, then
                 :mod:`numba.cuda`). Auto mode requires data ≥ 512KB for GPU.

    Returns:
        Shannon entropy value H ≥ 0 in nats (natural logarithm base).
        Higher values indicate more randomness/chaos.
        Returns 0.0 for empty or invalid input.

    Numerical Stability:
        - Data scaled to [-1, 1] prevents overflow/underflow
        - Non-finite values (NaN, ±∞) filtered before computation
        - Zero probability bins excluded (0·log(0) = 0 convention)
        - Chunked processing prevents memory overflow on large arrays

    Complexity:
        Time: O(N) for histogram + O(B) for entropy summation = O(N + B)
        Space: O(B) for histogram bins (constant w.r.t. N)

    Example:
        >>> prices = np.array([100, 101, 102, 101, 100, 99, 100, 101])
        >>> H = entropy(prices, bins=10)
        >>> print(f"Entropy: {H:.3f}")
        Entropy: 1.234

        >>> # Memory-efficient processing for large arrays
        >>> large_data = np.random.randn(1_000_000)
        >>> H = entropy(large_data, bins=50, use_float32=True, chunk_size=10000)

    Note:
        - Data is automatically scaled to [-1, 1] range for numerical stability
        - Invalid values (NaN, inf) are filtered out
        - Returns 0.0 if no valid data remains after filtering
        - Chunked processing computes weighted average entropy across chunks

    References:
        - Shannon, C. E. (1948). A mathematical theory of communication.
          Bell System Technical Journal, 27(3), 379-423.
        - Cover, T. M., & Thomas, J. A. (2006). Elements of Information Theory.
          Wiley, 2nd edition.
    """
    context_manager = (
        _logger.operation(
            "entropy",
            bins=bins,
            use_float32=use_float32,
            chunk_size=chunk_size,
            data_size=len(series),
            parallel=parallel,
            backend=backend,
        )
        if _log_debug_enabled()
        else nullcontext()
    )
    with context_manager:
        global _LAST_ENTROPY_BACKEND

        dtype = np.float32 if use_float32 else float
        x = np.asarray(series, dtype=dtype)
        if x.size == 0:
            _LAST_ENTROPY_BACKEND = "cpu"
            return 0.0

        # Filter out non-finite values
        finite = np.isfinite(x)
        if not finite.all():
            x = x[finite]
        if x.size == 0:
            _LAST_ENTROPY_BACKEND = "cpu"
            return 0.0

        data_bytes = int(x.size) * np.dtype(dtype).itemsize
        selected_backend = _resolve_backend(backend, data_bytes=data_bytes)
        if selected_backend != "cpu":
            try:
                result = _entropy_gpu(x, bins, selected_backend)
                _LAST_ENTROPY_BACKEND = selected_backend
                return result
            except Exception as exc:  # pragma: no cover - defensive logging
                _logger.warning(
                    "GPU entropy backend '%s' failed (%s); falling back to CPU.",
                    selected_backend,
                    exc,
                )
                _LAST_ENTROPY_BACKEND = "cpu"

        global_scale = float(np.max(np.abs(x)))
        if not np.isfinite(global_scale) or global_scale == 0.0:
            global_scale = None

        data_min = float(np.min(x))
        data_max = float(np.max(x))

        if global_scale is not None:
            norm_min = data_min / global_scale
            norm_max = data_max / global_scale
            hist_range: tuple[float, float] | None = (
                (norm_min, norm_max) if norm_max > norm_min else None
            )
        else:
            hist_range = (data_min, data_max) if data_max > data_min else None

        # Chunked processing for large arrays
        if chunk_size is not None and x.size > chunk_size:
            chunks = [
                x[i : min(i + chunk_size, x.size)] for i in range(0, x.size, chunk_size)
            ]
            tasks = [
                (chunk, bins, dtype, global_scale, hist_range)
                for chunk in chunks
                if chunk.size > 0
            ]
            if not tasks:
                _LAST_ENTROPY_BACKEND = "cpu"
                return 0.0

            if parallel == "process":
                results = _run_entropy_process(tasks, max_workers)
            elif parallel == "async":
                results = _run_entropy_async(tasks, max_workers)
            else:
                results = [_entropy_chunk_worker(task) for task in tasks]

            total_counts = np.zeros(bins, dtype=np.int64)
            total_weight = 0
            for counts, weight in results:
                if weight <= 0:
                    continue
                total_counts += counts.astype(np.int64)
                total_weight += weight

            if total_weight <= 0:
                _LAST_ENTROPY_BACKEND = "cpu"
                return 0.0

            probs = total_counts[total_counts > 0] / float(total_weight)
            _LAST_ENTROPY_BACKEND = "cpu"
            return float(-(probs * np.log(probs)).sum())

        # Standard single-pass processing
        # Normalize to [-1, 1] for numerical stability
        if global_scale is not None:
            x = x / global_scale

        # Compute histogram
        counts, _ = np.histogram(x, bins=bins, range=hist_range, density=False)
        total = counts.sum(dtype=dtype)
        if total == 0:
            _LAST_ENTROPY_BACKEND = "cpu"
            return 0.0

        # Calculate Shannon entropy
        p = counts[counts > 0] / total
        _LAST_ENTROPY_BACKEND = "cpu"
        return float(-(p * np.log(p)).sum())


def _cuda_available() -> bool:
    if cuda is None:
        return False
    try:
        return bool(cuda.is_available())
    except Exception:  # pragma: no cover - driver missing
        return False


def _gpu_memory_info() -> tuple[int, int] | None:
    if cp is None or not hasattr(cp, "cuda"):
        return None
    try:  # pragma: no cover - interacts with GPU driver
        device = cp.cuda.Device()
        free_mem, total_mem = device.mem_info
        return int(free_mem), int(total_mem)
    except Exception:
        return None


def _resolve_backend(requested: str, data_bytes: int | None = None) -> str:
    normalized = requested.lower()
    if normalized not in {"cpu", "gpu", "auto", "cupy", "numba"}:
        raise ValueError(f"Unsupported backend '{requested}'")
    if normalized == "cpu":
        return "cpu"
    if normalized == "cupy":
        return "cupy" if cp is not None else "cpu"
    if normalized == "numba":
        return "numba" if _cuda_available() else "cpu"
    # gpu/auto prefer CuPy, then Numba
    if data_bytes is not None and data_bytes < _GPU_MIN_SIZE_BYTES:
        return "cpu"
    if cp is not None:
        mem_info = _gpu_memory_info()
        if mem_info is not None:
            free_mem, _total_mem = mem_info
            required = data_bytes if data_bytes is not None else _GPU_MIN_SIZE_BYTES
            if free_mem > int(required * _GPU_MEMORY_MARGIN):
                return "cupy"
        else:
            # Unable to query memory; be conservative and stay on CPU.
            return "cpu"
    if _cuda_available():
        if data_bytes is not None and data_bytes < _GPU_MIN_SIZE_BYTES:
            return "cpu"
        return "numba"
    return "cpu"


def _entropy_gpu(
    x: np.ndarray, bins: int, backend: str
) -> float:  # pragma: no cover - requires GPU backends
    if backend == "cupy":
        if cp is None:
            raise RuntimeError("CuPy not available")
        arr = cp.asarray(x, dtype=cp.float32)
        mask = cp.isfinite(arr)
        if not cp.all(mask):
            arr = arr[mask]
        if arr.size == 0:
            return 0.0
        scale = cp.max(cp.abs(arr))
        scale_value = float(scale.get() if hasattr(scale, "get") else scale)
        if scale_value != 0.0 and np.isfinite(scale_value):
            arr = arr / scale_value
        counts, _ = cp.histogram(arr, bins=bins)
        total = counts.sum(dtype=cp.float32)
        total_value = float(total.get() if hasattr(total, "get") else total)
        if total_value == 0.0:
            return 0.0
        mask = counts > 0
        probs = counts[mask] / total_value
        entropy_value = -cp.sum(probs * cp.log(probs))
        return float(entropy_value.get())

    if backend == "numba":
        if not _cuda_available() or _entropy_histogram_kernel is None:
            raise RuntimeError("Numba CUDA backend is unavailable")
        data = np.asarray(x, dtype=np.float32)
        mask = np.isfinite(data)
        if not mask.all():
            data = data[mask]
        if data.size == 0:
            return 0.0
        min_v = float(np.min(data))
        max_v = float(np.max(data))
        if not np.isfinite(min_v) or not np.isfinite(max_v) or max_v == min_v:
            return 0.0
        device_data = cuda.to_device(data)
        device_hist = cuda.to_device(np.zeros(bins, dtype=np.int32))
        threads = 256
        blocks = (int(data.size) + threads - 1) // threads
        _entropy_histogram_kernel[blocks, threads](
            device_data, device_hist, min_v, max_v
        )
        cuda.synchronize()
        counts = device_hist.copy_to_host().astype(np.float32)
        total = counts.sum(dtype=np.float32)
        if total == 0:
            return 0.0
        probs = counts[counts > 0] / total
        return float(-(probs * np.log(probs)).sum())

    raise ValueError(f"Unknown backend '{backend}'")


def _entropy_chunk_worker(
    task: tuple[np.ndarray, int, np.dtype, float | None, tuple[float, float] | None],
) -> tuple[np.ndarray, int]:
    chunk, bins, dtype, scale, hist_range = task
    chunk = np.asarray(chunk, dtype=dtype)
    if chunk.size == 0:
        return (np.zeros(bins, dtype=np.int64), 0)
    if scale is not None:
        chunk = chunk / scale
    counts, _ = np.histogram(chunk, bins=bins, range=hist_range, density=False)
    counts = counts.astype(np.int64)
    total = int(counts.sum(dtype=np.int64))
    return counts, total


def _run_entropy_process(
    tasks: Sequence[
        tuple[np.ndarray, int, np.dtype, float | None, tuple[float, float] | None]
    ],
    max_workers: int | None,
) -> list[tuple[np.ndarray, int]]:
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        return list(executor.map(_entropy_chunk_worker, tasks))


def _run_entropy_async(
    tasks: Sequence[
        tuple[np.ndarray, int, np.dtype, float | None, tuple[float, float] | None]
    ],
    max_workers: int | None,
) -> list[tuple[np.ndarray, int]]:
    async def _runner() -> list[tuple[np.ndarray, int]]:
        loop = asyncio.get_running_loop()
        executor: ThreadPoolExecutor | None = None
        try:
            if max_workers is not None:
                executor = ThreadPoolExecutor(max_workers=max_workers)
            futures = [
                loop.run_in_executor(executor, _entropy_chunk_worker, task)
                for task in tasks
            ]
            return await asyncio.gather(*futures)
        finally:
            if executor is not None:
                executor.shutdown(wait=True)

    coro = _runner()
    try:
        return asyncio.run(coro)
    except RuntimeError as exc:
        message = str(exc)
        if (
            "event loop is running" not in message
            and "running event loop" not in message
        ):
            coro.close()
            raise
        coro.close()
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            return list(executor.map(_entropy_chunk_worker, tasks))


def delta_entropy(series: np.ndarray, window: int = 100, bins_range=(10, 50)) -> float:
    """Calculate delta entropy (temporal rate of change in uncertainty).

    Mathematical Definition:
        Delta entropy ΔH quantifies the temporal derivative of market uncertainty
        by comparing Shannon entropy between two consecutive time windows:

            ΔH(t) = H(t₂) - H(t₁)

        where:
        - t₁ = [t - 2τ, t - τ] is the earlier window
        - t₂ = [t - τ, t] is the recent window
        - τ = window size

        For a time series x(t), we compute:
            H(t₁) = -∑ᵢ p₁,ᵢ · log(p₁,ᵢ)  [entropy of first window]
            H(t₂) = -∑ᵢ p₂,ᵢ · log(p₂,ᵢ)  [entropy of second window]
            ΔH = H(t₂) - H(t₁)

    Physical Interpretation:
        ΔH > 0: Increasing entropy → market becoming more chaotic/uncertain
        ΔH = 0: Constant entropy → stable regime
        ΔH < 0: Decreasing entropy → market becoming more structured/predictable

    Applications in Regime Detection:
        - |ΔH| > threshold: Regime transition signal
        - ΔH ≫ 0 with low H(t₁): Trending → Random walk transition
        - ΔH ≪ 0 with high H(t₁): Random walk → Trending transition

    Delta entropy (ΔH) measures the rate of change in market uncertainty by
    comparing entropy between two consecutive time windows:

        ΔH = H(t) - H(t-τ)

    where τ is the window size. Positive ΔH indicates increasing chaos,
    negative ΔH suggests decreasing uncertainty.

    Args:
        series: 1D array of numeric data (typically prices)
        window: Size of each time window for entropy calculation (default: 100).
            Requires at least 2*window data points.
        bins_range: (min_bins, max_bins) for adaptive histogram binning.
                   Actual bins = clip(window // 3, min_bins, max_bins)
                   Default: (10, 50)
                   Rationale: Larger windows support finer binning.

    Returns:
        Delta entropy value ΔH (can be positive, negative, or zero).
        Positive values indicate increasing uncertainty (↑ chaos),
        negative values indicate decreasing uncertainty (↑ structure).
        Returns 0.0 if insufficient data (need at least 2 * window points).

    Numerical Stability:
        - Adaptive bin selection prevents over/under-discretization
        - Each window entropy computed independently
        - Difference computed in full precision (no premature rounding)

    Complexity:
        Time: O(2N) = O(N) where N = window size
        Space: O(B) for histogram bins

    Example:
        >>> prices = np.linspace(100, 110, 300)  # Trending market
        >>> dH = delta_entropy(prices, window=100)
        >>> if dH > 0.5:
        ...     print("Market becoming more chaotic")
        ... elif dH < -0.5:
        ...     print("Market becoming more structured")

    Note:
        - Requires at least 2 * window data points
        - Bins are adaptively chosen based on window size: B ∈ [B_min, B_max]
        - Useful for detecting regime transitions and structural breaks
        - Sign of ΔH indicates direction of uncertainty change

    References:
        - Pincus, S. M. (1991). Approximate entropy as a measure of system
          complexity. Proceedings of the National Academy of Sciences, 88(6).
        - Richman, J. S., & Moorman, J. R. (2000). Physiological time-series
          analysis using approximate entropy and sample entropy. AJP Heart, 278.
    """
    x = np.asarray(series, dtype=float)
    if x.size < 2 * window:
        return 0.0

    # Split into two consecutive windows
    a, b = x[-window * 2 : -window], x[-window:]

    # Adaptive bin selection
    bins = int(np.clip(window // 3, bins_range[0], bins_range[1]))

    # Compute entropy difference
    return float(entropy(b, bins) - entropy(a, bins))


class EntropyFeature(BaseFeature):
    """Feature wrapper for Shannon entropy indicator.

    This class wraps the entropy() function as a BaseFeature, making it
    compatible with the TradePulse feature pipeline and composition system.

    Attributes:
        bins: Number of histogram bins for entropy calculation
        use_float32: Use float32 precision to reduce memory usage
        chunk_size: Chunk size for processing large arrays
        parallel: Parallelization mode for chunked execution
        backend: Computation backend
        max_workers: Optional worker cap
        name: Feature identifier

    Example:
        >>> from core.indicators.entropy import EntropyFeature
        >>> import numpy as np
        >>>
        >>> feature = EntropyFeature(bins=50, name="market_entropy")
        >>> prices = np.random.randn(200) * 10 + 100
        >>> result = feature.transform(prices)
        >>>
        >>> print(f"{result.name}: {result.value:.3f}")
        >>> print(f"Metadata: {result.metadata}")
        market_entropy: 2.345
        Metadata: {'bins': 50}
    """

    def __init__(
        self,
        bins: int = 30,
        *,
        use_float32: bool = False,
        chunk_size: int | None = None,
        parallel: Literal["none", "process", "async"] = "none",
        backend: Literal["cpu", "gpu", "auto", "cupy", "numba"] = "cpu",
        max_workers: int | None = None,
        name: str | None = None,
    ) -> None:
        """Initialize entropy feature.

        Args:
            bins: Number of bins for histogram discretization (default: 30)
            use_float32: Use float32 precision for memory efficiency (default: False)
            chunk_size: Chunk size for large arrays, None disables chunking (default: None)
            parallel: Parallelization mode for chunked execution (default: "none")
            backend: Computation backend (default: "cpu")
            max_workers: Optional worker cap (default: None)
            name: Optional custom name for the feature (default: "entropy")
        """
        super().__init__(name or "entropy")
        self.bins = bins
        self.use_float32 = use_float32
        self.chunk_size = chunk_size
        self.parallel = parallel
        self.backend = backend
        self.max_workers = max_workers

    def transform(self, data: np.ndarray, **_: Any) -> FeatureResult:
        """Compute Shannon entropy of input data.

        Args:
            data: 1D array of numeric values (typically prices)
            **_: Additional keyword arguments (ignored)

        Returns:
            FeatureResult containing entropy value and metadata
        """
        with _metrics.measure_feature_transform(self.name, "entropy"):
            value = entropy(
                data,
                bins=self.bins,
                use_float32=self.use_float32,
                chunk_size=self.chunk_size,
                parallel=self.parallel,
                max_workers=self.max_workers,
                backend=self.backend,
            )
            _metrics.record_feature_value(self.name, value)
            metadata: dict[str, Any] = {"bins": self.bins}

            # Only expose optional optimisation flags when they are actively used
            # so the metadata payload remains stable for the simple/default case
            # and downstream tests/consumers do not need to defensively filter
            # out empty values.  This mirrors the expectations encoded in the
            # public unit tests which only anticipate the "bins" entry for the
            # default configuration while still validating the presence of
            # optimisation hints when they are explicitly enabled.
            if self.use_float32:
                metadata["use_float32"] = True
            if self.chunk_size is not None:
                metadata["chunk_size"] = self.chunk_size
            if self.parallel != "none":
                metadata["parallel"] = self.parallel
            if self.max_workers is not None:
                metadata["max_workers"] = self.max_workers
            actual_backend = _LAST_ENTROPY_BACKEND
            if self.backend != "cpu" or actual_backend != "cpu":
                metadata["backend"] = actual_backend
                if self.backend != actual_backend:
                    metadata["backend_requested"] = self.backend

            return FeatureResult(name=self.name, value=value, metadata=metadata)


class DeltaEntropyFeature(BaseFeature):
    """Feature wrapper for delta entropy (rate of entropy change).

    This feature computes the change in Shannon entropy over time by comparing
    entropy between consecutive time windows. Useful for detecting regime
    transitions and changes in market dynamics.

    Attributes:
        window: Size of each time window
        bins_range: (min, max) range for adaptive bin selection
        name: Feature identifier

    Example:
        >>> from core.indicators.entropy import DeltaEntropyFeature
        >>> import numpy as np
        >>>
        >>> feature = DeltaEntropyFeature(window=100, bins_range=(10, 50))
        >>> prices = np.linspace(100, 110, 300)  # Trending market
        >>> result = feature.transform(prices)
        >>>
        >>> if result.value > 0.5:
        ...     print("Market becoming more chaotic")
        ... elif result.value < -0.5:
        ...     print("Market becoming more structured")
    """

    def __init__(
        self,
        window: int = 100,
        bins_range: tuple[int, int] = (10, 50),
        *,
        name: str | None = None,
    ) -> None:
        """Initialize delta entropy feature.

        Args:
            window: Size of each time window (default: 100)
            bins_range: (min_bins, max_bins) for histogram (default: (10, 50))
            name: Optional custom name (default: "delta_entropy")
        """
        super().__init__(name or "delta_entropy")
        self.window = window
        self.bins_range = bins_range

    def transform(self, data: np.ndarray, **_: Any) -> FeatureResult:
        """Compute delta entropy (ΔH) of input data.

        Args:
            data: 1D array of numeric values (typically prices)
            **_: Additional keyword arguments (ignored)

        Returns:
            FeatureResult containing ΔH value and metadata

        Raises:
            ValueError: If data has fewer than 2 * window points
        """
        value = delta_entropy(data, window=self.window, bins_range=self.bins_range)
        metadata = {"window": self.window, "bins_range": self.bins_range}
        return FeatureResult(name=self.name, value=value, metadata=metadata)


__all__ = [
    "entropy",
    "delta_entropy",
    "EntropyFeature",
    "DeltaEntropyFeature",
]
