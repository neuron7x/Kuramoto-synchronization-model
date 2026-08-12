# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Microbenchmark: ``build_capital_weighted_adjacency`` runtime sweep.

We measure the cost of constructing a beta-modulated coupling matrix from a
baseline adjacency and an L2 depth snapshot at:

* ``N`` (instrument count) in ``{16, 64, 256, 1024, 4096}``;
* ``L`` (book levels) in ``{1, 5, 20}``;

and contrast it against a *trivial baseline-coupling* cost (a no-op symmetric
copy of the baseline adjacency). The trivial cost is reported alongside the
beta build cost so the multiplicative overhead is explicit.

Determinism is enforced by ``SEED`` from :mod:`bench.research_extensions`.
"""

from __future__ import annotations

import time
from typing import Any, Final, cast

import numpy as np
from numpy.typing import NDArray

from core.kuramoto.capital_weighted import (
    CapitalWeightedCouplingConfig,
    L2DepthSnapshot,
    build_capital_weighted_adjacency,
)

from . import SEED
from ._timing import BenchFailure, BenchOutcome, measure, safe_run, summarize

__all__ = [
    "BenchFailure",
    "BenchOutcome",
    "CONFIG_SIZES",
    "CONFIG_LEVELS",
    "build_baseline_inputs",
    "run_bench",
]


CONFIG_SIZES: Final[tuple[int, ...]] = (16, 64, 256, 1024, 4096)
CONFIG_LEVELS: Final[tuple[int, ...]] = (1, 5, 20)


def build_baseline_inputs(
    n: int,
    n_levels: int,
    *,
    seed: int,
) -> tuple[NDArray[np.float64], L2DepthSnapshot, int, CapitalWeightedCouplingConfig]:
    """Return ``(baseline_adj, snapshot, signal_ts, cfg)`` for the bench.

    The baseline is a fully connected, symmetric, zero-diagonal random matrix
    in ``[0, 1]``. The snapshot has timestamp ``0`` and a ``signal_timestamp``
    of ``1`` so the look-ahead guard never trips.
    """
    if n <= 0 or n_levels <= 0:
        raise ValueError("n and n_levels must be > 0.")

    rng = np.random.default_rng(seed)

    raw = rng.random((n, n), dtype=np.float64)
    baseline = 0.5 * (raw + raw.T)
    np.fill_diagonal(baseline, 0.0)

    bid_sizes = rng.random((n, n_levels), dtype=np.float64) * 100.0
    ask_sizes = rng.random((n, n_levels), dtype=np.float64) * 100.0
    mid_prices = 1.0 + rng.random(n, dtype=np.float64) * 100.0

    snapshot = L2DepthSnapshot(
        timestamp_ns=0,
        bid_sizes=bid_sizes.astype(np.float64),
        ask_sizes=ask_sizes.astype(np.float64),
        mid_prices=mid_prices.astype(np.float64),
    )
    cfg = CapitalWeightedCouplingConfig()
    return baseline, snapshot, 1, cfg


def _trivial_baseline_copy(baseline: NDArray[np.float64]) -> None:
    """Reference cost of a symmetric, zero-diagonal copy.

    This is the *cheapest possible* coupling-matrix construction (a no-op that
    only enforces the structural constraints). It bounds the overhead added
    by the beta envelope and the gini-derived scalar.
    """
    out = baseline.astype(np.float64, copy=True)
    out = 0.5 * (out + out.T)
    np.fill_diagonal(out, 0.0)
    # Touch the result so the optimiser cannot eliminate the work.
    if out.shape[0] > 0:
        _ = float(out[0, 0])


def _run_one(n: int, n_levels: int) -> BenchOutcome | BenchFailure:
    config: dict[str, object] = {"N": n, "L": n_levels, "seed": SEED}

    def body() -> BenchOutcome:
        baseline, snapshot, signal_ts, cfg = build_baseline_inputs(n, n_levels, seed=SEED)

        # Sanity: the build must produce a finite, symmetric matrix the same shape
        # as the baseline. We only check once outside the timing loop.
        result = build_capital_weighted_adjacency(baseline, snapshot, signal_ts, cfg)
        if result.coupling.shape != baseline.shape:
            raise RuntimeError(
                f"build_capital_weighted_adjacency returned shape "
                f"{result.coupling.shape} != baseline {baseline.shape}."
            )

        beta_samples = measure(
            lambda: build_capital_weighted_adjacency(baseline, snapshot, signal_ts, cfg)
        )
        beta_summary = summarize(beta_samples)

        baseline_samples = measure(lambda: _trivial_baseline_copy(baseline))
        baseline_summary = summarize(baseline_samples)

        overhead_ratio = (
            beta_summary["median_ns"] / baseline_summary["median_ns"]
            if baseline_summary["median_ns"] > 0.0
            else float("inf")
        )

        return BenchOutcome(
            config=config,
            samples_ns=tuple(beta_samples),
            summary=beta_summary,
            extras={
                "baseline_summary": dict(baseline_summary),
                "overhead_ratio_median": overhead_ratio,
                "beta_applied": float(result.beta),
                "used_fallback": bool(result.used_fallback),
            },
        )

    return safe_run(f"capital_weighted[N={n},L={n_levels}]", config, body)


def run_bench() -> dict[str, object]:
    """Run the full ``(N, L)`` sweep and return a JSON-friendly payload."""
    started = time.perf_counter_ns()
    outcomes: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []

    for n in CONFIG_SIZES:
        for n_levels in CONFIG_LEVELS:
            res = _run_one(n, n_levels)
            if isinstance(res, BenchOutcome):
                outcomes.append(
                    {
                        "config": res.config,
                        "summary": dict(res.summary),
                        "extras": res.extras,
                        "samples_ns": list(res.samples_ns),
                    }
                )
            else:
                failures.append(
                    {
                        "config": res.config,
                        "error_type": res.error_type,
                        "error_message": res.error_message,
                        "traceback": res.traceback_str,
                    }
                )

    elapsed_ns = time.perf_counter_ns() - started
    return {
        "name": "bench_capital_weighted",
        "module": "core.kuramoto.capital_weighted",
        "function": "build_capital_weighted_adjacency",
        "elapsed_total_ns": int(elapsed_ns),
        "configurations": outcomes,
        "failures": failures,
    }


def main() -> None:  # pragma: no cover - CLI entry point.
    payload = run_bench()
    name = str(payload["name"])
    configurations = cast(list[dict[str, Any]], payload["configurations"])
    failures = cast(list[dict[str, Any]], payload["failures"])

    summary_lines: list[str] = [f"=== {name} ==="]
    for entry in configurations:
        cfg = entry["config"]
        summ = entry["summary"]
        extras = entry["extras"]
        summary_lines.append(
            f"N={cfg['N']:>5} L={cfg['L']:>3} "
            f"median={summ['median_ms']:7.3f} ms  p99={summ['p99_ms']:7.3f} ms  "
            f"baseline={extras['baseline_summary']['median_ms']:7.4f} ms  "
            f"overhead_ratio={extras['overhead_ratio_median']:6.2f}x"
        )
    for fail in failures:
        summary_lines.append(
            f"FAIL {fail['config']}: {fail['error_type']}: {fail['error_message']}"
        )
    print("\n".join(summary_lines))


if __name__ == "__main__":  # pragma: no cover - CLI entry point.
    main()
