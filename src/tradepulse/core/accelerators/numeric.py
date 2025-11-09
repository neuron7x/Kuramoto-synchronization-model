"""High-performance numeric helpers with Rust accelerators and Python fallbacks."""

from __future__ import annotations

import logging
import math
from typing import Iterable, Sequence

try:  # pragma: no cover - optional dependency in some deployments
    import numpy as np
except ModuleNotFoundError:  # pragma: no cover - exercised in fallback tests
    np = None  # type: ignore[assignment]
    _NUMPY_AVAILABLE = False
else:  # pragma: no cover - default execution path when numpy is present
    _NUMPY_AVAILABLE = True

_logger = logging.getLogger(__name__)

try:  # pragma: no cover - optional acceleration module
    if _NUMPY_AVAILABLE:
        from tradepulse_accel import (
            convolve as _rust_convolve,
        )
        from tradepulse_accel import (
            quantiles as _rust_quantiles,
        )
        from tradepulse_accel import (
            sliding_windows as _rust_sliding_windows,
        )

        _RUST_ACCEL_AVAILABLE = True
    else:
        raise ImportError("Rust accelerators require numpy")
except Exception:  # pragma: no cover - rust extension not built or numpy missing
    _rust_convolve = None
    _rust_quantiles = None
    _rust_sliding_windows = None
    _RUST_ACCEL_AVAILABLE = False


def numpy_available() -> bool:
    """Return ``True`` when NumPy is importable."""

    return bool(_NUMPY_AVAILABLE and np is not None)


def rust_available() -> bool:
    """Return ``True`` when the compiled Rust extension is importable."""

    return bool(_RUST_ACCEL_AVAILABLE)


def _ensure_vector_numpy(data: Sequence[float] | np.ndarray) -> "np.ndarray":
    arr = np.ascontiguousarray(data, dtype=np.float64)
    if arr.ndim != 1:
        raise ValueError("input must be 1-dimensional")
    return arr


def _ensure_vector_python(data: Iterable[float]) -> list[float]:
    result: list[float] = []
    for item in data:
        if isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)):
            raise ValueError("input must be 1-dimensional")
        result.append(float(item))
    return result


def sliding_windows_python_backend(
    data: Iterable[float],
    window: int,
    step: int,
) -> list[list[float]]:
    """Pure-Python sliding window helper for benchmarking and fallbacks."""

    arr_list = _ensure_vector_python(data)
    return _sliding_windows_python(arr_list, int(window), int(step))


def sliding_windows_numpy_backend(
    data: Sequence[float] | np.ndarray,
    window: int,
    step: int,
) -> "np.ndarray":
    """NumPy implementation of :func:`sliding_windows`."""

    if not numpy_available():
        raise RuntimeError("NumPy backend requested but NumPy is not available")
    arr = _ensure_vector_numpy(data)
    return _sliding_windows_numpy(arr, int(window), int(step))


def sliding_windows_rust_backend(
    data: Sequence[float] | np.ndarray,
    window: int,
    step: int,
) -> "np.ndarray":
    """Rust-accelerated implementation of :func:`sliding_windows`."""

    if not (
        numpy_available() and rust_available() and _rust_sliding_windows is not None
    ):
        raise RuntimeError("Rust backend requested but the extension is not available")
    arr = _ensure_vector_numpy(data)
    return _rust_sliding_windows(arr, int(window), int(step))


def _sliding_windows_numpy(arr: "np.ndarray", window: int, step: int) -> "np.ndarray":
    if window <= 0:
        raise ValueError("window must be greater than zero")
    if step <= 0:
        raise ValueError("step must be greater than zero")
    if arr.size < window:
        return np.empty((0, window), dtype=np.float64)
    view = np.lib.stride_tricks.sliding_window_view(arr, window)
    if step != 1:
        view = view[::step]
    return np.array(view, copy=True)


def _sliding_windows_python(
    arr: list[float], window: int, step: int
) -> list[list[float]]:
    if window <= 0:
        raise ValueError("window must be greater than zero")
    if step <= 0:
        raise ValueError("step must be greater than zero")
    if len(arr) < window:
        return []
    result: list[list[float]] = []
    for start in range(0, len(arr) - window + 1, step):
        result.append(arr[start : start + window].copy())
    return result


