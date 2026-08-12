# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Dopamine prediction network — research-tier moving-average tracker.

⚠️ SCOPE OF NEURO-NAMING — read before extending.

This module uses biological vocabulary (``_dopamine_levels``, ``_serotonin``,
``_norepinephrine``) as decorative scalar dials updated by ad-hoc multiplicative
rules. It is NOT a functional homologue of midbrain dopamine — there is no
TD prediction error, no eligibility trace, no D1/D2 receptor model, no
phasic-vs-tonic decomposition.

For genuine Schultz-style RPE see:
  * ``backtest/dopamine_td.py``                  — Numba-accelerated TD(0)
  * ``core/neuro/dopamine_execution_adapter.py`` — RPE bridge to NeuroSignalBus
  * ``src/geosync/core/neuro/dopamine/dopamine_controller.py`` — full controller

Use ``DopaminePredictionNetwork`` only as a research-tier moving-average tracker
where the bio-naming is an analogy, not a contract. Do NOT wire its outputs
into any module that depends on INV-DA1..7.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import Any, Dict

import numpy as np

from .config import NeuroAdvancedConfig


class DopaminePredictionNetwork:
    """Implements dopamine prediction errors and neuromodulator tracking."""

    def __init__(self, config: NeuroAdvancedConfig):
        self._cfg = config
        self._learning_rate = config.dpa.learning_rate
        self._decay = config.dpa.decay_rate
        self._expected: Dict[str, float] = {}
        self._dopamine_levels: Dict[str, float] = {}
        self._errors: deque[Dict[str, Any]] = deque(maxlen=config.history_size)
        self._serotonin = 1.0
        self._norepinephrine = 1.0

    @staticmethod
    def _key(asset: str, strategy: str) -> str:
        return f"{asset}_{strategy}"

    def update(
        self,
        asset: str,
        strategy: str,
        actual_reward: float,
        expected_reward: float | None = None,
    ) -> Dict[str, float]:
        key = self._key(asset, strategy)
        baseline = self._expected.get(key, 0.0)
        expected = baseline if expected_reward is None else float(expected_reward)
        prediction_error = float(actual_reward) - expected

        effective_lr = self._learning_rate * (1.0 + float(np.tanh(abs(prediction_error))))
        new_expected = expected + effective_lr * prediction_error * self._norepinephrine
        self._expected[key] = new_expected

        dopamine_signal = float(np.tanh(prediction_error * (2.5 if prediction_error > 0 else 1.5)))
        current_level = self._dopamine_levels.get(key, 0.5)
        new_level = float(
            np.clip(
                current_level * self._decay + dopamine_signal * (1 - self._decay),
                0.0,
                1.0,
            )
        )
        self._dopamine_levels[key] = new_level

        if prediction_error < 0:
            self._serotonin = max(0.5, self._serotonin * 0.98)
        else:
            self._serotonin = min(1.6, self._serotonin * 1.01)
        if abs(prediction_error) > 0.05:
            self._norepinephrine = min(1.6, self._norepinephrine * 1.02)
        else:
            self._norepinephrine = max(0.7, self._norepinephrine * 0.99)

        self._errors.append(
            {
                "timestamp": datetime.now(),
                "key": key,
                "prediction_error": prediction_error,
                "dopamine_signal": dopamine_signal,
                "learning_rate": effective_lr,
            }
        )

        return {
            "prediction_error": prediction_error,
            "dopamine_signal": dopamine_signal,
            "dopamine_level": new_level,
            "expected_reward": new_expected,
            "learning_rate_used": effective_lr,
            "serotonin": self._serotonin,
            "norepinephrine": self._norepinephrine,
        }

    def get_risk_modulation(self, asset: str, strategy: str) -> float:
        level = float(self._dopamine_levels.get(self._key(asset, strategy), 0.5))
        base = 1.0 - (level - 0.5) * 0.3 * self._serotonin
        bounds = self._cfg.dpa
        return float(np.clip(base, bounds.risk_modulation_min, bounds.risk_modulation_max))

    def state(self) -> Dict[str, Any]:
        dopamine_values = list(self._dopamine_levels.values())
        avg_da = float(np.mean(dopamine_values)) if dopamine_values else 0.5
        recent = list(self._errors)[-100:]
        avg_pe = float(np.mean([entry["prediction_error"] for entry in recent])) if recent else 0.0
        return {
            "dopamine_levels": dict(self._dopamine_levels),
            "expected_rewards": dict(self._expected),
            "avg_dopamine_level": avg_da,
            "avg_prediction_error": avg_pe,
            "serotonin_level": self._serotonin,
            "norepinephrine_level": self._norepinephrine,
        }
