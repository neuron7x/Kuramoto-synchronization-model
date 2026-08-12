# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Monitoring, quality, and reporting utilities for ETL pipelines."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import mean
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd
from pandas.api.types import is_numeric_dtype
from scipy.spatial.distance import jensenshannon

from .stores import AuditEntry


@dataclass(slots=True)
class ProfileSummary:
    """Key statistics describing a dataset distribution."""

    column: str
    dtype: str
    count: int
    nulls: int
    null_ratio: float
    unique: int | None
    mean: float | None
    std: float | None
    min: float | None
    max: float | None
    median: float | None
    quantiles: dict[str, float] | None
    top_values: list[tuple[Any, int]] = field(default_factory=list)
    is_monotonic_increasing: bool | None = None
    is_monotonic_decreasing: bool | None = None


class DistributionProfiler:
    """Build descriptive statistics to understand dataset shape."""

    def __init__(
        self,
        *,
        quantiles: Sequence[float] | None = None,
        max_top_values: int = 5,
    ) -> None:
        if quantiles is None:
            quantiles = (0.05, 0.25, 0.5, 0.75, 0.95)
        cleaned_quantiles: list[float] = []
        for quantile in quantiles:
            value = float(quantile)
            if not 0.0 <= value <= 1.0:
                raise ValueError("Quantiles must be between 0 and 1 inclusive")
            cleaned_quantiles.append(value)
        # Preserve ordering but drop duplicates to avoid redundant work.
        seen: set[float] = set()
        ordered_quantiles: list[float] = []
        for quantile in cleaned_quantiles:
            if quantile not in seen:
                seen.add(quantile)
                ordered_quantiles.append(quantile)
        self._quantiles: tuple[float, ...] = tuple(ordered_quantiles)
        self._max_top_values = max(0, int(max_top_values))

    def profile(self, frame: pd.DataFrame) -> list[ProfileSummary]:
        summaries: list[ProfileSummary] = []
        for column in frame.columns:
            series = frame[column]
            dtype = str(series.dtype)
            non_null_values = series.dropna()
            numeric_values = pd.Series(dtype=float)
            if not non_null_values.empty:
                if is_numeric_dtype(series):
                    numeric_values = non_null_values.astype(float)
                else:
                    coerced_numeric = pd.to_numeric(non_null_values, errors="coerce")
                    if not coerced_numeric.isna().any():
                        numeric_values = coerced_numeric.astype(float)
            count = int(series.shape[0])
            nulls = int(series.isna().sum())
            null_ratio = float(nulls / count) if count else 0.0
            if count:
                try:
                    unique = int(series.nunique(dropna=True))
                except TypeError:
                    unique = None
            else:
                unique = None
            mean_value = (
                float(numeric_values.mean()) if not numeric_values.empty else None
            )
            std_value = (
                float(numeric_values.std()) if numeric_values.shape[0] > 1 else None
            )
            min_value = (
                float(numeric_values.min()) if not numeric_values.empty else None
            )
            max_value = (
                float(numeric_values.max()) if not numeric_values.empty else None
            )
            median_value = (
                float(numeric_values.median()) if not numeric_values.empty else None
            )

            quantiles_map: dict[str, float] | None = None
            if not numeric_values.empty and self._quantiles:
                quantiles_result = numeric_values.quantile(self._quantiles)
                if np.isscalar(quantiles_result):
                    key = f"p{int(round(self._quantiles[0] * 100)):02d}"
                    quantiles_map = {key: float(quantiles_result)}
                else:
                    quantiles_map = {
                        f"p{int(round(float(q) * 100)):02d}": float(value)
                        for q, value in quantiles_result.items()
                    }
                median_value = quantiles_map.get("p50", median_value)

            top_values: list[tuple[Any, int]] = []
            if self._max_top_values and not non_null_values.empty:
                counts = series.value_counts(dropna=True)
                sorted_counts = sorted(
                    (
                        (self._normalise_value(value), int(count))
                        for value, count in counts.items()
                    ),
                    key=lambda item: (-item[1], repr(item[0])),
                )
                top_values = sorted_counts[: self._max_top_values]

            is_monotonic_increasing: bool | None
            is_monotonic_decreasing: bool | None
            if non_null_values.shape[0] > 1:
                try:
                    is_monotonic_increasing = bool(
                        non_null_values.is_monotonic_increasing
                    )
                    is_monotonic_decreasing = bool(
                        non_null_values.is_monotonic_decreasing
                    )
                except TypeError:
                    is_monotonic_increasing = None
                    is_monotonic_decreasing = None
            else:
                is_monotonic_increasing = None
                is_monotonic_decreasing = None

            summary = ProfileSummary(
                column=column,
                dtype=dtype,
                count=count,
                nulls=nulls,
                null_ratio=null_ratio,
                unique=unique,
                mean=mean_value,
                std=std_value,
                min=min_value,
                max=max_value,
                median=median_value,
                quantiles=quantiles_map,
                top_values=top_values,
                is_monotonic_increasing=is_monotonic_increasing,
                is_monotonic_decreasing=is_monotonic_decreasing,
            )
            summaries.append(summary)
        return summaries

    @staticmethod
    def _normalise_value(value: Any) -> Any:
        """Convert pandas/numpy scalars into native Python types for reporting."""

        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, pd.Timestamp):
            return value.isoformat()
        return value


