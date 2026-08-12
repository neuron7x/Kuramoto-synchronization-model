# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Benchmark NeuroOptimizer step time and memory."""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from benchmarks._neuro_optimizer_loader import (
    compute_stability_score,
    load_optimizer,
    load_validation,
)
from core.utils.determinism import DEFAULT_SEED
from utils.seed import set_global_seed

try:
    from memory_profiler import memory_usage
except ImportError:  # pragma: no cover - optional dependency
    memory_usage = None


def _build_fixture(seed: int = DEFAULT_SEED) -> tuple[object, dict, dict]:
    rng = np.random.default_rng(seed)
    NeuroOptimizer, OptimizationConfig = load_optimizer()
    config = OptimizationConfig(dtype="float32", use_gpu=False)
    optimizer = NeuroOptimizer(config)
    params = {
        "dopamine": {"learning_rate": 0.01, "discount_gamma": 0.99},
        "serotonin": {"learning_rate": 0.01},
        "gaba": {"learning_rate": 0.01},
        "na_ach": {"learning_rate": 0.01},
    }
    state = {
        "dopamine_level": float(rng.uniform(0.3, 0.7)),
        "serotonin_level": float(rng.uniform(0.2, 0.5)),
        "gaba_inhibition": float(rng.uniform(0.3, 0.6)),
        "na_arousal": float(rng.uniform(0.8, 1.2)),
        "ach_attention": float(rng.uniform(0.6, 0.9)),
    }
    return optimizer, params, state


def _run_steps(steps: int = 200) -> dict:
    optimizer, params, state = _build_fixture()
    rng = np.random.default_rng(DEFAULT_SEED)
    validate_neuro_invariants = load_validation()

    start = time.perf_counter()
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
    elapsed = time.perf_counter() - start

    return {
        "steps": steps,
        "elapsed_s": elapsed,
        "ms_per_step": (elapsed / steps) * 1000.0,
    }


def _measure_peak_memory(steps: int = 200) -> float | None:
    if memory_usage is None:
        return None

    def _runner() -> None:
        _run_steps(steps)

    samples = memory_usage((_runner,))
    return float(max(samples)) if samples else None


def main() -> None:
    set_global_seed(DEFAULT_SEED)
    results = _run_steps()
    peak_mem = _measure_peak_memory()
    if peak_mem is not None:
        results["peak_mem_mb"] = peak_mem

    out_dir = Path("benchmarks/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "neuro_optimizer_benchmark.json"
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

    print(f"Saved results to {out_path}")


if __name__ == "__main__":
    main()
