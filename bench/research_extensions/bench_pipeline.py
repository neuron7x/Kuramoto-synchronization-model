# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Microbenchmark: end-to-end research-extension pipeline.

Pipeline (per measured iteration, with the inputs prebuilt outside the
timing window):

1. ``build_capital_weighted_adjacency`` — beta-modulated coupling.
2. ``ricci_flow_with_surgery`` — exactly one combined flow + surgery
   step on the boolean projection of the resulting coupling.
3. ``run_sparse_higher_order`` — 50 RK4 steps of the sparse triadic
   higher-order Kuramoto kernel on the post-surgery topology.

We measure the full chain at ``N`` in ``{64, 256, 1024}`` and report
both the total median wall time and the per-stage median wall time of
each component (the components are also timed independently to attribute
cost). The deterministic seed is ``20260425`` so that re-running the
suite yields bit-identical inputs.
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
from core.kuramoto.ricci_flow import (
    RicciFlowConfig,
    ricci_flow_with_surgery,
)
from core.physics.higher_order_kuramoto import (
    HigherOrderSparseConfig,
    run_sparse_higher_order,
)

from . import SEED
from ._timing import (
    BenchFailure,
    BenchOutcome,
    measure,
    safe_run,
    summarize,
)

__all__ = [
    "BenchFailure",
    "BenchOutcome",
    "CONFIG_SIZES",
    "PIPELINE_STEPS",
    "EDGE_PROBABILITY",
    "build_pipeline_inputs",
    "run_bench",
]


CONFIG_SIZES: Final[tuple[int, ...]] = (64, 256, 1024)
PIPELINE_STEPS: Final[int] = 50
EDGE_PROBABILITY: Final[float] = 0.1
EDGE_THRESHOLD: Final[float] = 1e-6


def _make_baseline(n: int, p: float, *, rng: np.random.Generator) -> NDArray[np.float64]:
    """Random symmetric baseline coupling, zero-diagonal, sparsity ``p``.

    The matrix is the elementwise product of a Bernoulli mask with a
    ``Uniform(0.1, 1.0)`` weight draw, then symmetrised.
    """
    upper_mask = np.triu(rng.random((n, n)) < p, k=1)
    upper_w = np.triu(0.1 + 0.9 * rng.random((n, n)), k=1)
    upper = (upper_mask * upper_w).astype(np.float64)
    baseline = upper + upper.T
    np.fill_diagonal(baseline, 0.0)
    return baseline


def build_pipeline_inputs(
    n: int,
    *,
    seed: int,
) -> tuple[
    NDArray[np.float64],
    L2DepthSnapshot,
    int,
    CapitalWeightedCouplingConfig,
    NDArray[np.float64],
    NDArray[np.float64],
    HigherOrderSparseConfig,
    RicciFlowConfig,
    int,
]:
    """Pre-build every input the pipeline needs.

    Returns ``(baseline, snapshot, signal_ts, beta_cfg, omega, theta0,
    sparse_cfg, ricci_cfg, n_levels)``. All matrices are symmetric and
    zero-diagonal.
    """
    if n <= 0:
        raise ValueError("n must be > 0.")

    rng = np.random.default_rng(seed)
    n_levels = 5

    baseline = _make_baseline(n, EDGE_PROBABILITY, rng=rng)

    bid_sizes = (rng.random((n, n_levels)) * 100.0).astype(np.float64)
    ask_sizes = (rng.random((n, n_levels)) * 100.0).astype(np.float64)
    mid_prices = (1.0 + rng.random(n) * 100.0).astype(np.float64)

    snapshot = L2DepthSnapshot(
        timestamp_ns=0,
        bid_sizes=bid_sizes,
        ask_sizes=ask_sizes,
        mid_prices=mid_prices,
    )
    beta_cfg = CapitalWeightedCouplingConfig()

    omega = rng.standard_normal(n).astype(np.float64)
    theta0 = rng.uniform(-np.pi, np.pi, size=n).astype(np.float64)

    sparse_cfg = HigherOrderSparseConfig(sigma1=1.0, sigma2=0.5)
    ricci_cfg = RicciFlowConfig(
        eta=0.05,
        eps_weight=1e-8,
        eps_neck=1e-3,
        preserve_total_edge_mass=True,
        preserve_connectedness=True,
        allow_disconnect=False,
        max_surgery_fraction=0.05,
    )

    return (
        baseline,
        snapshot,
        1,
        beta_cfg,
        omega,
        theta0,
        sparse_cfg,
        ricci_cfg,
        n_levels,
    )


def _curvature_from_weights(
    weights: NDArray[np.float64],
    *,
    base: float = 0.2,
) -> dict[tuple[int, int], float]:
    """Deterministic synthetic Ollivier-Ricci-like curvature dict."""
    n = int(weights.shape[0])
    out: dict[tuple[int, int], float] = {}
    iu, ju = np.triu_indices(n, k=1)
    w_vals = weights[iu, ju]
    for i, j, w in zip(iu.tolist(), ju.tolist(), w_vals.tolist(), strict=True):
        if w > 0.0:
            out[(int(i), int(j))] = base - 2.0 * float(w)
    return out


def _full_pipeline(
    *,
    baseline: NDArray[np.float64],
    snapshot: L2DepthSnapshot,
    signal_ts: int,
    beta_cfg: CapitalWeightedCouplingConfig,
    omega: NDArray[np.float64],
    theta0: NDArray[np.float64],
    sparse_cfg: HigherOrderSparseConfig,
    ricci_cfg: RicciFlowConfig,
    pipeline_steps: int,
    dt: float,
) -> None:
    """Execute the full pipeline once. The return value is discarded."""
    cw = build_capital_weighted_adjacency(baseline, snapshot, signal_ts, beta_cfg)
    coupling = cw.coupling

    curvature = _curvature_from_weights(coupling)
    flow = ricci_flow_with_surgery(coupling, curvature, ricci_cfg)

    adj_bool = flow.weights_after > EDGE_THRESHOLD
    np.fill_diagonal(adj_bool, False)

    _ = run_sparse_higher_order(
        adj_bool.astype(np.bool_, copy=False),
        omega,
        theta0,
        cfg=sparse_cfg,
        dt=dt,
        steps=pipeline_steps,
    )