def sliding_windows(
    data: Sequence[float] | np.ndarray,
    window: int,
    step: int = 1,
    *,
    use_rust: bool = True,
) -> np.ndarray:
    """Return a matrix of sliding windows over ``data``.

    Args:
        data: 1D input sequence.
        window: Size of each window (must be > 0).
        step: Step between windows (default: 1).
        use_rust: Attempt to dispatch to the Rust accelerator (default: True).

    Returns:
        ``(n_windows, window)`` matrix of float64 windows.
    """

    if _NUMPY_AVAILABLE and np is not None:
        arr = _ensure_vector_numpy(data)
        if use_rust and _RUST_ACCEL_AVAILABLE and _rust_sliding_windows is not None:
            try:
                return _rust_sliding_windows(arr, int(window), int(step))
            except Exception as exc:  # pragma: no cover - defensive fallback
                _logger.warning(
                    "Rust sliding_windows failed (%s); falling back to NumPy.",
                    exc,
                )
        return _sliding_windows_numpy(arr, int(window), int(step))
    arr_list = _ensure_vector_python(data)
    return _sliding_windows_python(arr_list, int(window), int(step))


def _quantiles_numpy(arr: "np.ndarray", probabilities: Sequence[float]) -> "np.ndarray":
    probs = np.asarray(list(probabilities), dtype=np.float64)
    if probs.ndim != 1:
        raise ValueError("probabilities must be a 1D sequence")
    if np.any(~np.isfinite(probs)):
        raise ValueError("probabilities must be finite")
    if np.any((probs < 0.0) | (probs > 1.0)):
        raise ValueError("probabilities must be within [0, 1]")
    if arr.size == 0:
        return np.full(probs.shape, np.nan, dtype=np.float64)
    return np.quantile(arr, probs, method="linear")


def _quantiles_python(arr: list[float], probabilities: Sequence[float]) -> list[float]:
    probs = [float(p) for p in probabilities]
    if any(not math.isfinite(p) for p in probs):
        raise ValueError("probabilities must be finite")
    if any((p < 0.0) or (p > 1.0) for p in probs):
        raise ValueError("probabilities must be within [0, 1]")
    if not arr:
        return [float("nan")] * len(probs)
    sorted_arr = sorted(arr)
    n = len(sorted_arr)
    results: list[float] = []
    for q in probs:
        position = q * (n - 1)
        lower_index = int(position)
        upper_index = lower_index if position.is_integer() else lower_index + 1
        if upper_index >= n:
            upper_index = n - 1
        lower = sorted_arr[lower_index]
        upper = sorted_arr[upper_index]
        if upper_index == lower_index:
            results.append(float(lower))
            continue
        weight = position - lower_index
        results.append(float(lower + (upper - lower) * weight))
    return results


def quantiles_python_backend(
    data: Iterable[float],
    probabilities: Sequence[float],
) -> list[float]:
    """Pure-Python implementation of :func:`quantiles`."""

    arr_list = _ensure_vector_python(data)
    return _quantiles_python(arr_list, probabilities)


def quantiles_numpy_backend(
    data: Sequence[float] | np.ndarray,
    probabilities: Sequence[float],
) -> "np.ndarray":
    """NumPy implementation of :func:`quantiles`."""

    if not numpy_available():
        raise RuntimeError("NumPy backend requested but NumPy is not available")
    arr = _ensure_vector_numpy(data)
    return _quantiles_numpy(arr, probabilities)


def quantiles_rust_backend(
    data: Sequence[float] | np.ndarray,
    probabilities: Sequence[float],
) -> "np.ndarray":
    """Rust-accelerated implementation of :func:`quantiles`."""

    if not (numpy_available() and rust_available() and _rust_quantiles is not None):
        raise RuntimeError("Rust backend requested but the extension is not available")
    arr = _ensure_vector_numpy(data)
    result = _rust_quantiles(arr, list(float(p) for p in probabilities))
    return np.asarray(result, dtype=np.float64)


def quantiles(
    data: Sequence[float] | np.ndarray,
    probabilities: Sequence[float] | np.ndarray,
    *,
    use_rust: bool = True,
) -> np.ndarray:
    """Compute quantiles for ``data`` at the given probabilities."""

    if _NUMPY_AVAILABLE and np is not None:
        arr = _ensure_vector_numpy(data)
        if use_rust and _RUST_ACCEL_AVAILABLE and _rust_quantiles is not None:
            try:
                result = _rust_quantiles(arr, list(float(p) for p in probabilities))
                return np.asarray(result, dtype=np.float64)
            except Exception as exc:  # pragma: no cover - defensive fallback
                _logger.warning(
                    "Rust quantiles failed (%s); falling back to NumPy.",
                    exc,
                )
        return _quantiles_numpy(arr, probabilities)
    arr_list = _ensure_vector_python(data)
    return _quantiles_python(arr_list, probabilities)


