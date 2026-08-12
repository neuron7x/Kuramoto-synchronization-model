# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping

from .neuro_params import OBSERVATION_KEYS
from .state import clamp

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class SensoryChannel:
    name: str
    min: float
    max: float
    dtype: type = float
    nan_policy: str = "zero"
    scale: float | None = None
    clip: bool = True
    weight: float = 1.0
    confidence: float = 1.0
    confidence_floor: float = 0.0

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("SensoryChannel name must be non-empty.")
        if self.nan_policy not in {"drop", "zero", "hold-last"}:
            raise ValueError(f"Unsupported nan_policy: {self.nan_policy}")
        if self.scale is not None and self.scale <= 0:
            raise ValueError("SensoryChannel scale must be positive.")
        if self.scale is None and self.max <= self.min:
            raise ValueError("SensoryChannel max must exceed min.")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("SensoryChannel confidence must be between 0 and 1.")
        if not 0.0 <= self.confidence_floor <= 1.0:
            raise ValueError("SensoryChannel confidence_floor must be between 0 and 1.")


@dataclass
class SensorySchemaResult:
    normalized: Dict[str, float]
    quality_flags: Dict[str, List[str]]
    sensory_confidence: float


@dataclass
class SensorySchema:
    channels: tuple[SensoryChannel, ...] = field(default_factory=tuple)
    _last_values: Dict[str, float] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        names = [channel.name for channel in self.channels]
        if len(set(names)) != len(names):
            raise ValueError("SensorySchema channel names must be unique.")

    @classmethod
    def default(cls) -> "SensorySchema":
        return cls(
            channels=tuple(
                SensoryChannel(
                    name=key,
                    min=0.0,
                    max=1.0,
                    dtype=float,
                    nan_policy="zero",
                    scale=None,
                    clip=True,
                    weight=1.0,
                    confidence_floor=0.0,
                )
                for key in OBSERVATION_KEYS
            )
        )

    def validate(self, obs: Mapping[str, Any]) -> SensorySchemaResult:
        normalized: Dict[str, float] = {}
        quality_flags: Dict[str, List[str]] = {}
        confidence_scores: List[float] = []

        for channel in self.channels:
            flags: List[str] = []
            raw = obs.get(channel.name, None)
            missing = channel.name not in obs
            if missing:
                flags.append("missing")

            value = self._coerce_value(channel, raw, flags)

            if value is None or not math.isfinite(value):
                if not missing and "nan" not in flags:
                    flags.append("nan")
                value = self._apply_nan_policy(channel, flags)
                if channel.nan_policy == "drop":
                    quality_flags[channel.name] = flags
                    confidence_scores.append(self._channel_confidence(channel, flags))
                    continue

            if value is None:
                value = 0.0

            out_of_range = self._is_out_of_range(channel, value)
            if out_of_range:
                flags.append("out_of_range")

            normalized_value = self._normalize_value(channel, value)
            if channel.clip:
                normalized_value = clamp(normalized_value)

            normalized[channel.name] = normalized_value
            quality_flags[channel.name] = flags
            confidence_scores.append(self._channel_confidence(channel, flags))
            if "nan" not in flags and "missing" not in flags:
                self._last_values[channel.name] = value

        sensory_confidence = (
            clamp(sum(confidence_scores) / len(confidence_scores)) if confidence_scores else 0.0
        )
        return SensorySchemaResult(
            normalized=normalized,
            quality_flags=quality_flags,
            sensory_confidence=sensory_confidence,
        )

    def _coerce_value(self, channel: SensoryChannel, raw: Any, flags: List[str]) -> float | None:
        if raw is None:
            return None
        try:
            return channel.dtype(raw)
        except (TypeError, ValueError):
            flags.append("nan")
            return None

    def _apply_nan_policy(self, channel: SensoryChannel, flags: List[str]) -> float | None:
        if channel.nan_policy == "zero":
            return 0.0
        if channel.nan_policy == "hold-last":
            return self._last_values.get(channel.name, 0.0)
        if "missing" not in flags:
            flags.append("missing")
        return None

    def _normalize_value(self, channel: SensoryChannel, value: float) -> float:
        if channel.scale is not None:
            return value / channel.scale
        span = channel.max - channel.min
        return (value - channel.min) / span

    def _is_out_of_range(self, channel: SensoryChannel, value: float) -> bool:
        if channel.scale is not None:
            return value < 0.0 or value > channel.scale
        return value < channel.min or value > channel.max

    def _channel_confidence(self, channel: SensoryChannel, flags: Iterable[str]) -> float:
        if "missing" in flags or "nan" in flags:
            return channel.confidence_floor
        confidence = channel.confidence
        if "out_of_range" in flags:
            confidence *= 0.5
        return max(channel.confidence_floor, confidence)


__all__ = ["SCHEMA_VERSION", "SensoryChannel", "SensorySchema", "SensorySchemaResult"]
