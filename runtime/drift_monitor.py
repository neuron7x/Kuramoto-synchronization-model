"""Lightweight drift monitoring utilities for runtime telemetry."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Iterable, Mapping, Optional

import numpy as np


@dataclass(frozen=True)
class DriftStatus:
    """Snapshot of drift detection outcome."""

    drifted: bool
    score: float
    metric_scores: Mapping[str, float]
    baseline_size: int
    window_size: int
    threshold: float
    timestamp: float = field(default_factory=time.time)


class DriftDetector:
    """Detect metric drift via rolling z-score comparisons."""

    def __init__(
        self,
        *,
        baseline_window: int = 50,
        detection_window: int = 20,
        threshold: float = 2.5,
        min_baseline: int = 30,
    ) -> None:
        if baseline_window <= 0 or detection_window <= 0:
            raise ValueError("Window sizes must be positive")
        self.baseline_window = baseline_window
        self.detection_window = detection_window
        self.threshold = threshold
        self.min_baseline = min_baseline
        self._history: Dict[str, Deque[float]] = defaultdict(
            lambda: deque(maxlen=baseline_window + detection_window)
        )

    def update(self, metrics: Mapping[str, float]) -> Optional[DriftStatus]:
        for key, value in metrics.items():
            if isinstance(value, (int, float)) and np.isfinite(value):
                self._history[key].append(float(value))

        return self._compute_status(metrics.keys())

    def _compute_status(self, keys: Iterable[str]) -> Optional[DriftStatus]:
        metric_scores: Dict[str, float] = {}
        baseline_size = 0
        for key in keys:
            history = self._history.get(key)
            if history is None:
                continue
            if len(history) < self.baseline_window + self.detection_window:
                baseline_size = max(baseline_size, len(history))
                continue
            baseline = np.asarray(
                list(history)[: self.baseline_window], dtype=float
            )
            detection = np.asarray(
                list(history)[-self.detection_window :], dtype=float
            )
            baseline_size = max(baseline_size, len(baseline))
            base_mean = float(np.mean(baseline))
            base_std = float(np.std(baseline))
            det_mean = float(np.mean(detection))
            denom = base_std if base_std > 1e-6 else 1.0
            metric_scores[key] = abs(det_mean - base_mean) / denom

        if baseline_size < self.min_baseline:
            return None

        score = max(metric_scores.values(), default=0.0)
        return DriftStatus(
            drifted=score >= self.threshold,
            score=score,
            metric_scores=metric_scores,
            baseline_size=baseline_size,
            window_size=self.detection_window,
            threshold=self.threshold,
        )
