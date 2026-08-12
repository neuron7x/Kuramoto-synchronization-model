# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

from .neuro_params import SensoryConfig
from .sensory_schema import SensorySchemaResult
from .state import clamp


@dataclass
class SensorySnapshot:
    filtered: Dict[str, float]
    temporal: Dict[str, float]
    spatial: Dict[str, float]
    quality_flags: Dict[str, list[str]] = field(default_factory=dict)


@dataclass
class SensoryFilter:
    """Retina-inspired filter with temporal contrast and lateral suppression."""

    cfg: SensoryConfig = field(default_factory=SensoryConfig)
    _prev: Dict[str, float] = field(default_factory=dict, init=False)

    def _neighbor_average(self, key: str, values: Dict[str, float]) -> float:
        neighbors = [values[k] for k in self.cfg.keys if k != key]
        if not neighbors:
            return values.get(key, 0.0)
        return sum(neighbors) / len(neighbors)

    def _ensure_prev(self, values: Dict[str, float]) -> None:
        for key in self.cfg.keys:
            self._prev.setdefault(key, values.get(key, 0.0))

    def transform(self, schema_output: SensorySchemaResult) -> SensorySnapshot:
        values = {k: schema_output.normalized.get(k, 0.0) for k in self.cfg.keys}
        self._ensure_prev(values)

        filtered: Dict[str, float] = {}
        temporal: Dict[str, float] = {}
        spatial: Dict[str, float] = {}
        for key, value in values.items():
            prev = self._prev.get(key, value)
            neighbor = self._neighbor_average(key, values)
            temporal_delta = value - prev
            spatial_delta = value - neighbor
            signal = (
                value
                + self.cfg.contrast_gain * self.cfg.temporal_lambda * temporal_delta
                + self.cfg.contrast_gain * self.cfg.spatial_lambda * spatial_delta
            )
            filtered[key] = clamp(signal)
            temporal[key] = temporal_delta
            spatial[key] = spatial_delta

        self._prev.update(values)
        return SensorySnapshot(
            filtered=filtered,
            temporal=temporal,
            spatial=spatial,
            quality_flags=dict(schema_output.quality_flags),
        )

    def apply(self, schema_output: SensorySchemaResult) -> Dict[str, float]:
        """Return filtered observation values merged with normalized output."""

        snapshot = self.transform(schema_output)
        merged = dict(schema_output.normalized)
        merged.update(snapshot.filtered)
        return merged