@dataclass(slots=True)
class DriftReport:
    """Summarise detected drift for a monitored feature."""

    column: str
    statistic: float
    threshold: float
    drifted: bool


@dataclass(slots=True)
class DriftCalibration:
    """Details returned when calibrating the drift detector sensitivity."""

    threshold: float
    quantile: float
    iterations: int
    sample_size: int | None
    divergences: dict[str, tuple[float, ...]]


class DriftDetector:
    """Detect significant dataset drift using Jensen-Shannon divergence."""

    def __init__(self, *, threshold: float = 0.15, bins: int = 30) -> None:
        self._threshold = threshold
        self._bins = bins

    @property
    def threshold(self) -> float:
        """Current divergence threshold used to flag drift."""

        return self._threshold

    def compare(
        self, baseline: pd.DataFrame, candidate: pd.DataFrame
    ) -> list[DriftReport]:
        reports: list[DriftReport] = []
        for column in candidate.select_dtypes(include=[np.number]).columns:
            baseline_series = baseline[column].dropna().to_numpy()
            candidate_series = candidate[column].dropna().to_numpy()
            if baseline_series.size == 0 or candidate_series.size == 0:
                reports.append(
                    DriftReport(
                        column=column,
                        statistic=float("nan"),
                        threshold=self._threshold,
                        drifted=False,
                    )
                )
                continue
            hist_range = (
                min(baseline_series.min(), candidate_series.min()),
                max(baseline_series.max(), candidate_series.max()),
            )
            baseline_hist, _ = np.histogram(
                baseline_series, bins=self._bins, range=hist_range, density=True
            )
            candidate_hist, _ = np.histogram(
                candidate_series, bins=self._bins, range=hist_range, density=True
            )
            divergence = float(
                jensenshannon(baseline_hist + 1e-12, candidate_hist + 1e-12)
            )
            reports.append(
                DriftReport(
                    column=column,
                    statistic=divergence,
                    threshold=self._threshold,
                    drifted=divergence > self._threshold,
                )
            )
        return reports

    def calibrate(
        self,
        baseline: pd.DataFrame,
        *,
        quantile: float = 0.95,
        iterations: int = 32,
        sample_size: int | None = None,
        random_state: np.random.Generator | int | None = None,
        apply: bool = True,
    ) -> DriftCalibration:
        """Estimate a threshold from baseline variability to tune sensitivity."""

        if not 0.0 < quantile < 1.0:
            raise ValueError("quantile must lie strictly between 0 and 1")
        if iterations <= 0:
            raise ValueError("iterations must be a positive integer")
        if sample_size is not None and sample_size < 2:
            raise ValueError("sample_size must be at least 2 when provided")

        if isinstance(random_state, np.random.Generator):
            rng = random_state
        else:
            rng = np.random.default_rng(random_state)

        divergences: dict[str, tuple[float, ...]] = {}
        aggregated: list[float] = []

        numeric_columns = baseline.select_dtypes(include=[np.number]).columns
        for column in numeric_columns:
            series = baseline[column].to_numpy(dtype=float, copy=False)
            series = series[np.isfinite(series)]
            if series.size < 2:
                divergences[column] = tuple()
                continue

            target_sample = int(sample_size or min(series.size, 512))
            replace = series.size < target_sample
            column_scores: list[float] = []
            for _ in range(iterations):
                sample_a = rng.choice(series, size=target_sample, replace=replace)
                sample_b = rng.choice(series, size=target_sample, replace=replace)
                min_val = float(min(sample_a.min(), sample_b.min()))
                max_val = float(max(sample_a.max(), sample_b.max()))
                if not np.isfinite(min_val) or not np.isfinite(max_val):
                    continue
                if min_val == max_val:
                    column_scores.append(0.0)
                    continue
                hist_range = (min_val, max_val)
                hist_a, _ = np.histogram(
                    sample_a, bins=self._bins, range=hist_range, density=True
                )
                hist_b, _ = np.histogram(
                    sample_b, bins=self._bins, range=hist_range, density=True
                )
                divergence = float(jensenshannon(hist_a + 1e-12, hist_b + 1e-12))
                column_scores.append(divergence)

            divergences[column] = tuple(column_scores)
            aggregated.extend(value for value in column_scores if np.isfinite(value))

        if aggregated:
            new_threshold = float(np.quantile(np.asarray(aggregated), quantile))
        else:
            new_threshold = self._threshold

        if apply:
            self._threshold = new_threshold

        return DriftCalibration(
            threshold=new_threshold,
            quantile=quantile,
            iterations=iterations,
            sample_size=sample_size,
            divergences=divergences,
        )


