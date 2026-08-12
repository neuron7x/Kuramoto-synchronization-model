# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Shared timing primitives for the research-extension microbenchmarks.

Every benchmark in this package consumes the same primitives so that the
emitted JSON is structurally homogeneous and trivially join-able.

Public API
----------
* :func:`measure` — run a callable, return wall-time samples in nanoseconds.
* :func:`summarize` — turn a sample list into median / p99 / mean / stdev.
* :func:`fit_loglog_slope` — least-squares slope of ``log(y)`` vs ``log(x)``.
* :func:`safe_run` — execute a benchmark with traceback capture.
"""

from __future__ import annotations

import math
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, TypedDict

import numpy as np
from numpy.typing import NDArray

from . import MAX_WALL_NS, MEASURE_ITERS, WARMUP_ITERS

__all__ = [
    "TimingSummary",
    "BenchOutcome",
    "BenchFailure",
    "measure",
    "summarize",
    "fit_loglog_slope",
    "safe_run",
]


_NS_PER_MS: Final[float] = 1_000_000.0
_NS_PER_US: Final[float] = 1_000.0


class TimingSummary(TypedDict):
    """JSON-friendly view of a measured-sample distribution."""

    n_samples: int
    median_ns: float
    p99_ns: float
    mean_ns: float
    std_ns: float
    min_ns: float
    max_ns: float
    median_ms: float
    p99_ms: float
    median_us: float


@dataclass(frozen=True, slots=True)
class BenchOutcome:
    """Successful measurement of a single configuration."""

    config: dict[str, object]
    samples_ns: tuple[int, ...]
    summary: TimingSummary
    extras: dict[str, object]


@dataclass(frozen=True, slots=True)
class BenchFailure:
    """Captured failure for one configuration (recorded, not raised)."""

    config: dict[str, object]
    error_type: str
    error_message: str
    traceback_str: str


def measure(
    func: Callable[[], object],
    *,
    warmup: int = WARMUP_ITERS,
    iters: int = MEASURE_ITERS,
    max_wall_ns: int = MAX_WALL_NS,
) -> list[int]:
    """Run ``func`` and return wall-time samples in nanoseconds.

    ``func`` may return any object — return values are intentionally ignored
    so the same primitive measures both side-effecting and pure callables.

    The function executes ``warmup`` un-recorded iterations and then up to
    ``iters`` measured iterations. The loop terminates early when the cumulative
    wall time exceeds ``max_wall_ns`` so that very slow configurations cannot
    block the suite indefinitely.
    """
    if warmup < 0 or iters < 1:
        raise ValueError("warmup must be >= 0 and iters must be >= 1.")

    for _ in range(warmup):
        func()

    samples: list[int] = []
    elapsed = 0
    for _ in range(iters):
        t0 = time.perf_counter_ns()
        func()
        dt = time.perf_counter_ns() - t0
        samples.append(int(dt))
        elapsed += int(dt)
        if elapsed >= max_wall_ns:
            break

    if not samples:
        raise RuntimeError("measure: no samples collected (iters must be >= 1).")
    return samples


def summarize(samples_ns: list[int]) -> TimingSummary:
    """Reduce a list of nanosecond samples to a JSON-serialisable summary.

    Percentiles use ``numpy.percentile`` with ``linear`` interpolation so that
    small sample counts still yield a defined p99.
    """
    if not samples_ns:
        raise ValueError("summarize: samples_ns must not be empty.")
    arr = np.asarray(samples_ns, dtype=np.float64)
    median = float(np.median(arr))
    p99 = float(np.percentile(arr, 99.0))
    mean = float(arr.mean())
    std = float(arr.std(ddof=0))
    return TimingSummary(
        n_samples=int(arr.size),
        median_ns=median,
        p99_ns=p99,
        mean_ns=mean,
        std_ns=std,
        min_ns=float(arr.min()),
        max_ns=float(arr.max()),
        median_ms=median / _NS_PER_MS,
        p99_ms=p99 / _NS_PER_MS,
        median_us=median / _NS_PER_US,
    )


def fit_loglog_slope(
    xs: list[float] | NDArray[np.float64],
    ys: list[float] | NDArray[np.float64],
) -> tuple[float, float]:
    """Return ``(slope, intercept)`` of a least-squares fit on log-log axes.

    Inputs are filtered to strictly positive entries before the log transform.
    Raises :class:`ValueError` when fewer than two positive points remain.
    """
    x_arr = np.asarray(xs, dtype=np.float64)
    y_arr = np.asarray(ys, dtype=np.float64)
    if x_arr.shape != y_arr.shape:
        raise ValueError("xs and ys must share shape.")
    mask = (x_arr > 0.0) & (y_arr > 0.0) & np.isfinite(x_arr) & np.isfinite(y_arr)
    if int(mask.sum()) < 2:
        raise ValueError("fit_loglog_slope needs at least two positive (x, y) pairs.")
    lx = np.log(x_arr[mask])
    ly = np.log(y_arr[mask])
    # numpy.polyfit deg=1 returns [slope, intercept]; use numerically stable lstsq.
    A = np.vstack([lx, np.ones_like(lx)]).T
    sol, *_ = np.linalg.lstsq(A, ly, rcond=None)
    slope = float(sol[0])
    intercept = float(sol[1])
    if not (math.isfinite(slope) and math.isfinite(intercept)):
        raise RuntimeError("fit_loglog_slope produced non-finite parameters.")
    return slope, intercept


def safe_run(
    name: str,
    config: dict[str, object],
    body: Callable[[], BenchOutcome],
) -> BenchOutcome | BenchFailure:
    """Execute ``body`` and return either an outcome or a captured failure.

    A ``BenchFailure`` is returned (not raised) so the JSON dump always
    contains every requested configuration with full diagnostic context.
    The ``name`` argument is recorded inside the traceback string for
    cross-reference with the run-all log.
    """
    try:
        return body()
    except Exception as exc:  # noqa: BLE001 — capture every failure into JSON.
        return BenchFailure(
            config=config,
            error_type=type(exc).__name__,
            error_message=f"[{name}] {exc!s}",
            traceback_str=traceback.format_exc(),
        )
