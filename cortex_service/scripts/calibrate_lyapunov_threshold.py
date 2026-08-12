# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Deterministic Lyapunov threshold calibration with holdout metadata."""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(slots=True)
class Point:
    step: int
    lyapunov: float
    label: str


@dataclass(frozen=True, slots=True)
class ThresholdMetrics:
    mean_lead: float
    coverage: int
    score: float


@dataclass(frozen=True, slots=True)
class SensitivityRow:
    candidate: float
    calibration_metric: float
    validation_metric: float
    passes: bool
    failure_reason: str


@dataclass(frozen=True, slots=True)
class CalibrationResult:
    method: str
    parameter_name: str
    candidate_values: tuple[float, ...]
    selected_value: float
    metric_name: str
    metric_values: dict[str, float]
    calibration_count: int
    validation_count: int
    invalid_count: int
    seed: int
    tie_policy: str
    sensitivity_band: tuple[float, float]
    failure_policy: str
    not_financial_advice: bool
    not_predictive_claim: bool
    calibration_dataset: str
    validation_dataset: str
    objective: str
    allowed_range: tuple[float, float]
    selection_rule: str
    sensitivity_sweep: tuple[SensitivityRow, ...]


def load_points(path: Path) -> list[Point]:
    with path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = {"step", "lyapunov", "regime_label"} - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing columns: {sorted(missing)}")
        points: list[Point] = []
        for row in reader:
            lyapunov = float(row["lyapunov"])
            if not math.isfinite(lyapunov):
                raise ValueError("lyapunov must be finite")
            points.append(
                Point(
                    step=int(row["step"]),
                    lyapunov=lyapunov,
                    label=str(row["regime_label"]),
                )
            )
        return points


def transition_steps(points: list[Point]) -> list[int]:
    return [cur.step for prev, cur in zip(points, points[1:]) if prev.label != cur.label]


def threshold_metrics(points: list[Point], threshold: float) -> ThresholdMetrics:
    if not math.isfinite(threshold):
        raise ValueError("threshold must be finite")
    lead_times: list[int] = []
    for transition in transition_steps(points):
        candidates = [
            point.step
            for point in points
            if point.step < transition and point.lyapunov >= threshold
        ]
        if candidates:
            lead_times.append(transition - max(candidates))
    if not lead_times:
        return ThresholdMetrics(mean_lead=0.0, coverage=0, score=0.0)
    mean_lead = sum(lead_times) / len(lead_times)
    return ThresholdMetrics(
        mean_lead=mean_lead,
        coverage=len(lead_times),
        score=mean_lead * len(lead_times),
    )


def evaluate_threshold(points: list[Point], threshold: float) -> tuple[float, int]:
    metrics = threshold_metrics(points, threshold)
    return metrics.mean_lead, metrics.coverage


def build_candidate_grid(
    min_threshold: float,
    max_threshold: float,
    step_size: float,
) -> tuple[float, ...]:
    values = (min_threshold, max_threshold, step_size)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("candidate range values must be finite")
    if step_size <= 0:
        raise ValueError("step_size must be positive")
    if min_threshold > max_threshold:
        raise ValueError("min_threshold must be <= max_threshold")
    out: list[float] = []
    current = min_threshold
    while current <= max_threshold + 1e-12:
        out.append(round(current, 12))
        current += step_size
    if not out:
        raise ValueError("candidate grid must not be empty")
    return tuple(out)


def validate_candidates(
    candidates: Iterable[float],
    allowed_range: tuple[float, float],
) -> tuple[float, ...]:
    lower, upper = allowed_range
    if not math.isfinite(lower) or not math.isfinite(upper) or lower > upper:
        raise ValueError("allowed_range must be finite and ordered")
    seen: set[float] = set()
    out: list[float] = []
    for candidate in candidates:
        if not math.isfinite(candidate):
            raise ValueError("candidate threshold must be finite")
        rounded = round(float(candidate), 12)
        if rounded < lower or rounded > upper:
            raise ValueError("candidate threshold outside allowed range")
        if rounded not in seen:
            seen.add(rounded)
            out.append(rounded)
    if not out:
        raise ValueError("candidate grid must not be empty")
    return tuple(sorted(out))


def split_points(
    points: list[Point],
    *,
    calibration_fraction: float,
) -> tuple[list[Point], list[Point], str, str]:
    if not 0.0 < calibration_fraction < 1.0:
        raise ValueError("calibration_fraction must be between 0 and 1")
    if len(points) < 4:
        raise ValueError("at least four points are required for split calibration")
    ordered = sorted(points, key=lambda point: point.step)
    split_at = max(1, min(int(len(ordered) * calibration_fraction), len(ordered) - 1))
    calibration = ordered[:split_at]
    validation = ordered[split_at:]
    if calibration[-1].step >= validation[0].step:
        raise ValueError("calibration split must precede validation split")
    calibration_id = f"steps:{calibration[0].step}-{calibration[-1].step}"
    validation_id = f"steps:{validation[0].step}-{validation[-1].step}"
    return calibration, validation, calibration_id, validation_id


