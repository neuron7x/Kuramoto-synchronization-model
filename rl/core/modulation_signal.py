"""Modulation signal controllers for risk-weighted learning updates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(slots=True)
class ModulationSignalConfig:
    """Configuration for modulation-signal scaling."""

    base_scale: float = 1.0
    rpe_weight: float = 0.6
    threat_weight: float = 0.8
    orexin_weight: float = 0.3
    min_scale: float = 0.1
    max_scale: float = 1.5

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, object] | None
    ) -> "ModulationSignalConfig":
        if not payload:
            return cls()
        return cls(
            base_scale=float(payload.get("base_scale", cls.base_scale)),
            rpe_weight=float(payload.get("rpe_weight", cls.rpe_weight)),
            threat_weight=float(payload.get("threat_weight", cls.threat_weight)),
            orexin_weight=float(payload.get("orexin_weight", cls.orexin_weight)),
            min_scale=float(payload.get("min_scale", cls.min_scale)),
            max_scale=float(payload.get("max_scale", cls.max_scale)),
        )


@dataclass(slots=True)
class ModulationSignalDecision:
    """Derived modulation decision for a learning update."""

    scale: float
    risk_score: float
    arousal_boost: float
    rpe_abs: float
    orexin: float
    threat: float


class ModulationSignalController:
    """Controller generating risk-weighted modulation signals."""

    def __init__(self, config: ModulationSignalConfig | None = None) -> None:
        self._config = config or ModulationSignalConfig()

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, object] | None
    ) -> "ModulationSignalController":
        return cls(ModulationSignalConfig.from_mapping(payload))

    def compute(
        self,
        rpe_metrics: Mapping[str, float],
        *,
        orexin: float,
        threat: float,
    ) -> ModulationSignalDecision:
        rpe_abs = float(rpe_metrics.get("rpe_abs", 0.0))
        risk_score = (rpe_abs * self._config.rpe_weight) + (
            threat * self._config.threat_weight
        )
        arousal_boost = orexin * self._config.orexin_weight
        raw_scale = self._config.base_scale + arousal_boost - risk_score
        scale = max(self._config.min_scale, min(self._config.max_scale, raw_scale))
        return ModulationSignalDecision(
            scale=scale,
            risk_score=risk_score,
            arousal_boost=arousal_boost,
            rpe_abs=rpe_abs,
            orexin=orexin,
            threat=threat,
        )
