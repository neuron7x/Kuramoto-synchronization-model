from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Optional

from .params import PredictiveConfig


@dataclass
class PredictiveState:
    mu: Dict[str, float]
    error: Dict[str, float]


@dataclass
class PredictiveCoder:
    """Predictive coding module that emits aggregated prediction error.

    Maintains stateful prediction means across steps; errors reflect the most
    recent observation update cadence.
    """

    cfg: PredictiveConfig = field(default_factory=PredictiveConfig)
    _mu: Dict[str, float] = field(default_factory=dict, init=False)
    _error_scale: Dict[str, float] = field(default_factory=dict, init=False)
    _last_error: Optional[Dict[str, float]] = field(default=None, init=False)

    def _ensure_mu(self, values: Dict[str, float]) -> None:
        for key in self.cfg.keys:
            self._mu.setdefault(key, float(values.get(key, 0.0)))

    def _update_error_scale(self, errors: Dict[str, float]) -> None:
        for key, error in errors.items():
            abs_error = abs(error)
            previous = self._error_scale.get(key, abs_error)
            scale = self.cfg.decay * previous + (1.0 - self.cfg.decay) * abs_error
            self._error_scale[key] = scale

    def normalize_errors(self, errors: Dict[str, float]) -> Dict[str, float]:
        normalized: Dict[str, float] = {}
        for key, error in errors.items():
            scale = max(
                self._error_scale.get(key, 0.0),
                self.cfg.prediction_error_scale,
                1e-6,
            )
            normalized[key] = math.tanh(error / scale)
        return normalized

    def step(self, obs: Dict[str, float]) -> PredictiveState:
        values = {k: float(obs.get(k, 0.0)) for k in self.cfg.keys}
        self._ensure_mu(values)

        errors: Dict[str, float] = {}
        for key, value in values.items():
            mu = self._mu.get(key, value)
            mu = self.cfg.decay * mu + (1.0 - self.cfg.decay) * value
            self._mu[key] = mu
            errors[key] = value - mu

        self._update_error_scale(errors)
        self._last_error = dict(errors)
        return PredictiveState(mu=dict(self._mu), error=errors)

    def snapshot(self) -> Dict[str, Dict[str, float] | None]:
        """Return the latest mean state and last error if available."""
        last_error = None if not self._last_error else dict(self._last_error)
        return {"mu": dict(self._mu), "error": last_error}

    def error_energy(self, obs: Dict[str, float]) -> float:
        state = self.step(obs)
        if not state.error:
            return 0.0
        normalized = self.normalize_errors(state.error)
        magnitude = sum(abs(v) for v in normalized.values()) / len(normalized)
        return self.cfg.error_gain * magnitude
