# SPDX-License-Identifier: MIT
from __future__ import annotations

import math

METRIC_NAMES = (
    "dopamine.rpe_finite_rate",
    "dopamine.output_finite_rate",
    "dopamine.output_bound_violation_count",
    "dopamine.config_validation_pass_rate",
    "dopamine.schema_runtime_parity_failures",
    "dopamine.contract_violation_count",
    "dopamine.null_survival_rate",
    "dopamine.artifact_completeness_rate",
    "dopamine.claim_promotion_block_count",
    "dopamine.backtest_parity_error_rate",
    "dopamine.p95_step_latency_ms",
    "dopamine.p99_step_latency_ms",
    "dopamine.max_memory_mb",
    "dopamine.cognitive_value_score",
    "dopamine.cognitive_value_delta",
    "dopamine.cognitive_value_priority",
)


def metric_catalog() -> dict[str, dict[str, str]]:
    return {
        name: {"owner": "geosync.dopamine", "unit": "ratio|count|ms|MiB"} for name in METRIC_NAMES
    }


def _unit(value: float) -> float:
    if not math.isfinite(value):
        return 0.0
    return min(1.0, max(0.0, value))  # bounds: normalised telemetry value ∈ [0, 1]


def bounded_value(
    human: float,
    system: float,
    repository: float,
    research: float,
) -> float:
    return (
        0.35 * _unit(human)
        + 0.30 * _unit(system)
        + 0.20 * _unit(repository)
        + 0.15 * _unit(research)
    )


def bounded_value_delta(
    previous_score: float,
    current_score: float,
) -> dict[str, float]:
    previous = _unit(previous_score)
    current = _unit(current_score)
    delta = current - previous
    rpe = math.tanh(3.0 * delta)
    priority = min(1.0, max(0.0, 0.5 + 0.5 * rpe))  # bounds: priority ∈ [0, 1]
    return {"bounded_rpe": rpe, "delta": delta, "priority": priority}
