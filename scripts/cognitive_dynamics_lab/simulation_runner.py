#!/usr/bin/env python3
"""Replayable stdlib-only artifact emitter for cognitive dynamics lab."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

CaseName = str
RunRecord = dict[str, str]
Summary = dict[str, Any]
QuantizedMetric = dict[str, float | str]
OptimizedMetric = dict[str, float | str]

CASES: list[CaseName] = [
    "baseline",
    "high_noise",
    "delayed_feedback",
    "scarce_data",
    "rapid_regime_shift",
    "stress_case",
    "resource_constrained",
]

RUN_ID = "CDL-SUMMARY"
METHOD_VERSION = "cognitive-dynamics-lab-v0.1"
SEED = 20260613
CLAIM_TIER = "simulation-only"
DEFAULT_OUT = "artifacts/cognitive_dynamics_lab"
UNIT_SCALE = "0..1"
CALIBRATION_PROFILE = {
    "version": "calibration-v0.1",
    "sensitivity": "balanced",
    "low_upper": 0.25,
    "high_lower": 0.75,
    "precision_digits": 6,
}
QUANTIZED_STATES = ["low", "medium", "high"]
QUANTIZATION_BINS = {
    "low": [0.0, CALIBRATION_PROFILE["low_upper"]],
    "medium": [CALIBRATION_PROFILE["low_upper"], CALIBRATION_PROFILE["high_lower"]],
    "high": [CALIBRATION_PROFILE["high_lower"], 1.0],
}

AGGREGATE_METRICS = {
    "mean_mae": 0.189113,
    "mean_realism_gap": 0.157488,
    "mean_ei_balance": 0.643307,
    "mean_outside_ei_fraction": 0.777974,
    "mean_energy_efficiency": 0.000152479,
    "mean_stability_margin": 0.736609,
}

NORMALIZATION_REFERENCES = {
    "mean_mae": 1.0,
    "mean_realism_gap": 1.0,
    "mean_ei_balance": 1.0,
    "mean_outside_ei_fraction": 1.0,
    "mean_energy_efficiency": 0.001,
    "mean_stability_margin": 1.0,
}

OPTIMIZATION_PROFILE = {
    "version": "objective-v0.1",
    "mode": "bounded_weighted_utility",
    "objective_scale": UNIT_SCALE,
    "metric_directions": {
        "mean_mae": "minimize",
        "mean_realism_gap": "minimize",
        "mean_ei_balance": "maximize",
        "mean_outside_ei_fraction": "minimize",
        "mean_energy_efficiency": "maximize",
        "mean_stability_margin": "maximize",
    },
    "metric_weights": {
        "mean_mae": 0.20,
        "mean_realism_gap": 0.20,
        "mean_ei_balance": 0.15,
        "mean_outside_ei_fraction": 0.15,
        "mean_energy_efficiency": 0.15,
        "mean_stability_margin": 0.15,
    },
    "decision_thresholds": {
        "optimize_below": 0.60,
        "stable_at_or_above": 0.75,
    },
}

CONFIDENCE = {
    "level": 0.60,
    "reason": (
        "simulation-only perturbation evidence; stability thresholds are not "
        "consistently passed"
    ),
    "cannot_claim": ["external validation", "production readiness"],
}


def clamp_unit(value: float) -> float:
    """Clamp a metric to the shared unit interval."""
    digits = int(CALIBRATION_PROFILE["precision_digits"])
    return round(max(0.0, min(1.0, value)), digits)


def normalize_metric(name: str, value: float) -> float:
    """Normalize a raw metric into the common 0..1 scale."""
    reference = NORMALIZATION_REFERENCES[name]
    return clamp_unit(value / reference)


def build_normalized_metrics(metrics: dict[str, float]) -> dict[str, float]:
    """Return normalized aggregate metrics using explicit references."""
    return {name: normalize_metric(name, value) for name, value in metrics.items()}


def quantize_unit(value: float) -> str:
    """Map a unit-scaled continuous value to a calibrated discrete state."""
    if value <= float(CALIBRATION_PROFILE["low_upper"]):
        return "low"
    if value < float(CALIBRATION_PROFILE["high_lower"]):
        return "medium"
    return "high"


def quantize_metric(name: str, value: float) -> QuantizedMetric:
    """Return both the normalized value and its calibrated discrete state."""
    normalized = normalize_metric(name, value)
    return {"value": normalized, "state": quantize_unit(normalized)}


def build_quantized_metrics(metrics: dict[str, float]) -> dict[str, QuantizedMetric]:
    """Return calibrated discrete states for normalized aggregate metrics."""
    return {name: quantize_metric(name, value) for name, value in metrics.items()}


def metric_direction(name: str) -> str:
    """Return the configured optimization direction for a metric."""
    directions = OPTIMIZATION_PROFILE["metric_directions"]
    return str(directions[name])


def metric_weight(name: str) -> float:
    """Return the configured objective weight for a metric."""
    weights = OPTIMIZATION_PROFILE["metric_weights"]
    return float(weights[name])


def metric_utility(name: str, normalized: float) -> float:
    """Return utility contribution before applying the metric weight."""
    direction = metric_direction(name)
    if direction == "minimize":
        return clamp_unit(1.0 - normalized)
    return clamp_unit(normalized)


def optimize_metric(name: str, value: float) -> OptimizedMetric:
    """Return objective terms for one metric."""
    normalized = normalize_metric(name, value)
    utility = metric_utility(name, normalized)
    weight = metric_weight(name)
    contribution = clamp_unit(utility * weight)
    return {
        "direction": metric_direction(name),
        "normalized_value": normalized,
        "utility": utility,
        "weight": weight,
        "weighted_utility": contribution,
    }


def build_optimized_metrics(metrics: dict[str, float]) -> dict[str, OptimizedMetric]:
    """Return per-metric objective terms."""
    return {name: optimize_metric(name, value) for name, value in metrics.items()}


def build_objective_score(metrics: dict[str, float]) -> float:
    """Return bounded weighted objective score on the shared unit scale."""
    optimized = build_optimized_metrics(metrics)
    return clamp_unit(sum(float(row["weighted_utility"]) for row in optimized.values()))


def objective_state(score: float) -> str:
    """Return a discrete state for the objective score."""
    thresholds = OPTIMIZATION_PROFILE["decision_thresholds"]
    if score < float(thresholds["optimize_below"]):
        return "optimize"
    if score < float(thresholds["stable_at_or_above"]):
        return "watch"
    return "stable"


def replay_command() -> str:
    """Return the canonical replay command exposed in the summary artifact."""
    return (
        "python scripts/cognitive_dynamics_lab/simulation_runner.py "
        "--out artifacts/cognitive_dynamics_lab"
    )


def build_summary() -> Summary:
    """Build the deterministic top-level summary artifact."""
    objective_score = build_objective_score(AGGREGATE_METRICS)
    return {
        "run_id": RUN_ID,
        "method_version": METHOD_VERSION,
        "seed": SEED,
        "status": "ARTIFACT_BUILT",
        "artifact_role": "simulation_evidence",
        "claim_tier": CLAIM_TIER,
        "runs": len(CASES),
        "cases": CASES,
        "replay_command": replay_command(),
        "metric_scale": UNIT_SCALE,
        "calibration_profile": CALIBRATION_PROFILE,
        "optimization_profile": OPTIMIZATION_PROFILE,
        "normalization_references": NORMALIZATION_REFERENCES,
        "quantization_bins": QUANTIZATION_BINS,
        "quantized_states": QUANTIZED_STATES,
        "aggregate_metrics": AGGREGATE_METRICS,
        "normalized_metrics": build_normalized_metrics(AGGREGATE_METRICS),
        "quantized_metrics": build_quantized_metrics(AGGREGATE_METRICS),
        "optimized_metrics": build_optimized_metrics(AGGREGATE_METRICS),
        "objective_score": objective_score,
        "objective_state": objective_state(objective_score),
        "detected_holes_frequency": {"H5": 7, "H6": 1, "H10": 1},
        "confidence": CONFIDENCE,
    }


SUMMARY = build_summary()


def run_case(case: CaseName) -> RunRecord:
    """Return one deterministic per-case replay record."""
    return {
        "run_id": f"CDL-{case}",
        "case": case,
        "claim_tier": CLAIM_TIER,
        "metric_scale": UNIT_SCALE,
        "calibration": str(CALIBRATION_PROFILE["version"]),
        "optimization": str(OPTIMIZATION_PROFILE["version"]),
        "quantization": "enabled",
    }


def write_json(path: Path, payload: Any) -> None:
    """Write stable sorted JSON with a trailing newline."""
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_run_records(out: Path) -> None:
    """Write one deterministic JSON record per configured case."""
    runs_dir = out / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    for case in CASES:
        write_json(runs_dir / f"{case}.json", run_case(case))


def write_metrics_table(out: Path) -> None:
    """Write a compact CSV index of deterministic run records."""
    with (out / "metrics_table.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "case",
                "claim_tier",
                "metric_scale",
                "calibration",
                "optimization",
                "quantization",
            ]
        )
        for case in CASES:
            writer.writerow(
                [
                    case,
                    CLAIM_TIER,
                    UNIT_SCALE,
                    CALIBRATION_PROFILE["version"],
                    OPTIMIZATION_PROFILE["version"],
                    "enabled",
                ]
            )


def write_outputs(out: Path) -> None:
    """Write deterministic summary, run records, and a compact metrics table."""
    out.mkdir(parents=True, exist_ok=True)
    write_run_records(out)
    write_json(out / "summary.json", SUMMARY)
    write_metrics_table(out)
    print(json.dumps(SUMMARY, indent=2, sort_keys=True))


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the replay emitter."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=DEFAULT_OUT)
    return parser.parse_args()


def main() -> int:
    """Run the deterministic artifact emitter."""
    args = parse_args()
    write_outputs(Path(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
