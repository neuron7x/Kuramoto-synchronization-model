# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from .neuro_params import PredictiveConfig


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
    _last_error: Optional[Dict[str, float]] = field(default=None, init=False)

    def _ensure_mu(self, values: Dict[str, float]) -> None:
        for key in self.cfg.keys:
            self._mu.setdefault(key, float(values.get(key, 0.0)))

    def step(self, obs: Dict[str, float]) -> PredictiveState:
        values = {k: float(obs.get(k, 0.0)) for k in self.cfg.keys}
        self._ensure_mu(values)

        errors: Dict[str, float] = {}
        for key, value in values.items():
            mu = self._mu.get(key, value)
            mu = self.cfg.decay * mu + (1.0 - self.cfg.decay) * value
            self._mu[key] = mu
            errors[key] = value - mu

        self._last_error = dict(errors)
        return PredictiveState(mu=dict(self._mu), error=errors)

    def snapshot(self) -> PredictiveState:
        """Return the latest mean state and last per-channel error."""
        last_error = dict(self._last_error) if self._last_error else {}
        return PredictiveState(mu=dict(self._mu), error=last_error)

    def error_energy(self, obs: Dict[str, float]) -> float:
        state = self.step(obs)
        if not state.error:
            return 0.0
        magnitude = sum(abs(v) for v in state.error.values()) / len(state.error)
        return self.cfg.error_gain * magnitude
