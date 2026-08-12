# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Baseline loading utilities for nightly regression runs."""

from __future__ import annotations

# SPDX-License-Identifier: MIT
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

__all__ = [
    "BaselineEntry",
    "BaselineStore",
    "MetricEvaluation",
    "MetricThreshold",
]


@dataclass(slots=True, frozen=True)
class MetricEvaluation:
    """Outcome of comparing an observed metric against its baseline."""

    passed: bool
    absolute_degradation: float
    relative_degradation: float | None
    message: str | None


@dataclass(slots=True, frozen=True)
class MetricThreshold:
    """Acceptance criteria for a metric when compared to its baseline."""

    higher_is_better: bool = True
    max_relative_change: float | None = None
    max_absolute_change: float | None = None
    min_value: float | None = None
    max_value: float | None = None

    def evaluate(self, baseline: float, actual: float) -> MetricEvaluation:
        """Return an evaluation describing whether ``actual`` passes the threshold."""

        if not math.isfinite(actual):
            return MetricEvaluation(
                passed=False,
                absolute_degradation=math.inf,
                relative_degradation=None,
                message="observed metric is not finite",
            )
        if not math.isfinite(baseline):
            return MetricEvaluation(
                passed=False,
                absolute_degradation=math.inf,
                relative_degradation=None,
                message="baseline metric is not finite",
            )

        violations: list[str] = []
        if self.min_value is not None and actual < self.min_value:
            violations.append(f"value {actual:.6g} below minimum {self.min_value:.6g}")
        if self.max_value is not None and actual > self.max_value:
            violations.append(f"value {actual:.6g} above maximum {self.max_value:.6g}")

        if self.higher_is_better:
            absolute_degradation = max(0.0, baseline - actual)
            if abs(baseline) > 1e-12:
                relative_degradation = absolute_degradation / abs(baseline)
            elif absolute_degradation > 0.0:
                relative_degradation = math.inf
            else:
                relative_degradation = None
        else:
            baseline_magnitude = abs(baseline)
            actual_magnitude = abs(actual)
            absolute_degradation = max(0.0, actual_magnitude - baseline_magnitude)
            if baseline_magnitude > 1e-12:
                relative_degradation = absolute_degradation / baseline_magnitude
            elif absolute_degradation > 0.0:
                relative_degradation = math.inf
            else:
                relative_degradation = None

        if (
            self.max_relative_change is not None
            and relative_degradation is not None
            and relative_degradation > self.max_relative_change + 1e-12
        ):
            violations.append(
                "relative degradation "
                f"{relative_degradation:.3f} exceeds limit "
                f"{self.max_relative_change:.3f}"
            )

        if (
            self.max_absolute_change is not None
            and absolute_degradation > self.max_absolute_change + 1e-12
        ):
            violations.append(
                f"absolute degradation {absolute_degradation:.6g} exceeds limit "
                f"{self.max_absolute_change:.6g}"
            )

        return MetricEvaluation(
            passed=not violations,
            absolute_degradation=absolute_degradation,
            relative_degradation=relative_degradation,
            message="; ".join(violations) if violations else None,
        )


@dataclass(slots=True, frozen=True)
class BaselineEntry:
    """Baseline metrics and thresholds for a specific scenario."""

    metrics: Mapping[str, float]
    thresholds: Mapping[str, MetricThreshold]


class BaselineStore:
    """Load and expose nightly regression baselines from JSON."""

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        if not self._path.exists():
            raise FileNotFoundError(f"Baseline file not found: {self._path}")
        data = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(data, Mapping):
            raise ValueError("Baseline configuration must be a mapping")

        self._entries: dict[str, dict[str, BaselineEntry]] = {}
        for stage, stage_value in data.items():
            if not isinstance(stage_value, Mapping):
                continue
            parsed_stage: dict[str, BaselineEntry] = {}
            for scenario, scenario_value in stage_value.items():
                if not isinstance(scenario_value, Mapping):
                    continue
                baseline = self._coerce_metrics(scenario_value.get("baseline", {}))
                thresholds = self._coerce_thresholds(scenario_value.get("thresholds", {}))
                parsed_stage[str(scenario)] = BaselineEntry(metrics=baseline, thresholds=thresholds)
            self._entries[str(stage)] = parsed_stage

    @staticmethod
    def _coerce_metrics(raw: Any) -> dict[str, float]:
        metrics: dict[str, float] = {}
        if isinstance(raw, Mapping):
            for key, value in raw.items():
                if isinstance(value, (int, float)) and math.isfinite(value):
                    metrics[str(key)] = float(value)
        return metrics

    @staticmethod
    def _coerce_thresholds(raw: Any) -> dict[str, MetricThreshold]:
        thresholds: dict[str, MetricThreshold] = {}
        if isinstance(raw, Mapping):
            for key, value in raw.items():
                if not isinstance(value, Mapping):
                    continue
                thresholds[str(key)] = MetricThreshold(
                    higher_is_better=bool(value.get("higher_is_better", True)),
                    max_relative_change=BaselineStore._optional_float(
                        value.get("max_relative_change")
                    ),
                    max_absolute_change=BaselineStore._optional_float(
                        value.get("max_absolute_change")
                    ),
                    min_value=BaselineStore._optional_float(value.get("min_value")),
                    max_value=BaselineStore._optional_float(value.get("max_value")),
                )
        return thresholds

    @staticmethod
    def _optional_float(value: Any) -> float | None:
        if isinstance(value, (int, float)) and math.isfinite(value):
            return float(value)
        return None

    def get_entry(self, stage: str, scenario: str) -> BaselineEntry | None:
        """Return the baseline entry for ``stage``/``scenario`` when available."""

        return self._entries.get(stage, {}).get(scenario)

    def stages(self) -> Mapping[str, Mapping[str, BaselineEntry]]:
        """Expose all stages and scenarios for introspection/testing."""

        return self._entries
