"""Adaptive sensory calibration utilities for VLPO pipelines."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Iterable, Literal

import numpy as np
import pandas as pd

CalibrationMode = Literal["ema_minmax", "robust_quantile"]


@dataclass(slots=True)
class SensoryCalibrationConfig:
    """Configuration for sensory calibration windows."""

    mode: CalibrationMode = "ema_minmax"
    calibration_window: int = 256
    ema_alpha: float = 0.2
    quantile_low: float = 0.05
    quantile_high: float = 0.95
    epsilon: float = 1e-8


class SensoryCalibrator:
    """Calibrate per-channel scaling ranges before steady-state operation."""

    def __init__(
        self,
        channels: Iterable[str],
        config: SensoryCalibrationConfig | None = None,
    ) -> None:
        self._channels = tuple(channels)
        self._config = config or SensoryCalibrationConfig()
        self._min_max: dict[str, tuple[float, float]] = {}
        self._buffers: dict[str, deque[float]] = {
            channel: deque(maxlen=self._config.calibration_window)
            for channel in self._channels
        }
        self._samples_seen = 0
        self._steady_state = False

    @property
    def channels(self) -> tuple[str, ...]:
        return self._channels

    @property
    def steady_state(self) -> bool:
        return self._steady_state

    def scales(self) -> dict[str, tuple[float, float]]:
        return dict(self._min_max)

    def update(self, frame: pd.DataFrame) -> None:
        if self._steady_state or frame.empty:
            return

        for channel in self._channels:
            if channel not in frame.columns:
                continue
            values = frame[channel].to_numpy(dtype=float)
            finite = values[np.isfinite(values)]
            if finite.size == 0:
                continue

            if self._config.mode == "ema_minmax":
                current_min = float(np.min(finite))
                current_max = float(np.max(finite))
                if channel not in self._min_max:
                    self._min_max[channel] = (current_min, current_max)
                else:
                    prev_min, prev_max = self._min_max[channel]
                    alpha = self._config.ema_alpha
                    next_min = (1.0 - alpha) * prev_min + alpha * current_min
                    next_max = (1.0 - alpha) * prev_max + alpha * current_max
                    self._min_max[channel] = (next_min, next_max)
            else:
                buffer = self._buffers[channel]
                buffer.extend(float(val) for val in finite)
                if buffer:
                    buffered = np.asarray(buffer, dtype=float)
                    low = float(np.quantile(buffered, self._config.quantile_low))
                    high = float(np.quantile(buffered, self._config.quantile_high))
                    self._min_max[channel] = (low, high)

        self._samples_seen += int(frame.shape[0])
        if self._samples_seen >= self._config.calibration_window:
            self._steady_state = True

    def transform(self, frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame.copy()

        scaled = frame.copy()
        for channel, (min_val, max_val) in self._min_max.items():
            if channel not in scaled.columns:
                continue
            values = scaled[channel].to_numpy(dtype=float)
            denom = max(max_val - min_val, self._config.epsilon)
            normalized = (values - min_val) / denom
            scaled[channel] = np.clip(normalized, 0.0, 1.0)
        return scaled

    def normalize(self, frame: pd.DataFrame) -> pd.DataFrame:
        self.update(frame)
        return self.transform(frame)


__all__ = ["SensoryCalibrationConfig", "SensoryCalibrator"]
