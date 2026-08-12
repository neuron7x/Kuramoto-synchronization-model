# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Microbenchmark: ``DRFreeEnergyModel.evaluate_robust`` cost vs ambiguity dim.

The DR-FREE evaluation should be ``O(1)`` *per metric* — the box ambiguity
mapping ``m -> m * (1 + r_m)`` is a per-metric multiply followed by a single
free-energy evaluation that is itself ``O(1)`` in the metric count (the
underlying :class:`tacl.EnergyModel` has a fixed metric registry).

We confirm the ``O(1)`` behaviour empirically by sweeping the populated
ambiguity-set size from 0 to ``len(known_metrics)``: per-call cost should
stay essentially flat. The slope of a log-log fit on populated dimension
vs runtime is reported alongside the medians.
"""

from __future__ import annotations

import time
from typing import Any, Final, cast

from tacl.dr_free import AmbiguitySet, DRFreeEnergyModel
from tacl.energy_model import EnergyMetrics, EnergyModel

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
    "AMBIGUITY_DIMENSIONS",
    "build_metrics",
    "run_bench",
]


def _default_metrics_template() -> EnergyMetrics:
    """Construct a representative nominal metrics payload.

    Values are well below the production thresholds in
    :mod:`tacl.energy_model` so the nominal free energy is finite and the
    DR-FREE inflation produces a meaningful but bounded margin.
    """
    return EnergyMetrics(
        latency_p95=40.0,
        latency_p99=70.0,
        coherency_drift=0.02,
        cpu_burn=0.45,
        mem_cost=3.5,
        queue_depth=14.0,
        packet_loss=0.001,
    )


def build_metrics() -> EnergyMetrics:
    """Public helper exposing the canonical bench metrics."""
    return _default_metrics_template()


_METRIC_NAMES: Final[tuple[str, ...]] = (
    "latency_p95",
    "latency_p99",
    "coherency_drift",
    "cpu_burn",
    "mem_cost",
    "queue_depth",
    "packet_loss",
)
AMBIGUITY_DIMENSIONS: Final[tuple[int, ...]] = (0, 1, 2, 3, 4, 5, 6, 7)


def _build_ambiguity(dim: int, *, radius: float) -> AmbiguitySet:
    """Return an :class:`AmbiguitySet` populating ``dim`` of the seven metrics.

    Ordering is deterministic (the module-level ``_METRIC_NAMES`` tuple) so
    the bench is repeatable across runs with the same ``SEED``.
    """
    if dim < 0 or dim > len(_METRIC_NAMES):
        raise ValueError(f"dim must be in [0, {len(_METRIC_NAMES)}].")
    radii: dict[str, float] = {name: radius for name in _METRIC_NAMES[:dim]}
    return AmbiguitySet(radii=radii)


def _run_one(dim: int) -> BenchOutcome | BenchFailure:
    config: dict[str, object] = {"ambiguity_dim": dim, "seed": SEED}

    def body() -> BenchOutcome:
        model = DRFreeEnergyModel(EnergyModel())
        metrics = build_metrics()
        ambiguity = _build_ambiguity(dim, radius=0.10)

        # Sanity: the result must respect INV-FE-ROBUST.
        result = model.evaluate_robust(metrics, ambiguity)
        if not (result.robust_free_energy + 1e-12 >= result.nominal_free_energy):
            raise RuntimeError(
                "DR-FREE invariant INV-FE-ROBUST violated in warm sanity: "
                f"robust={result.robust_free_energy} < nominal={result.nominal_free_energy}."
            )

        samples = measure(lambda: model.evaluate_robust(metrics, ambiguity))
        summ = summarize(samples)
        return BenchOutcome(
            config=config,
            samples_ns=tuple(samples),
            summary=summ,
            extras={
                "robust_margin": float(result.robust_margin),
                "nominal_free_energy": float(result.nominal_free_energy),
                "robust_free_energy": float(result.robust_free_energy),
            },
        )

    return safe_run(f"dr_free[dim={dim}]", config, body)


def run_bench() -> dict[str, object]:
    """Run the ambiguity-dimension sweep and return a JSON-friendly payload."""
    started = time.perf_counter_ns()
    outcomes: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []

    for dim in AMBIGUITY_DIMENSIONS:
        res = _run_one(dim)
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

    # O(1) confirmation: log-log slope of dim (>=1) vs median runtime.
    slope: float | None = None
    intercept: float | None = None
    if len(outcomes) >= 2:
        xs = [
            float(cast(int, entry["config"]["ambiguity_dim"]))  # type: ignore[index]
            for entry in outcomes
            if cast(int, entry["config"]["ambiguity_dim"]) > 0  # type: ignore[index]
        ]
        ys = [
            float(cast(float, entry["summary"]["median_ns"]))  # type: ignore[index]
            for entry in outcomes
            if cast(int, entry["config"]["ambiguity_dim"]) > 0  # type: ignore[index]
        ]
        if len(xs) >= 2:
            try:
                slope, intercept = fit_loglog_slope(xs, ys)
            except (ValueError, RuntimeError):
                slope, intercept = None, None

    elapsed_ns = time.perf_counter_ns() - started
    return {
        "name": "bench_dr_free",
        "module": "tacl.dr_free",
        "function": "DRFreeEnergyModel.evaluate_robust",
        "elapsed_total_ns": int(elapsed_ns),
        "loglog_slope_vs_dim": slope,
        "loglog_intercept_vs_dim": intercept,
        "is_O1_per_metric": (slope is not None and abs(slope) < 0.5),
        "configurations": outcomes,
        "failures": failures,
    }


def main() -> None:  # pragma: no cover - CLI entry point.
    payload = run_bench()
    name = str(payload["name"])
    configurations = cast(list[dict[str, Any]], payload["configurations"])
    failures = cast(list[dict[str, Any]], payload["failures"])
    slope = payload.get("loglog_slope_vs_dim")
    is_o1 = payload.get("is_O1_per_metric")

    summary_lines: list[str] = [f"=== {name} ==="]
    for entry in configurations:
        cfg = entry["config"]
        summ = entry["summary"]
        summary_lines.append(
            f"dim={cfg['ambiguity_dim']:>2}  "
            f"median={summ['median_us']:8.2f} us  p99={summ['p99_ns'] / 1_000.0:8.2f} us"
        )
    summary_lines.append(f"loglog_slope_vs_dim={slope}  is_O1_per_metric={is_o1}")
    for fail in failures:
        summary_lines.append(
            f"FAIL {fail['config']}: {fail['error_type']}: {fail['error_message']}"
        )
    print("\n".join(summary_lines))


if __name__ == "__main__":  # pragma: no cover - CLI entry point.
    main()
