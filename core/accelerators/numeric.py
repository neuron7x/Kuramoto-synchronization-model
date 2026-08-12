# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""High-performance numeric helpers with Rust accelerators and Python fallbacks."""

from __future__ import annotations

import logging
import math
import os
import threading
import time
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterable, Iterator, Sequence

try:  # pragma: no cover - optional dependency in some deployments
    import numpy as np
except ModuleNotFoundError:  # pragma: no cover - exercised in fallback tests
    np = None  # type: ignore[assignment]
    _NUMPY_AVAILABLE = False
else:  # pragma: no cover - default execution path when numpy is present
    _NUMPY_AVAILABLE = True

_logger = logging.getLogger(__name__)


class BackendSynchronizationError(RuntimeError):
    """Raised when strict backend synchronization cannot be maintained.

    The exception carries a structured forensic payload so that an audit
    consumer can tell *why* the dispatch refused without parsing the
    human-readable message:

    * ``backend`` — name of the accelerator that failed (``"rust"`` /
      ``"numpy"`` / ``"python"``).
    * ``reason`` — machine-readable cause. Canonical values:
      ``"unavailable"`` (extension not loaded), ``"runtime_error"``
      (extension raised), ``"numpy_missing"`` (dependency absent).
    * ``last_healthy_epoch_ns`` — wall-clock Unix-nanosecond timestamp
      of the most recent successful dispatch, or ``None`` if none has
      ever succeeded in this process.
    * ``downgrade_count`` — number of Rust→fallback downgrades the
      process has observed since start (or last counter reset).
    """

    def __init__(
        self,
        message: str,
        *,
        backend: str = "rust",
        reason: str = "unspecified",
        last_healthy_epoch_ns: int | None = None,
        downgrade_count: int = 0,
    ) -> None:
        super().__init__(message)
        self.backend = backend
        self.reason = reason
        self.last_healthy_epoch_ns = last_healthy_epoch_ns
        self.downgrade_count = downgrade_count

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable forensic snapshot of the failure."""
        return {
            "message": str(self),
            "backend": self.backend,
            "reason": self.reason,
            "last_healthy_epoch_ns": self.last_healthy_epoch_ns,
            "downgrade_count": self.downgrade_count,
        }


# ---------------------------------------------------------------------------
# Backend telemetry — lightweight, thread-safe, zero-dependency counters.
# ---------------------------------------------------------------------------

_DOWNGRADE_LOCK = threading.Lock()
_DOWNGRADE_COUNTER: Counter[tuple[str, str, str]] = Counter()
_LAST_HEALTHY_EPOCH_NS: dict[str, int] = {}


def _record_healthy(backend: str) -> None:
    """Mark ``backend`` as having produced a successful dispatch just now."""
    with _DOWNGRADE_LOCK:
        _LAST_HEALTHY_EPOCH_NS[backend] = time.time_ns()


def _record_downgrade(from_backend: str, to_backend: str, reason: str) -> int:
    """Increment and return the downgrade counter for this triple."""
    key = (from_backend, to_backend, reason)
    with _DOWNGRADE_LOCK:
        _DOWNGRADE_COUNTER[key] += 1
        return _DOWNGRADE_COUNTER[key]


def _get_last_healthy(backend: str) -> int | None:
    with _DOWNGRADE_LOCK:
        return _LAST_HEALTHY_EPOCH_NS.get(backend)


def _total_downgrades_from(backend: str) -> int:
    """Return total downgrades originating at ``backend`` across every target."""
    with _DOWNGRADE_LOCK:
        return sum(
            count for (frm, _to, _reason), count in _DOWNGRADE_COUNTER.items() if frm == backend
        )


def downgrade_counts() -> dict[tuple[str, str, str], int]:
    """Return a snapshot of the downgrade counter.

    External observers (Prometheus exporter, audit scraper) call this to
    read-without-reset. Keys are ``(from_backend, to_backend, reason)``.
    """
    with _DOWNGRADE_LOCK:
        return dict(_DOWNGRADE_COUNTER)


def reset_downgrade_counter() -> None:
    """Reset the downgrade counter and last-healthy registry.

    Test-only helper; production processes should never need this.
    """
    with _DOWNGRADE_LOCK:
        _DOWNGRADE_COUNTER.clear()
        _LAST_HEALTHY_EPOCH_NS.clear()


def _raise_sync_error(
    message: str,
    *,
    backend: str,
    reason: str,
) -> "BackendSynchronizationError":
    """Build a structured BackendSynchronizationError + record the downgrade.

    Returns the exception instance so callers can ``raise _raise_sync_error(...)
    from exc``.
    """
    count = _record_downgrade(backend, "abort", reason)
    return BackendSynchronizationError(
        message,
        backend=backend,
        reason=reason,
        last_healthy_epoch_ns=_get_last_healthy(backend),
        downgrade_count=count,
    )


# ---------------------------------------------------------------------------
# Process-wide strict-backend default — ``GEOSYNC_STRICT_BACKEND`` env flip.
# ---------------------------------------------------------------------------

_STRICT_BACKEND_ENV = "GEOSYNC_STRICT_BACKEND"


def _default_strict_backend() -> bool:
    """Return the process-wide default for ``strict_backend``.

    Resolution order (first hit wins):

    * Environment variable ``GEOSYNC_STRICT_BACKEND`` set to a truthy
      value (``"1"``, ``"true"``, ``"yes"``, ``"on"`` — case-insensitive)
      flips the default to ``True``. Production deployments set this
      once to make fail-closed the default without touching call
      sites.
    * Otherwise the legacy ``False`` default — fail-open fallback —
      keeps every existing caller working unchanged.
    """
    raw = os.environ.get(_STRICT_BACKEND_ENV, "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _resolve_strict(explicit: bool | None) -> bool:
    """Resolve the effective ``strict_backend`` for a call.

    A caller's explicit ``True`` / ``False`` always wins; ``None``
    means "use process default", which consults the env flag above.
    """
    if explicit is None:
        return _default_strict_backend()
    return bool(explicit)


# ---------------------------------------------------------------------------
# BackendHealth — scoped observability span, Prometheus-free.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BackendHealthReport:
    """Frozen snapshot of a ``BackendHealth`` span's observations."""

    label: str
    wall_duration_s: float
    downgrades: dict[tuple[str, str, str], int]
    last_healthy_epoch_ns: dict[str, int | None]

    @property
    def n_downgrades(self) -> int:
        return sum(self.downgrades.values())

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable form for audit ledgers."""
        return {
            "label": self.label,
            "wall_duration_s": self.wall_duration_s,
            "n_downgrades": self.n_downgrades,
            "downgrades": {
                f"{frm}->{to}:{reason}": count
                for (frm, to, reason), count in self.downgrades.items()
            },
            "last_healthy_epoch_ns": dict(self.last_healthy_epoch_ns),
        }


@contextmanager
def BackendHealth(label: str) -> Iterator["_HealthSpan"]:
    """Scoped observability span over an accelerator-using block.

    Usage::

        with BackendHealth("ingest-batch") as span:
            for frame in batch:
                sliding_windows(frame, 32, 8)
            report = span.report()
            emit_audit(report.to_dict())

    The span records:

    * wall-clock duration of the block,
    * downgrade delta (snapshot diff between enter / exit),
    * last-healthy-epoch per backend at exit.

    The caller reads the report explicitly — the span never writes to
    a global registry, so two spans can nest without contaminating
    each other.
    """
    span = _HealthSpan(label=label, started_ns=time.time_ns())
    span._enter_snapshot = downgrade_counts()
    try:
        yield span
    finally:
        span._exit_snapshot = downgrade_counts()
        span._wall_duration_s = (time.time_ns() - span.started_ns) / 1_000_000_000
        span._last_healthy = {
            backend: _get_last_healthy(backend) for backend in _LAST_HEALTHY_EPOCH_NS.keys()
        }


@dataclass
class _HealthSpan:
    """Mutable mid-span state that ``BackendHealth`` fills in on exit."""

    label: str
    started_ns: int
    _enter_snapshot: dict[tuple[str, str, str], int] | None = None
    _exit_snapshot: dict[tuple[str, str, str], int] | None = None
    _wall_duration_s: float = 0.0
    _last_healthy: dict[str, int | None] | None = None

    def report(self) -> BackendHealthReport:
        """Return the immutable observation snapshot.

        Must be called after the ``with`` block exits; calling during
        the block returns a zeroed report and ``_exit_snapshot is None``.
        """
        if self._exit_snapshot is None:
            # Span still in flight — return a zero-delta report.
            return BackendHealthReport(
                label=self.label,
                wall_duration_s=0.0,
                downgrades={},
                last_healthy_epoch_ns={},
            )
        entry = self._enter_snapshot or {}
        delta: dict[tuple[str, str, str], int] = {}
        for key, count in self._exit_snapshot.items():
            diff = count - entry.get(key, 0)
            if diff > 0:
                delta[key] = diff
        return BackendHealthReport(
            label=self.label,
            wall_duration_s=self._wall_duration_s,
            downgrades=delta,
            last_healthy_epoch_ns=self._last_healthy or {},
        )


try:  # pragma: no cover - optional acceleration module
    if _NUMPY_AVAILABLE:
        from geosync_accel import (
            convolve as _rust_convolve,
        )
        from geosync_accel import (
            quantiles as _rust_quantiles,
        )
        from geosync_accel import (
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

    if not (numpy_available() and rust_available() and _rust_sliding_windows is not None):
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


def _sliding_windows_python(arr: list[float], window: int, step: int) -> list[list[float]]:
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
    strict_backend: bool | None = None,
) -> np.ndarray:
    """Return a matrix of sliding windows over ``data``.

    Args:
        data: 1D input sequence.
        window: Size of each window (must be > 0).
        step: Step between windows (default: 1).
        use_rust: Attempt to dispatch to the Rust accelerator (default: True).
        strict_backend: Raise if Rust dispatch fails while ``use_rust`` is
            enabled. ``None`` (default) delegates to
            ``_default_strict_backend()`` which consults the
            ``GEOSYNC_STRICT_BACKEND`` env var.

    Returns:
        ``(n_windows, window)`` matrix of float64 windows.
    """

    strict_backend = _resolve_strict(strict_backend)
    if _NUMPY_AVAILABLE and np is not None:
        arr = _ensure_vector_numpy(data)
        if (
            use_rust
            and strict_backend
            and (not _RUST_ACCEL_AVAILABLE or _rust_sliding_windows is None)
        ):
            raise _raise_sync_error(
                "Rust sliding_windows backend unavailable with strict_backend=True",
                backend="rust",
                reason="unavailable",
            )
        if use_rust and _RUST_ACCEL_AVAILABLE and _rust_sliding_windows is not None:
            try:
                result = _rust_sliding_windows(arr, int(window), int(step))
                _record_healthy("rust")
                return result
            except Exception as exc:  # pragma: no cover - defensive fallback
                if strict_backend:
                    raise _raise_sync_error(
                        "Rust sliding_windows backend failed with strict_backend=True",
                        backend="rust",
                        reason="runtime_error",
                    ) from exc
                _record_downgrade("rust", "numpy", "runtime_error")
                _logger.warning(
                    "Rust sliding_windows failed (%s); falling back to NumPy.",
                    exc,
                )
        elif use_rust and not strict_backend and not _RUST_ACCEL_AVAILABLE:
            _record_downgrade("rust", "numpy", "unavailable")
        return _sliding_windows_numpy(arr, int(window), int(step))
    if use_rust and strict_backend:
        raise _raise_sync_error(
            "Rust sliding_windows backend requires NumPy and compiled extension "
            "when strict_backend=True",
            backend="rust",
            reason="numpy_missing",
        )
    if use_rust and not strict_backend:
        _record_downgrade("rust", "python", "numpy_missing")
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
    strict_backend: bool | None = None,
) -> np.ndarray:
    """Compute quantiles for ``data`` at the given probabilities.

    ``strict_backend=None`` delegates to ``GEOSYNC_STRICT_BACKEND`` env.
    """

    strict_backend = _resolve_strict(strict_backend)
    if _NUMPY_AVAILABLE and np is not None:
        arr = _ensure_vector_numpy(data)
        if use_rust and strict_backend and (not _RUST_ACCEL_AVAILABLE or _rust_quantiles is None):
            raise _raise_sync_error(
                "Rust quantiles backend unavailable with strict_backend=True",
                backend="rust",
                reason="unavailable",
            )
        if use_rust and _RUST_ACCEL_AVAILABLE and _rust_quantiles is not None:
            try:
                result = _rust_quantiles(arr, list(float(p) for p in probabilities))
                _record_healthy("rust")
                return np.asarray(result, dtype=np.float64)
            except Exception as exc:  # pragma: no cover - defensive fallback
                if strict_backend:
                    raise _raise_sync_error(
                        "Rust quantiles backend failed with strict_backend=True",
                        backend="rust",
                        reason="runtime_error",
                    ) from exc
                _record_downgrade("rust", "numpy", "runtime_error")
                _logger.warning(
                    "Rust quantiles failed (%s); falling back to NumPy.",
                    exc,
                )
        elif use_rust and not strict_backend and not _RUST_ACCEL_AVAILABLE:
            _record_downgrade("rust", "numpy", "unavailable")
        return _quantiles_numpy(arr, probabilities)
    if use_rust and strict_backend:
        raise _raise_sync_error(
            "Rust quantiles backend requires NumPy and compiled extension when strict_backend=True",
            backend="rust",
            reason="numpy_missing",
        )
    if use_rust and not strict_backend:
        _record_downgrade("rust", "python", "numpy_missing")
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
    if any(isinstance(v, Sequence) and not isinstance(v, (str, bytes, bytearray)) for v in signal):
        raise ValueError("convolution inputs must be 1-dimensional")
    if any(isinstance(v, Sequence) and not isinstance(v, (str, bytes, bytearray)) for v in kernel):
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
    strict_backend: bool | None = None,
) -> np.ndarray:
    """Convolve ``signal`` with ``kernel`` using the requested mode.

    ``strict_backend=None`` delegates to ``GEOSYNC_STRICT_BACKEND`` env.
    """

    strict_backend = _resolve_strict(strict_backend)
    if _NUMPY_AVAILABLE and np is not None:
        signal_arr = _ensure_vector_numpy(signal)
        kernel_arr = _ensure_vector_numpy(kernel)
        if use_rust and strict_backend and (not _RUST_ACCEL_AVAILABLE or _rust_convolve is None):
            raise _raise_sync_error(
                "Rust convolve backend unavailable with strict_backend=True",
                backend="rust",
                reason="unavailable",
            )
        if use_rust and _RUST_ACCEL_AVAILABLE and _rust_convolve is not None:
            try:
                result = _rust_convolve(signal_arr, kernel_arr, mode)
                _record_healthy("rust")
                return result
            except Exception as exc:  # pragma: no cover - defensive fallback
                if strict_backend:
                    raise _raise_sync_error(
                        "Rust convolve backend failed with strict_backend=True",
                        backend="rust",
                        reason="runtime_error",
                    ) from exc
                _record_downgrade("rust", "numpy", "runtime_error")
                _logger.warning(
                    "Rust convolve failed (%s); falling back to NumPy.",
                    exc,
                )
        elif use_rust and not strict_backend and not _RUST_ACCEL_AVAILABLE:
            _record_downgrade("rust", "numpy", "unavailable")
        return _convolve_numpy(signal_arr, kernel_arr, mode=mode)
    if use_rust and strict_backend:
        raise _raise_sync_error(
            "Rust convolve backend requires NumPy and compiled extension when strict_backend=True",
            backend="rust",
            reason="numpy_missing",
        )
    if use_rust and not strict_backend:
        _record_downgrade("rust", "python", "numpy_missing")
    signal_list = _ensure_vector_python(signal)
    kernel_list = _ensure_vector_python(kernel)
    return _convolve_python(signal_list, kernel_list, mode=mode)


__all__ = [
    "BackendHealth",
    "BackendHealthReport",
    "BackendSynchronizationError",
    "convolve",
    "convolve_numpy_backend",
    "convolve_python_backend",
    "convolve_rust_backend",
    "downgrade_counts",
    "numpy_available",
    "quantiles",
    "quantiles_numpy_backend",
    "quantiles_python_backend",
    "quantiles_rust_backend",
    "reset_downgrade_counter",
    "rust_available",
    "sliding_windows",
    "sliding_windows_numpy_backend",
    "sliding_windows_python_backend",
    "sliding_windows_rust_backend",
]
