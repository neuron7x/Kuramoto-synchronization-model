from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Dict, Iterable

from .params import SensoryConfig
from .state import clamp

log = logging.getLogger(__name__)


@dataclass
class SensorySnapshot:
    filtered: Dict[str, float]
    temporal: Dict[str, float]
    spatial: Dict[str, float]


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

    def _sanitize_value(self, key: str, raw_value: object) -> float:
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            log.warning(
                "SensoryFilter received non-numeric value for %s: %r; defaulting to 0.0",
                key,
                raw_value,
            )
            return 0.0
        if not math.isfinite(value):
            log.warning(
                "SensoryFilter received non-finite value for %s: %r; defaulting to 0.0",
                key,
                value,
            )
            return 0.0
        return value

    def transform(self, obs: Dict[str, float]) -> SensorySnapshot:
        values = {
            k: self._sanitize_value(k, obs.get(k, 0.0)) for k in self.cfg.keys
        }
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
        return SensorySnapshot(filtered=filtered, temporal=temporal, spatial=spatial)

    def apply(self, obs: Dict[str, float]) -> Dict[str, float]:
        """Return filtered observation values merged with original obs."""

        snapshot = self.transform(obs)
        merged = dict(obs)
        merged.update(snapshot.filtered)
        return merged
