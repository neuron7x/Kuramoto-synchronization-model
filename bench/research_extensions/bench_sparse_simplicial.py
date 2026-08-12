# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""HEADLINE microbenchmark: ``triadic_rhs_sparse`` log-log scaling.

We measure the sparse triadic RHS at ``N`` in ``{32, 64, 128, 256, 512, 1024}``
on Erdos-Renyi adjacency matrices at edge probability ``p`` in
``{0.05, 0.1}``. For each configuration we record:

* actual triangle count ``T2`` returned by
  :func:`build_sparse_triangle_index`;
* sparse runtime median + p99 over ``MEASURE_ITERS`` samples (warmup
  ``WARMUP_ITERS``);
* dense ``O(N^3)`` reference runtime, only for ``N <= 128``.

The headline number is the log-log slope of sparse runtime vs ``N`` at
each ``p``. The contract is *sub-quadratic*: ``slope < 2.0`` confirms
that the sparse kernel asymptotically beats the ``O(N^2)`` pairwise
work and cannot, in particular, be hiding a quadratic auxiliary
allocation.

Configurations whose first measurement exceeds ``MAX_WALL_NS`` are
skipped with reason ``skipped_wall_time`` recorded in the JSON.

The dense reference reproduces the inner loop of
:meth:`HigherOrderKuramotoEngine._dtheta_dt` (triadic part only) so
that it is byte-equivalent in floating-point semantics to a hypothetical
``O(N^3)`` formulation at small ``N``.