class SLAMonitor:
    """Track pipeline durations and flag SLA breaches."""

    def __init__(self, *, max_duration: timedelta) -> None:
        self._max_duration = max_duration
        self._breaches: list[str] = []

    def evaluate(self, entries: Iterable[AuditEntry]) -> list[str]:
        self._breaches.clear()
        for entry in entries:
            if entry.duration_seconds > self._max_duration.total_seconds():
                message = (
                    f"SLA breach for segment {entry.segment}: "
                    f"{entry.duration_seconds:.2f}s exceeds {self._max_duration.total_seconds():.2f}s"
                )
                self._breaches.append(message)
        return list(self._breaches)


class AutoReporter:
    """Generate concise execution reports for stakeholders."""

    def render(
        self,
        *,
        run_id: str,
        audit_entries: Iterable[AuditEntry],
        sla_findings: Iterable[str],
    ) -> str:
        entries = list(audit_entries)
        total_duration = sum(entry.duration_seconds for entry in entries)
        avg_duration = (
            mean(entry.duration_seconds for entry in entries) if entries else 0.0
        )
        lines = [
            f"Pipeline run {run_id}",
            f"Total segments: {len(entries)}",
            f"Total duration: {total_duration:.2f}s",
            f"Average segment duration: {avg_duration:.2f}s",
            "",
            "Segment breakdown:",
        ]
        for entry in entries:
            lines.append(
                f"- {entry.segment} [{entry.status}] took {entry.duration_seconds:.2f}s"
            )
        if sla_findings:
            lines.extend(["", "SLA findings:", *sla_findings])
        return "\n".join(lines)


class LoadSimulator:
    """Generate synthetic datasets to stress-test pipelines."""

    def simulate(
        self, *, rows: int, columns: dict[str, tuple[float, float]]
    ) -> pd.DataFrame:
        data: dict[str, np.ndarray] = {}
        for name, (mean_value, std_dev) in columns.items():
            data[name] = np.random.normal(mean_value, std_dev, size=rows)
        data["ts"] = pd.date_range(datetime.utcnow(), periods=rows, freq="s")
        return pd.DataFrame(data)


class ResourceScaler:
    """Naïve resource scaling heuristic based on queue length."""

    def __init__(self, *, min_workers: int = 1, max_workers: int = 16) -> None:
        self._min_workers = min_workers
        self._max_workers = max_workers

    def recommend(self, pending_runs: int) -> int:
        if pending_runs <= 0:
            return self._min_workers
        scale = min(self._max_workers, self._min_workers + pending_runs)
        return max(self._min_workers, scale)