def _convolve_numpy(
    signal: "np.ndarray",
    kernel: "np.ndarray",
    *,
    mode: str = "full",
) -> np.ndarray:
    if signal.ndim != 1 or kernel.ndim != 1:
        raise ValueError("convolution inputs must be 1-dimensional")
    return np.convolve(signal, kernel, mode=mode)


def _convolve_python(
    signal: list[float],
    kernel: list[float],
    *,
    mode: str = "full",
) -> list[float]:
    if not signal:
        raise ValueError("convolution signal must not be empty")
    if not kernel:
        raise ValueError("convolution kernel must not be empty")
    if any(
        isinstance(v, Sequence) and not isinstance(v, (str, bytes, bytearray))
        for v in signal
    ):
        raise ValueError("convolution inputs must be 1-dimensional")
    if any(
        isinstance(v, Sequence) and not isinstance(v, (str, bytes, bytearray))
        for v in kernel
    ):
        raise ValueError("convolution inputs must be 1-dimensional")
    n = len(signal)
    m = len(kernel)
    full_length = n + m - 1
    full = [0.0] * full_length
    for i, a in enumerate(signal):
        for j, b in enumerate(kernel):
            full[i + j] += float(a) * float(b)
    if mode == "full":
        return full
    if mode == "same":
        target_len = max(n, m)
        trim = full_length - target_len
        start = trim // 2
        end = start + target_len
        return full[start:end]
    if mode == "valid":
        target_len = max(n, m) - min(n, m) + 1
        if target_len <= 0:
            return []
        start = m - 1 if n >= m else n - 1
        end = start + target_len
        return full[start:end]
    raise ValueError(f"invalid convolution mode: {mode}")


def convolve_python_backend(
    signal: Iterable[float],
    kernel: Iterable[float],
    *,
    mode: str = "full",
) -> list[float]:
    """Pure-Python implementation of :func:`convolve`."""

    signal_list = _ensure_vector_python(signal)
    kernel_list = _ensure_vector_python(kernel)
    return _convolve_python(signal_list, kernel_list, mode=mode)


def convolve_numpy_backend(
    signal: Sequence[float] | np.ndarray,
    kernel: Sequence[float] | np.ndarray,
    *,
    mode: str = "full",
) -> "np.ndarray":
    """NumPy implementation of :func:`convolve`."""

    if not numpy_available():
        raise RuntimeError("NumPy backend requested but NumPy is not available")
    signal_arr = _ensure_vector_numpy(signal)
    kernel_arr = _ensure_vector_numpy(kernel)
    return _convolve_numpy(signal_arr, kernel_arr, mode=mode)


def convolve_rust_backend(
    signal: Sequence[float] | np.ndarray,
    kernel: Sequence[float] | np.ndarray,
    *,
    mode: str = "full",
) -> "np.ndarray":
    """Rust-accelerated implementation of :func:`convolve`."""

    if not (numpy_available() and rust_available() and _rust_convolve is not None):
        raise RuntimeError("Rust backend requested but the extension is not available")
    signal_arr = _ensure_vector_numpy(signal)
    kernel_arr = _ensure_vector_numpy(kernel)
    return _rust_convolve(signal_arr, kernel_arr, mode)


def convolve(
    signal: Sequence[float] | np.ndarray,
    kernel: Sequence[float] | np.ndarray,
    *,
    mode: str = "full",
    use_rust: bool = True,
) -> np.ndarray:
    """Convolve ``signal`` with ``kernel`` using the requested mode."""

    if _NUMPY_AVAILABLE and np is not None:
        signal_arr = _ensure_vector_numpy(signal)
        kernel_arr = _ensure_vector_numpy(kernel)
        if use_rust and _RUST_ACCEL_AVAILABLE and _rust_convolve is not None:
            try:
                return _rust_convolve(signal_arr, kernel_arr, mode)
            except Exception as exc:  # pragma: no cover - defensive fallback
                _logger.warning(
                    "Rust convolve failed (%s); falling back to NumPy.",
                    exc,
                )
        return _convolve_numpy(signal_arr, kernel_arr, mode=mode)

    signal_list = _ensure_vector_python(signal)
    kernel_list = _ensure_vector_python(kernel)
    return _convolve_python(signal_list, kernel_list, mode=mode)


__all__ = [
    "sliding_windows",
    "quantiles",
    "convolve",
    "numpy_available",
    "rust_available",
    "sliding_windows_python_backend",
    "sliding_windows_numpy_backend",
    "sliding_windows_rust_backend",
    "quantiles_python_backend",
    "quantiles_numpy_backend",
    "quantiles_rust_backend",
    "convolve_python_backend",
    "convolve_numpy_backend",
    "convolve_rust_backend",
]