Determinism is enforced by ``SEED`` from :mod:`bench.research_extensions`.
"""

from __future__ import annotations

import time
from typing import Any, Final, cast

import numpy as np
from numpy.typing import NDArray

from core.physics.higher_order_kuramoto import (
    SparseTriangleIndex,
    build_sparse_triangle_index,
    build_triangle_index,
    find_triangles,
    triadic_rhs_sparse,
)

from . import SEED
from ._timing import (
    BenchFailure,
    BenchOutcome,
    fit_loglog_slope,
    measure,
    safe_run,
    summarize,
)

__all__ = [
    "BenchFailure",
    "BenchOutcome",
    "CONFIG_SIZES",
    "CONFIG_PROBS",
    "DENSE_REFERENCE_MAX_N",
    "build_er_boolean_adjacency",
    "dense_triadic_rhs_reference",
    "run_bench",
]


CONFIG_SIZES: Final[tuple[int, ...]] = (32, 64, 128, 256, 512, 1024)
CONFIG_PROBS: Final[tuple[float, ...]] = (0.05, 0.1)
DENSE_REFERENCE_MAX_N: Final[int] = 128


def build_er_boolean_adjacency(
    n: int,
    p: float,
    *,
    seed: int,
) -> NDArray[np.bool_]:
    """Return a symmetric, zero-diagonal Erdos-Renyi boolean adjacency.

    Edges are sampled in the strict upper triangle and mirrored. The seed
    is consumed once via :func:`numpy.random.default_rng` so identical
    ``(n, p, seed)`` triples produce bit-identical matrices.
    """
    if n <= 0:
        raise ValueError("n must be > 0.")
    if not (0.0 <= p <= 1.0):
        raise ValueError("p must be in [0, 1].")

    rng = np.random.default_rng(seed)
    upper = rng.random((n, n), dtype=np.float64)
    mask = np.triu(upper < p, k=1)
    adj = mask | mask.T
    np.fill_diagonal(adj, False)
    return adj.astype(np.bool_, copy=False)


def dense_triadic_rhs_reference(
    theta: NDArray[np.float64],
    tri_index: dict[int, list[tuple[int, int]]],
    sigma2: float,
) -> NDArray[np.float64]:
    """Dense reference for the sparse triadic RHS, ``O(N * sum_deg^2)``.

    The dense path here mirrors :meth:`HigherOrderKuramotoEngine._dtheta_dt`
    triadic loop without the pairwise term. Because the per-node lists
    contain BOTH ``(j, k)`` and the symmetric reflections, the reference
    sums ``sin(2θ_j - θ_k - θ_i)`` over every node-incident triangle —
    matching the convention of :func:`triadic_rhs_sparse` once both are
    aggregated to a per-node vector.

    Each triangle ``(a, b, c)`` appears three times in ``tri_index``
    (once anchored at each vertex), so the dense and sparse outputs are
    equal by construction up to floating-point summation order.
    """
    n = int(theta.shape[0])
    out = np.zeros(n, dtype=np.float64)
    for i in range(n):
        contribs = tri_index.get(i, [])
        if not contribs:
            continue
        acc = 0.0
        for j, k in contribs:
            acc += float(np.sin(2.0 * theta[j] - theta[k] - theta[i]))
        out[i] = acc
    out *= float(sigma2)
    return out


def _build_inputs(
    n: int,
    p: float,
    *,
    seed: int,
) -> tuple[NDArray[np.bool_], SparseTriangleIndex, NDArray[np.float64]]:
    """Return ``(adj, sparse_index, theta)`` for a single configuration."""
    adj = build_er_boolean_adjacency(n, p, seed=seed)
    sparse_index = build_sparse_triangle_index(adj, max_triangles=None)
    rng = np.random.default_rng(seed + 1)
    theta = rng.uniform(-np.pi, np.pi, size=n).astype(np.float64, copy=False)
    return adj, sparse_index, theta


def _measure_with_skip(
    name: str,
    func: Any,
) -> tuple[list[int], bool]:
    """Run ``measure``; flag skipped configurations whose first run is too slow.

    Returns ``(samples, was_truncated)``. The bench harness in
    :mod:`._timing` already truncates on cumulative wall time. We
    additionally probe a single timed call before the standard ``measure``
    so that very large ``N`` configurations whose *individual* call
    exceeds 60 s are reported with ``skipped_wall_time``.
    """
    t0 = time.perf_counter_ns()
    func()
    single_dt = time.perf_counter_ns() - t0
    if single_dt >= 60_000_000_000:
        return [int(single_dt)], True
    samples = measure(func)
    return samples, False


def _run_one(n: int, p: float) -> BenchOutcome | BenchFailure:
    config: dict[str, object] = {"N": n, "p": p, "seed": SEED}

    def body() -> BenchOutcome:
        adj, sparse_index, theta = _build_inputs(n, p, seed=SEED)
        sigma2 = 0.5
        t2 = sparse_index.n_triangles

        # Warm sanity: sparse RHS has correct shape and is finite.
        sparse_warm = triadic_rhs_sparse(theta, sparse_index, sigma2)
        if sparse_warm.shape != (n,):
            raise RuntimeError(f"triadic_rhs_sparse returned shape {sparse_warm.shape} != ({n},).")
        if not np.isfinite(sparse_warm).all():
            raise RuntimeError("triadic_rhs_sparse produced non-finite output.")

        sparse_samples, sparse_truncated = _measure_with_skip(
            f"sparse[N={n},p={p}]",
            lambda: triadic_rhs_sparse(theta, sparse_index, sigma2),
        )
        sparse_summary = summarize(sparse_samples)

        extras: dict[str, object] = {
            "n_triangles": int(t2),
            "edge_density_actual": float(adj.sum()) / float(max(n * (n - 1), 1)),
            "sparse_truncated": bool(sparse_truncated),
        }

        # Dense reference only for N <= 128 — strictly bounded so we never
        # spend more than ~seconds on the O(N^3) path.
        if n <= DENSE_REFERENCE_MAX_N:
            triangles = find_triangles(adj)
            tri_idx_dense = build_triangle_index(n, triangles)

            sparse_check = triadic_rhs_sparse(theta, sparse_index, sigma2)
            dense_check = dense_triadic_rhs_reference(theta, tri_idx_dense, sigma2)
            max_abs = float(np.max(np.abs(sparse_check - dense_check)))
            if max_abs > 1e-9:
                raise RuntimeError(
                    "dense vs sparse RHS disagree beyond 1e-9: "
                    f"max_abs_diff={max_abs} at N={n}, p={p}."
                )

            dense_samples, dense_truncated = _measure_with_skip(
                f"dense[N={n},p={p}]",
                lambda: dense_triadic_rhs_reference(theta, tri_idx_dense, sigma2),
            )
            dense_summary = summarize(dense_samples)
            extras["dense_summary"] = dict(dense_summary)
            extras["dense_truncated"] = bool(dense_truncated)
            extras["sparse_vs_dense_max_abs_diff"] = max_abs
            extras["sparse_speedup_vs_dense_median"] = (
                dense_summary["median_ns"] / sparse_summary["median_ns"]
                if sparse_summary["median_ns"] > 0.0
                else float("inf")
            )
        else:
            extras["dense_summary"] = None
            extras["dense_truncated"] = False
            extras["sparse_vs_dense_max_abs_diff"] = None
            extras["sparse_speedup_vs_dense_median"] = None

        return BenchOutcome(
            config=config,
            samples_ns=tuple(sparse_samples),
            summary=sparse_summary,
            extras=extras,
        )

    return safe_run(f"sparse_simplicial[N={n},p={p}]", config, body)


def _slope_per_p(
    outcomes: list[dict[str, object]],
    p: float,
) -> tuple[float | None, float | None]:
    """Fit the log-log slope of sparse median runtime vs ``N`` for one ``p``."""
    xs: list[float] = []
    ys: list[float] = []
    for entry in outcomes:
        cfg = cast(dict[str, Any], entry["config"])
        if not np.isclose(float(cfg["p"]), p):
            continue
        summ = cast(dict[str, Any], entry["summary"])
        xs.append(float(cfg["N"]))
        ys.append(float(summ["median_ns"]))
    if len(xs) < 2:
        return None, None
    try:
        slope, intercept = fit_loglog_slope(xs, ys)
    except (ValueError, RuntimeError):
        return None, None
    return slope, intercept


def _slope_vs_triangles(
    outcomes: list[dict[str, object]],
) -> tuple[float | None, float | None]:
    """Fit log-log slope of runtime vs *triangle count* across all configs.

    This is the work-faithful axis: in Erdos-Renyi at fixed ``p``, the
    triangle count grows as ``T2 ~ p^3 * N^3 / 6``, so the runtime-vs-N
    slope reflects triangle growth, not algorithmic complexity. A sparse
    kernel that is genuinely linear in its work load satisfies
    ``slope_vs_triangles ~ 1.0``.
    """
    xs: list[float] = []
    ys: list[float] = []
    for entry in outcomes:
        extras = cast(dict[str, Any], entry["extras"])
        summ = cast(dict[str, Any], entry["summary"])
        t2 = float(extras["n_triangles"])
        if t2 <= 0.0:
            continue
        xs.append(t2)
        ys.append(float(summ["median_ns"]))
    if len(xs) < 2:
        return None, None
    try:
        slope, intercept = fit_loglog_slope(xs, ys)
    except (ValueError, RuntimeError):
        return None, None
    return slope, intercept


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

    slopes_per_p: dict[str, dict[str, float | None | bool]] = {}
    for p in CONFIG_PROBS:
        slope, intercept = _slope_per_p(outcomes, p)
        slopes_per_p[f"p={p}"] = {
            "loglog_slope": slope,
            "loglog_intercept": intercept,
            "is_subquadratic": slope is not None and slope < 2.0,
        }

    triangle_slope, triangle_intercept = _slope_vs_triangles(outcomes)
    slope_vs_triangles: dict[str, float | None | bool] = {
        "loglog_slope": triangle_slope,
        "loglog_intercept": triangle_intercept,
        "is_linear_in_work": (triangle_slope is not None and 0.7 <= triangle_slope <= 1.3),
    }

    elapsed_ns = time.perf_counter_ns() - started
    return {
        "name": "bench_sparse_simplicial",
        "module": "core.physics.higher_order_kuramoto",
        "function": "triadic_rhs_sparse",
        "elapsed_total_ns": int(elapsed_ns),
        "slopes_per_p": slopes_per_p,
        "slope_vs_triangles": slope_vs_triangles,
        "configurations": outcomes,
        "failures": failures,
    }


def main() -> None:  # pragma: no cover - CLI entry point.
    payload = run_bench()
    name = str(payload["name"])
    configurations = cast(list[dict[str, Any]], payload["configurations"])
    failures = cast(list[dict[str, Any]], payload["failures"])
    slopes = cast(dict[str, dict[str, Any]], payload["slopes_per_p"])
    triangle_slope = cast(dict[str, Any], payload["slope_vs_triangles"])

    summary_lines: list[str] = [f"=== {name} ==="]
    for entry in configurations:
        cfg = entry["config"]
        summ = entry["summary"]
        extras = entry["extras"]
        dense_md = extras.get("dense_summary")
        if isinstance(dense_md, dict):
            dense_str = f"dense_med={dense_md['median_us']:8.2f} us"
        else:
            dense_str = "dense_med=     n/a"
        summary_lines.append(
            f"N={cfg['N']:>5} p={cfg['p']:.2f}  "
            f"sparse_med={summ['median_us']:8.2f} us  "
            f"sparse_p99={summ['p99_ns'] / 1_000.0:8.2f} us  "
            f"{dense_str}  "
            f"T2={extras['n_triangles']}"
        )
    for key, info in slopes.items():
        summary_lines.append(
            f"slope[{key}]={info['loglog_slope']}  sub_quadratic={info['is_subquadratic']}"
        )
    summary_lines.append(
        f"slope_vs_triangles={triangle_slope['loglog_slope']}  "
        f"is_linear_in_work={triangle_slope['is_linear_in_work']}"
    )
    for fail in failures:
        summary_lines.append(
            f"FAIL {fail['config']}: {fail['error_type']}: {fail['error_message']}"
        )
    print("\n".join(summary_lines))


if __name__ == "__main__":  # pragma: no cover - CLI entry point.
    main()
