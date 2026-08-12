# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Microbenchmark: ``ricci_flow_with_surgery`` per-step cost.

We measure on Erdos-Renyi graphs at ``N`` in ``{16, 64, 256, 1024}`` and edge
probability ``p`` in ``{0.05, 0.1, 0.3}``. For each ``(N, p)`` we record:

* ``per_step_total`` — cost of one combined ``ricci_flow_with_surgery`` call;
* ``per_step_flow_only`` — cost of ``discrete_ricci_flow_step`` alone;
* ``per_step_surgery_only`` — cost of ``apply_neckpinch_surgery`` alone;
* ``surgery_fraction_vs_time`` — fraction of edges touched by surgery in
  each of 10 sequential ``ricci_flow_with_surgery`` invocations.

The curvature input is a deterministic function of edge weight (a small
synthetic ``kappa = 1 - 2*w_ij`` mapping) so the bench remains deterministic
without depending on the upstream Ollivier-Ricci computation.
"""

from __future__ import annotations

import time
from typing import Any, Final, cast

import numpy as np
from numpy.typing import NDArray

from core.kuramoto.ricci_flow import (
    RicciFlowConfig,
    apply_neckpinch_surgery,
    discrete_ricci_flow_step,
    ricci_flow_with_surgery,
)

from . import SEED
from ._timing import BenchFailure, BenchOutcome, measure, safe_run, summarize

__all__ = [
    "BenchFailure",
    "BenchOutcome",
    "CONFIG_SIZES",
    "CONFIG_PROBS",
    "build_er_weights",
    "synthetic_curvature",
    "run_bench",
]


CONFIG_SIZES: Final[tuple[int, ...]] = (16, 64, 256, 1024)
CONFIG_PROBS: Final[tuple[float, ...]] = (0.05, 0.1, 0.3)
SURGERY_TRACE_STEPS: Final[int] = 10


def build_er_weights(n: int, p: float, *, seed: int) -> NDArray[np.float64]:
    """Return a symmetric, zero-diagonal Erdos-Renyi weight matrix.

    Edge weights are drawn from ``Uniform(0.1, 1.0)`` only on edges sampled
    by the Bernoulli mask. The minimum edge weight (0.1) keeps the surgery
    threshold (default ``eps_weight=1e-8``) inert until the flow drives a
    weight down explicitly.
    """
    if n <= 0:
        raise ValueError("n must be > 0.")
    if not (0.0 <= p <= 1.0):
        raise ValueError("p must be in [0, 1].")

    rng = np.random.default_rng(seed)
    upper = np.triu(rng.random((n, n), dtype=np.float64), k=1)
    mask = (upper > 0.0) & (upper < p)
    weights = np.where(mask, 0.1 + 0.9 * rng.random((n, n), dtype=np.float64), 0.0)
    weights = np.triu(weights, k=1)
    weights = weights + weights.T
    np.fill_diagonal(weights, 0.0)
    return weights.astype(np.float64, copy=False)


def synthetic_curvature(
    weights: NDArray[np.float64],
    *,
    base: float = 0.2,
) -> dict[tuple[int, int], float]:
    """Deterministic synthetic Ollivier-Ricci-like curvature dict.

    The mapping ``kappa_ij = base - 2 * w_ij`` is in ``[-2, base]`` and so
    occasionally produces edges in the singular tail (kappa <= -1 + eps_neck)
    once the flow shrinks weights — exercising the surgery path. The function
    is symmetric and only emits ``i < j`` keys to match the registry contract.
    """
    if weights.ndim != 2 or weights.shape[0] != weights.shape[1]:
        raise ValueError("weights must be a square matrix.")
    n = int(weights.shape[0])
    out: dict[tuple[int, int], float] = {}
    iu, ju = np.triu_indices(n, k=1)
    w_vals = weights[iu, ju]
    for i, j, w in zip(iu.tolist(), ju.tolist(), w_vals.tolist(), strict=True):
        if w > 0.0:
            kappa = base - 2.0 * float(w)
            out[(int(i), int(j))] = kappa
    return out


def _count_active_edges(weights: NDArray[np.float64]) -> int:
    n = int(weights.shape[0])
    iu, ju = np.triu_indices(n, k=1)
    return int(np.count_nonzero(weights[iu, ju] > 0.0))


def _run_one(n: int, p: float) -> BenchOutcome | BenchFailure:
    config: dict[str, object] = {"N": n, "p": p, "seed": SEED}

    def body() -> BenchOutcome:
        weights = build_er_weights(n, p, seed=SEED)
        kappa = synthetic_curvature(weights)
        cfg = RicciFlowConfig(
            eta=0.05,
            eps_weight=1e-8,
            eps_neck=1e-3,
            preserve_total_edge_mass=True,
            preserve_connectedness=True,
            allow_disconnect=False,
            max_surgery_fraction=0.05,
        )

        # Warm sanity check (not part of timing).
        _ = ricci_flow_with_surgery(weights, kappa, cfg)

        total_samples = measure(lambda: ricci_flow_with_surgery(weights, kappa, cfg))
        flow_samples = measure(lambda: discrete_ricci_flow_step(weights, kappa, cfg))
        surgery_samples = measure(lambda: apply_neckpinch_surgery(weights, kappa, cfg))

        # Fraction of edges touched by surgery across SURGERY_TRACE_STEPS.
        surgery_fraction_vs_time: list[float] = []
        active_initial = max(_count_active_edges(weights), 1)
        running_w = weights
        for _ in range(SURGERY_TRACE_STEPS):
            step = ricci_flow_with_surgery(running_w, kappa, cfg)
            surgery_fraction_vs_time.append(float(step.surgery_event_count) / float(active_initial))
            running_w = step.weights_after

        total_summary = summarize(total_samples)
        flow_summary = summarize(flow_samples)
        surgery_summary = summarize(surgery_samples)

        return BenchOutcome(
            config=config,
            samples_ns=tuple(total_samples),
            summary=total_summary,
            extras={
                "flow_only_summary": dict(flow_summary),
                "surgery_only_summary": dict(surgery_summary),
                "surgery_fraction_vs_time": surgery_fraction_vs_time,
                "active_edges_initial": active_initial,
                "surgery_share_of_step_median": (
                    surgery_summary["median_ns"] / total_summary["median_ns"]
                    if total_summary["median_ns"] > 0.0
                    else 0.0
                ),
            },
        )

    return safe_run(f"ricci_flow[N={n},p={p}]", config, body)


def run_bench() -> dict[str, object]:
    """Run the full ``(N, p)`` sweep and return a JSON-friendly payload."""
    started = time.perf_counter_ns()
    outcomes: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []

    for n in CONFIG_SIZES:
        for p in CONFIG_PROBS:
            res = _run_one(n, p)
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
        "name": "bench_ricci_flow",
        "module": "core.kuramoto.ricci_flow",
        "function": "ricci_flow_with_surgery",
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
            f"N={cfg['N']:>5} p={cfg['p']:.2f}  "
            f"total_med={summ['median_ms']:8.3f} ms  p99={summ['p99_ms']:8.3f} ms  "
            f"flow_med={extras['flow_only_summary']['median_ms']:7.3f} ms  "
            f"surgery_med={extras['surgery_only_summary']['median_ms']:7.3f} ms  "
            f"active_edges={extras['active_edges_initial']}"
        )
    for fail in failures:
        summary_lines.append(
            f"FAIL {fail['config']}: {fail['error_type']}: {fail['error_message']}"
        )
    print("\n".join(summary_lines))


if __name__ == "__main__":  # pragma: no cover - CLI entry point.
    main()