def calibrate_threshold(
    points: list[Point],
    *,
    candidates: Iterable[float],
    allowed_range: tuple[float, float] = (0.0, 1.0),
    calibration_fraction: float = 0.6,
    seed: int = 0,
) -> CalibrationResult:
    """Select a descriptor threshold using calibration split metrics only."""
    if not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    candidate_values = validate_candidates(candidates, allowed_range)
    calibration, validation, calibration_id, validation_id = split_points(
        points,
        calibration_fraction=calibration_fraction,
    )
    scores = {
        candidate: threshold_metrics(calibration, candidate) for candidate in candidate_values
    }
    if all(metric.coverage == 0 for metric in scores.values()):
        raise ValueError("calibration split has no threshold coverage")
    selected_value = min(
        candidate_values,
        key=lambda candidate: (-scores[candidate].score, candidate),
    )
    selected_validation = threshold_metrics(validation, selected_value)
    sweep = tuple(
        SensitivityRow(
            candidate=candidate,
            calibration_metric=scores[candidate].score,
            validation_metric=threshold_metrics(validation, candidate).score,
            passes=scores[candidate].coverage > 0,
            failure_reason="" if scores[candidate].coverage > 0 else "no_calibration_coverage",
        )
        for candidate in candidate_values
    )
    return CalibrationResult(
        method="fixed_grid_holdout_sensitivity",
        parameter_name="lyapunov_prefetch_threshold",
        candidate_values=candidate_values,
        selected_value=selected_value,
        metric_name="mean_lead_times_coverage",
        metric_values={
            "selected_calibration_metric": scores[selected_value].score,
            "selected_validation_metric": selected_validation.score,
        },
        calibration_count=len(calibration),
        validation_count=len(validation),
        invalid_count=0,
        seed=seed,
        tie_policy="lowest_threshold_on_equal_calibration_score",
        sensitivity_band=(candidate_values[0], candidate_values[-1]),
        failure_policy="raise_value_error_fail_closed",
        not_financial_advice=True,
        not_predictive_claim=True,
        calibration_dataset=calibration_id,
        validation_dataset=validation_id,
        objective="maximize calibration split mean lead times covered transitions",
        allowed_range=allowed_range,
        selection_rule="select highest calibration metric; validation is reported only",
        sensitivity_sweep=sweep,
    )


def result_to_dict(result: CalibrationResult) -> dict[str, object]:
    return {
        "method": result.method,
        "parameter_name": result.parameter_name,
        "candidate_values": result.candidate_values,
        "selected_value": result.selected_value,
        "metric_name": result.metric_name,
        "metric_values": result.metric_values,
        "calibration_count": result.calibration_count,
        "validation_count": result.validation_count,
        "invalid_count": result.invalid_count,
        "seed": result.seed,
        "tie_policy": result.tie_policy,
        "sensitivity_band": result.sensitivity_band,
        "failure_policy": result.failure_policy,
        "not_financial_advice": result.not_financial_advice,
        "not_predictive_claim": result.not_predictive_claim,
        "calibration_dataset": result.calibration_dataset,
        "validation_dataset": result.validation_dataset,
        "objective": result.objective,
        "allowed_range": result.allowed_range,
        "selection_rule": result.selection_rule,
        "sensitivity_sweep": [
            {
                "candidate": row.candidate,
                "calibration_metric": row.calibration_metric,
                "validation_metric": row.validation_metric,
                "passes": row.passes,
                "failure_reason": row.failure_reason,
            }
            for row in result.sensitivity_sweep
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--min", dest="min_threshold", type=float, default=0.4)
    parser.add_argument("--max", dest="max_threshold", type=float, default=0.9)
    parser.add_argument("--step", dest="step_size", type=float, default=0.01)
    parser.add_argument("--calibration-fraction", type=float, default=0.6)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    points = load_points(args.csv)
    candidates = build_candidate_grid(args.min_threshold, args.max_threshold, args.step_size)
    result = calibrate_threshold(
        points,
        candidates=candidates,
        allowed_range=(args.min_threshold, args.max_threshold),
        calibration_fraction=args.calibration_fraction,
        seed=args.seed,
    )
    if args.json:
        print(json.dumps(result_to_dict(result), sort_keys=True))
        return
    metric = result.metric_values["selected_calibration_metric"]
    print(
        f"best_threshold={result.selected_value:.3f} "
        f"coverage={result.metric_values['selected_validation_metric']:.3f} "
        f"score={metric:.3f}"
    )


if __name__ == "__main__":
    main()