def _stage_capital(
    baseline: NDArray[np.float64],
    snapshot: L2DepthSnapshot,
    signal_ts: int,
    beta_cfg: CapitalWeightedCouplingConfig,
) -> NDArray[np.float64]:
    return build_capital_weighted_adjacency(baseline, snapshot, signal_ts, beta_cfg).coupling


def _stage_ricci(
    coupling: NDArray[np.float64],
    ricci_cfg: RicciFlowConfig,
) -> NDArray[np.float64]:
    curvature = _curvature_from_weights(coupling)
    return ricci_flow_with_surgery(coupling, curvature, ricci_cfg).weights_after


def _stage_sparse(
    adj_bool: NDArray[np.bool_],
    omega: NDArray[np.float64],
    theta0: NDArray[np.float64],
    sparse_cfg: HigherOrderSparseConfig,
    pipeline_steps: int,
    dt: float,
) -> None:
    _ = run_sparse_higher_order(
        adj_bool,
        omega,
        theta0,
        cfg=sparse_cfg,
        dt=dt,
        steps=pipeline_steps,
    )


def _run_one(n: int) -> BenchOutcome | BenchFailure:
    config: dict[str, object] = {
        "N": n,
        "seed": SEED,
        "pipeline_steps": PIPELINE_STEPS,
        "edge_probability": EDGE_PROBABILITY,
    }

    def body() -> BenchOutcome:
        (
            baseline,
            snapshot,
            signal_ts,
            beta_cfg,
            omega,
            theta0,
            sparse_cfg,
            ricci_cfg,
            n_levels,
        ) = build_pipeline_inputs(n, seed=SEED)
        dt = 0.01

        # Warm-up + correctness sanity outside the timing window.
        _full_pipeline(
            baseline=baseline,
            snapshot=snapshot,
            signal_ts=signal_ts,
            beta_cfg=beta_cfg,
            omega=omega,
            theta0=theta0,
            sparse_cfg=sparse_cfg,
            ricci_cfg=ricci_cfg,
            pipeline_steps=PIPELINE_STEPS,
            dt=dt,
        )

        # Stage breakdowns reuse the same inputs so call patterns match.
        coupling = _stage_capital(baseline, snapshot, signal_ts, beta_cfg)
        flowed = _stage_ricci(coupling, ricci_cfg)
        adj_bool = flowed > EDGE_THRESHOLD
        np.fill_diagonal(adj_bool, False)
        adj_bool = adj_bool.astype(np.bool_, copy=False)

        total_samples = measure(
            lambda: _full_pipeline(
                baseline=baseline,
                snapshot=snapshot,
                signal_ts=signal_ts,
                beta_cfg=beta_cfg,
                omega=omega,
                theta0=theta0,
                sparse_cfg=sparse_cfg,
                ricci_cfg=ricci_cfg,
                pipeline_steps=PIPELINE_STEPS,
                dt=dt,
            )
        )
        capital_samples = measure(lambda: _stage_capital(baseline, snapshot, signal_ts, beta_cfg))
        ricci_samples = measure(lambda: _stage_ricci(coupling, ricci_cfg))
        sparse_samples = measure(
            lambda: _stage_sparse(adj_bool, omega, theta0, sparse_cfg, PIPELINE_STEPS, dt)
        )

        total_summary = summarize(total_samples)
        capital_summary = summarize(capital_samples)
        ricci_summary = summarize(ricci_samples)
        sparse_summary = summarize(sparse_samples)

        sum_components_ns = (
            capital_summary["median_ns"] + ricci_summary["median_ns"] + sparse_summary["median_ns"]
        )

        return BenchOutcome(
            config=config,
            samples_ns=tuple(total_samples),
            summary=total_summary,
            extras={
                "capital_summary": dict(capital_summary),
                "ricci_summary": dict(ricci_summary),
                "sparse_summary": dict(sparse_summary),
                "stage_sum_median_ns": float(sum_components_ns),
                "n_active_edges_post_surgery": int(np.count_nonzero(adj_bool)) // 2,
                "n_levels": int(n_levels),
                "dt": dt,
            },
        )

    return safe_run(f"pipeline[N={n}]", config, body)


def run_bench() -> dict[str, object]:
    """Run the pipeline sweep and return a JSON-friendly payload."""
    started = time.perf_counter_ns()
    outcomes: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []

    for n in CONFIG_SIZES:
        res = _run_one(n)
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
        "name": "bench_pipeline",
        "module": "bench.research_extensions.bench_pipeline",
        "function": "_full_pipeline",
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
            f"N={cfg['N']:>5}  total_med={summ['median_ms']:9.3f} ms  "
            f"p99={summ['p99_ms']:9.3f} ms  "
            f"capital={extras['capital_summary']['median_ms']:7.3f} ms  "
            f"ricci={extras['ricci_summary']['median_ms']:7.3f} ms  "
            f"sparse={extras['sparse_summary']['median_ms']:7.3f} ms  "
            f"edges={extras['n_active_edges_post_surgery']}"
        )
    for fail in failures:
        summary_lines.append(
            f"FAIL {fail['config']}: {fail['error_type']}: {fail['error_message']}"
        )
    print("\n".join(summary_lines))


if __name__ == "__main__":  # pragma: no cover - CLI entry point.
    main()
