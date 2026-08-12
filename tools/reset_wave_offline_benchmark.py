# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Offline benchmark for reset-wave (no network required).

Reports the rate at which:
  * sync_monotonic_rate  — synchronous solver keeps potential nonincreasing,
  * async_monotonic_rate — async-resilient solver keeps potential nonincreasing,
  * async_lock_rate      — fail-closed lock fired in adversarial conditions.

Use this as a local reality anchor while offline. Acceptance gate is
declarative: change the model only if these rates do not regress.

Usage:
    python tools/reset_wave_offline_benchmark.py
    -> reports/reset_wave_offline_benchmark_summary.json
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from geosync.neuroeconomics.reset_wave_engine import (
    AsyncResilienceConfig,
    ResetWaveConfig,
    run_reset_wave,
    run_reset_wave_async_resilient,
)


def run(n: int = 2000, seed: int = 2026) -> dict[str, float]:
    """Run ``n`` Monte-Carlo scenarios and aggregate rates."""
    rng = random.Random(seed)
    mono_sync = 0
    mono_async = 0
    lock_async = 0
    for _ in range(n):
        cfg = ResetWaveConfig(
            coupling_gain=rng.choice([0.2, 0.5, 1.0, 1.5]),
            dt=rng.choice([0.02, 0.05, 0.1]),
            steps=64,
            convergence_tol=0.03,
            max_phase_error=rng.choice([0.6, 1.0, 3.14]),
        )
        base = [rng.uniform(-0.5, 0.5) for _ in range(6)]
        node = [b + rng.uniform(-1.0, 1.0) for b in base]

        sync = run_reset_wave(node, base, cfg)
        mono_sync += int(sync.final_potential <= sync.initial_potential)

        async_out = run_reset_wave_async_resilient(
            node,
            base,
            cfg,
            AsyncResilienceConfig(
                message_jitter=rng.choice([0.0, 0.01, 0.03]),
                dropout_rate=rng.choice([0.0, 0.1, 0.2]),
                reentry_gain=0.4,
                seed=rng.randint(0, 10_000_000),
            ),
        )
        mono_async += int(async_out.final_potential <= async_out.initial_potential)
        lock_async += int(async_out.locked)

    return {
        "n": float(n),
        "sync_monotonic_rate": mono_sync / n,
        "async_monotonic_rate": mono_async / n,
        "async_lock_rate": lock_async / n,
        "seed": float(seed),
    }


if __name__ == "__main__":
    summary = run()
    out = Path("reports/reset_wave_offline_benchmark_summary.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
