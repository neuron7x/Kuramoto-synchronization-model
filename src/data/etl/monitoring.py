"""Monitoring, quality, and reporting utilities for ETL pipelines."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import mean
from typing import Iterable

import numpy as np
import pandas as pd
from scipy.spatial.distance import jensenshannon

from .stores import AuditEntry


@dataclass(slots=True)
class ProfileSummary:
    """Key statistics describing a dataset distribution."""

    column: str
    count: int
    nulls: int
    mean: float | None
    std: float | None
    min: float | None
    max: float | None


class DistributionProfiler:
    """Build descriptive statistics to understand dataset shape."""

    def profile(self, frame: pd.DataFrame) -> list[ProfileSummary]:
        summaries: list[ProfileSummary] = []
        for column in frame.columns:
            series = frame[column]
            numeric_series = series.dropna()
            numeric_values = numeric_series.astype(float) if not numeric_series.empty else numeric_series
            summary = ProfileSummary(
                column=column,
                count=int(series.shape[0]),
                nulls=int(series.isna().sum()),
                mean=float(numeric_values.mean()) if not numeric_series.empty else None,
                std=float(numeric_values.std()) if numeric_series.shape[0] > 1 else None,
                min=float(numeric_values.min()) if not numeric_series.empty else None,
                max=float(numeric_values.max()) if not numeric_series.empty else None,
            )
            summaries.append(summary)
        return summaries


@dataclass(slots=True)
class DriftReport:
    """Summarise detected drift for a monitored feature."""

    column: str
    statistic: float
    threshold: float
    drifted: bool


class DriftDetector:
    """Detect significant dataset drift using Jensen-Shannon divergence."""

    def __init__(self, *, threshold: float = 0.15, bins: int = 30) -> None:
        self._threshold = threshold
        self._bins = bins

    def compare(self, baseline: pd.DataFrame, candidate: pd.DataFrame) -> list[DriftReport]:
        reports: list[DriftReport] = []
        for column in candidate.select_dtypes(include=[np.number]).columns:
            baseline_series = baseline[column].dropna().to_numpy()
            candidate_series = candidate[column].dropna().to_numpy()
            if baseline_series.size == 0 or candidate_series.size == 0:
                reports.append(
                    DriftReport(column=column, statistic=float("nan"), threshold=self._threshold, drifted=False)
                )
                continue
            hist_range = (
                min(baseline_series.min(), candidate_series.min()),
                max(baseline_series.max(), candidate_series.max()),
            )
            baseline_hist, _ = np.histogram(baseline_series, bins=self._bins, range=hist_range, density=True)
            candidate_hist, _ = np.histogram(candidate_series, bins=self._bins, range=hist_range, density=True)
            divergence = float(jensenshannon(baseline_hist + 1e-12, candidate_hist + 1e-12))
            reports.append(
                DriftReport(
                    column=column,
                    statistic=divergence,
                    threshold=self._threshold,
                    drifted=divergence > self._threshold,
                )
            )
        return reports


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

    def render(self, *, run_id: str, audit_entries: Iterable[AuditEntry], sla_findings: Iterable[str]) -> str:
        entries = list(audit_entries)
        total_duration = sum(entry.duration_seconds for entry in entries)
        avg_duration = mean(entry.duration_seconds for entry in entries) if entries else 0.0
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

    def simulate(self, *, rows: int, columns: dict[str, tuple[float, float]]) -> pd.DataFrame:
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
