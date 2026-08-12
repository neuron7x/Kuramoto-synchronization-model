# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Monitoring utilities for the advanced neuro module."""

from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import Any, Dict

from .config import NeuroAdvancedConfig


class NeuroStateMonitor:
    """Aggregates metrics and provides a lightweight dashboard view."""

    def __init__(self, config: NeuroAdvancedConfig):
        self._history: deque[Dict[str, Any]] = deque(maxlen=config.history_size)
        self._metrics: Dict[str, Dict[str, Any]] = {}
        self._start_time = datetime.now()

    def record(self, metric_type: str, data: Dict[str, Any]) -> None:
        self._history.append({"timestamp": datetime.now(), "type": metric_type, "data": data})
        self._aggregate(metric_type, data)

    def dashboard(self) -> Dict[str, Any]:
        return {
            "uptime": str(datetime.now() - self._start_time),
            "records": len(self._history),
            "metrics": self._metrics,
        }

    def _aggregate(self, metric_type: str, data: Dict[str, Any]) -> None:
        metric = self._metrics.setdefault(metric_type, {})
        for key, value in data.items():
            if not isinstance(value, (int, float)):
                continue
            stats = metric.setdefault(
                key,
                {
                    "current": 0.0,
                    "average": 0.0,
                    "min": value,
                    "max": value,
                    "count": 0,
                },
            )
            stats["current"] = float(value)
            stats["average"] = (stats["average"] * stats["count"] + float(value)) / (
                stats["count"] + 1
            )
            stats["count"] += 1
            stats["min"] = min(stats["min"], float(value))
            stats["max"] = max(stats["max"], float(value))
