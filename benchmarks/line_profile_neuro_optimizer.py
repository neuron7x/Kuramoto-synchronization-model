# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Run line_profiler for hot NeuroOptimizer functions."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from benchmarks._neuro_optimizer_loader import (
    compute_stability_score,
    load_optimizer,
    load_validation,
)
from utils.seed import set_global_seed

try:
    from line_profiler import LineProfiler
except ImportError:  # pragma: no cover - optional dependency
    LineProfiler = None


def _run_steps(steps: int = 200) -> None:
    set_global_seed(11)
    rng = np.random.default_rng(11)
    NeuroOptimizer, OptimizationConfig = load_optimizer()
    validate_neuro_invariants = load_validation()
    optimizer = NeuroOptimizer(OptimizationConfig(dtype="float32"))
    params = {
        "dopamine": {"learning_rate": 0.01, "discount_gamma": 0.99},
        "serotonin": {"learning_rate": 0.01},
        "gaba": {"learning_rate": 0.01},
        "na_ach": {"learning_rate": 0.01},
    }
    state = {
        "dopamine_level": 0.55,
        "serotonin_level": 0.35,
        "gaba_inhibition": 0.45,
        "na_arousal": 1.05,
        "ach_attention": 0.75,
    }

    for _ in range(steps):
        performance = float(rng.normal(loc=0.5, scale=0.1))
        params, balance = optimizer.optimize(params, state, performance)
        stability = compute_stability_score(optimizer._performance_history)
        validate_neuro_invariants(
            dopamine_serotonin_ratio=balance.dopamine_serotonin_ratio,
            excitation_inhibition_balance=balance.gaba_excitation_balance,
            arousal_attention_coherence=balance.arousal_attention_coherence,
            stability=stability,
            da_5ht_ratio_range=optimizer.config.da_5ht_ratio_range,
            ei_balance_range=optimizer.config.ei_balance_range,
        )


def main() -> None:
    if LineProfiler is None:
        raise SystemExit("line_profiler is not installed")

    NeuroOptimizer, OptimizationConfig = load_optimizer()
    optimizer = NeuroOptimizer(OptimizationConfig(dtype="float32"))
    profiler = LineProfiler()
    profiler.add_function(optimizer._calculate_balance_metrics)
    profiler.add_function(optimizer._calculate_objective)
    profiler.add_function(optimizer._apply_updates)

    profiler.enable_by_count()
    _run_steps()
    profiler.disable_by_count()

    out_dir = Path("reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "neuro_optimizer_line_profile.txt"
    with out_path.open("w", encoding="utf-8") as handle:
        profiler.print_stats(stream=handle)

    print(f"Wrote line profile to {out_path}")


if __name__ == "__main__":
    main()
