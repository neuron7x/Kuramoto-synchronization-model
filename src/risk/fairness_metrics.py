# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fairness metrics used for compliance reporting and guardrail enforcement."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

import numpy as np

__all__ = [
    "FairnessEvaluation",
    "FairnessMetricError",
    "demographic_parity_difference",
    "equal_opportunity_difference",
    "evaluate_fairness",
    "write_fairness_report",
]

DEFAULT_THRESHOLDS: Mapping[str, float] = {
    "demographic_parity": 0.1,
    "equal_opportunity": 0.1,
}


class FairnessMetricError(ValueError):
    """Raised when fairness metrics cannot be computed because of bad input."""


def _to_numpy(array_like: Iterable[float]) -> np.ndarray:
    array = np.asarray(list(array_like))
    if array.ndim != 1:
        raise FairnessMetricError("Input arrays must be one-dimensional")
    return array


def _validate_lengths(*arrays: np.ndarray) -> None:
    lengths = {arr.size for arr in arrays}
    if len(lengths) != 1:
        raise FairnessMetricError("All inputs must contain the same number of elements")


def _group_indices(
    groups: Iterable[str | int],
    expected_length: int | None = None,
) -> dict[str, np.ndarray]:
    labels = np.asarray(list(groups))
    if labels.ndim != 1:
        raise FairnessMetricError("Group labels must be one-dimensional")
    if expected_length is not None and labels.size != expected_length:
        raise FairnessMetricError("Group labels must be the same length as predictions/targets")
    unique_labels = np.unique(labels)
    group_indices: dict[str, np.ndarray] = {}
    for label in unique_labels:
        mask = labels == label
        group_indices[str(label)] = np.where(mask)[0]
    return group_indices


def demographic_parity_difference(
    y_pred: Iterable[int | float],
    group: Iterable[str | int],
    *,
    positive_label: int | float = 1,
) -> float:
    """Return the maximum absolute difference in positive rates between groups."""

    predictions = _to_numpy(y_pred)
    groups = _group_indices(group, expected_length=predictions.size)

    if not groups:
        return 0.0

    positive_rates = []
    for indices in groups.values():
        if indices.size == 0:
            positive_rates.append(0.0)
            continue
        positives = np.count_nonzero(predictions[indices] == positive_label)
        positive_rates.append(positives / indices.size)

    return float(np.max(positive_rates) - np.min(positive_rates))


def equal_opportunity_difference(
    y_true: Iterable[int | float],
    y_pred: Iterable[int | float],
    group: Iterable[str | int],
    *,
    positive_label: int | float = 1,
) -> float:
    """Return the absolute difference between the best and worst TPR across groups."""

    truths = _to_numpy(y_true)
    predictions = _to_numpy(y_pred)
    _validate_lengths(truths, predictions)
    groups = _group_indices(group, expected_length=truths.size)

    if not groups:
        return 0.0

    tprs = []
    for indices in groups.values():
        positive_truth = truths[indices] == positive_label
        true_positive_count = np.count_nonzero(
            positive_truth & (predictions[indices] == positive_label)
        )
        positives = np.count_nonzero(positive_truth)
        if positives == 0:
            tprs.append(0.0)
            continue
        tprs.append(true_positive_count / positives)

    return float(np.max(tprs) - np.min(tprs))


@dataclass(slots=True)
class FairnessEvaluation:
    """Container for fairness metrics and the thresholds they must satisfy."""

    demographic_parity: float
    equal_opportunity: float
    thresholds: Mapping[str, float]

    def to_dict(self) -> dict[str, float | Mapping[str, float]]:
        return {
            "demographic_parity": self.demographic_parity,
            "equal_opportunity": self.equal_opportunity,
            "thresholds": dict(self.thresholds),
        }

    def assert_within_thresholds(self) -> None:
        if self.demographic_parity > self.thresholds["demographic_parity"]:
            raise AssertionError(
                "Demographic parity difference exceeds threshold: "
                f"{self.demographic_parity:.4f} > {self.thresholds['demographic_parity']:.4f}"
            )
        if self.equal_opportunity > self.thresholds["equal_opportunity"]:
            raise AssertionError(
                "Equal opportunity difference exceeds threshold: "
                f"{self.equal_opportunity:.4f} > {self.thresholds['equal_opportunity']:.4f}"
            )


def _normalise_thresholds(
    thresholds: Mapping[str, float] | None,
) -> dict[str, float]:
    base = dict(DEFAULT_THRESHOLDS)
    if thresholds is None:
        return base
    for key, value in thresholds.items():
        if key not in base:
            raise FairnessMetricError(f"Unknown fairness threshold: {key}")
        base[key] = float(value)
    return base


def evaluate_fairness(
    y_true: Iterable[int | float],
    y_pred: Iterable[int | float],
    group: Iterable[str | int],
    *,
    thresholds: Mapping[str, float] | None = None,
    positive_label: int | float = 1,
) -> FairnessEvaluation:
    """Calculate fairness metrics and optionally enforce provided thresholds."""

    normalised_thresholds = _normalise_thresholds(thresholds)
    demographic = demographic_parity_difference(y_pred, group, positive_label=positive_label)
    opportunity = equal_opportunity_difference(y_true, y_pred, group, positive_label=positive_label)
    return FairnessEvaluation(demographic, opportunity, normalised_thresholds)


def write_fairness_report(
    evaluation: FairnessEvaluation,
    *,
    output_path: Path,
) -> None:
    """Persist fairness metrics as a JSON document and compressed arrays."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    content = evaluation.to_dict()
    np.savez_compressed(
        output_path.with_suffix(".npz"),
        **{k: np.asarray(v) for k, v in content.items() if k != "thresholds"},
    )
    # JSON representation keeps compatibility with dashboards and analytics tooling
    output_path.write_text(
        _to_json_string(content),
        encoding="utf-8",
    )


def _to_json_string(content: Mapping[str, float | Mapping[str, float]]) -> str:
    import json

    class NpEncoder(json.JSONEncoder):
        def default(self, obj):  # type: ignore[override]
            if isinstance(obj, np.floating):
                return float(obj)
            if isinstance(obj, np.integer):
                return int(obj)
            return super().default(obj)

    return json.dumps(content, indent=2, cls=NpEncoder)
