# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Run cProfile on a minimal NeuroOptimizer loop."""

from __future__ import annotations

import cProfile
import pstats
from pathlib import Path

import numpy as np

from benchmarks._neuro_optimizer_loader import (
    compute_stability_score,
    load_optimizer,
    load_validation,
)
from utils.seed import set_global_seed


def _run_profile(steps: int = 200) -> None:
    set_global_seed(7)
    rng = np.random.default_rng(7)
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
    out_dir = Path("reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    profile_path = out_dir / "neuro_optimizer_cprofile.prof"
    stats_path = out_dir / "neuro_optimizer_cprofile.txt"

    profiler = cProfile.Profile()
    profiler.enable()
    _run_profile()
    profiler.disable()
    profiler.dump_stats(profile_path)

    stats = pstats.Stats(profiler).sort_stats("cumtime")
    with stats_path.open("w", encoding="utf-8") as handle:
        stats.stream = handle
        stats.print_stats(30)

    print(f"Wrote cProfile stats to {stats_path}")


if __name__ == "__main__":
    main()
