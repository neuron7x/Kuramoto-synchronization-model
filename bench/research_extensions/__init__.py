# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Microbenchmark suite for the four GeoSync research extensions.

Modules
-------
* :mod:`bench.research_extensions.bench_capital_weighted` —
  ``build_capital_weighted_adjacency`` over ``(N, L)`` sweeps.
* :mod:`bench.research_extensions.bench_ricci_flow` —
  ``ricci_flow_with_surgery`` per-step cost on Erdos-Renyi graphs.
* :mod:`bench.research_extensions.bench_dr_free` —
  ``DRFreeEnergyModel.evaluate_robust`` per-call cost vs ambiguity dim.
* :mod:`bench.research_extensions.bench_sparse_simplicial` —
  ``triadic_rhs_sparse`` log-log scaling vs dense reference.
* :mod:`bench.research_extensions.bench_pipeline` —
  end-to-end build-coupling -> Ricci flow -> sparse triadic simulation.
* :mod:`bench.research_extensions.run_all` —
  driver that runs all five and emits ``BENCHMARK_REPORT.{json,md}``.

Implementation contract
-----------------------
* All measurements use :func:`time.perf_counter_ns`.
* Each configuration runs 2 warm-up iterations before measurement.
* Configurations whose first measured run exceeds ``MAX_WALL_NS`` (60 s) are
  skipped and recorded as ``"skipped_wall_time"``.
* Failures are captured (with traceback) inside the JSON payload — never
  silently dropped.
* Determinism: all random draws derive from ``SEED = 20260425``.
"""

from __future__ import annotations

from typing import Final

SEED: Final[int] = 20260425
WARMUP_ITERS: Final[int] = 2
MEASURE_ITERS: Final[int] = 30
MAX_WALL_NS: Final[int] = 60 * 1_000_000_000  # 60 seconds per configuration

__all__ = ["SEED", "WARMUP_ITERS", "MEASURE_ITERS", "MAX_WALL_NS"]
