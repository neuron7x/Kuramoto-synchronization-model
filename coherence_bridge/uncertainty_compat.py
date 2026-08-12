# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Backward-compatible UncertaintyEstimator for coherence_bridge layer.

Wraps geosync.neuroeconomics.uncertainty.UncertaintyController
with the signal-dict API that coherence_bridge consumers expect.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass


def _to_float(v: object) -> float:
    if isinstance(v, (int, float)):
        f = float(v)
        return f if math.isfinite(f) else 0.0
    return 0.0


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(max(0.0, var))


@dataclass(frozen=True, slots=True)
class UncertaintyEstimate:
    aleatoric: float
    epistemic: float
    total: float
    surprise: float
    ambiguity_index: float
    is_novel: bool


class UncertaintyEstimator:
    """Signal-dict API for coherence_bridge decision_engine."""

    def __init__(self, window_size: int = 100, novelty_threshold: float = 0.7) -> None:
        self.window_size = window_size
        self.novelty_threshold = novelty_threshold
        self._gamma_history: deque[float] = deque(maxlen=window_size)
        self._r_history: deque[float] = deque(maxlen=window_size)
        self._ricci_history: deque[float] = deque(maxlen=window_size)
        self._regime_history: deque[str] = deque(maxlen=window_size)
        self._risk_history: deque[float] = deque(maxlen=window_size)

    def update(self, signal: dict[str, object]) -> UncertaintyEstimate:
        gamma = _to_float(signal.get("gamma"))
        r_val = _to_float(signal.get("order_parameter_R"))
        ricci = _to_float(signal.get("ricci_curvature"))
        regime = str(signal.get("regime") or "UNKNOWN")
        risk = _to_float(signal.get("risk_scalar"))

        self._gamma_history.append(gamma)
        self._r_history.append(r_val)
        self._ricci_history.append(ricci)
        self._regime_history.append(regime)
        self._risk_history.append(risk)

        if len(self._gamma_history) < 10:
            return UncertaintyEstimate(1.0, 1.0, 1.0, 1.0, 2.0, True)

        regime_risks = [
            r for r, reg in zip(self._risk_history, self._regime_history) if reg == regime
        ]
        aleatoric = min(1.0, _std(regime_risks) * 3.0) if len(regime_risks) >= 3 else 0.5

        gamma_vote = max(0.0, min(1.0, 1.0 - abs(gamma - 1.0)))
        r_vote = max(0.0, min(1.0, r_val))
        ricci_vote = max(0.0, min(1.0, 0.5 + 0.5 * math.tanh(ricci)))
        epistemic = min(1.0, _std([gamma_vote, r_vote, ricci_vote]) * 2.0)

        sigma_1 = 1.0 - _to_float(signal.get("regime_confidence"))
        gamma_list = list(self._gamma_history)
        if len(gamma_list) >= 3:
            diffs = [abs(gamma_list[i] - gamma_list[i - 1]) for i in range(1, len(gamma_list))]
            mean_gamma = sum(gamma_list) / len(gamma_list)
            sigma_2 = _std(diffs) / (abs(mean_gamma) + 1e-6)
        else:
            sigma_2 = 1.0
        ambiguity_index = sigma_2 / (sigma_1 + 1e-6)

        mean_risk = sum(self._risk_history) / len(self._risk_history)
        surprise = min(1.0, abs(risk - mean_risk) / (mean_risk + 0.01))

        regime_counts: dict[str, int] = {}
        for r in self._regime_history:
            regime_counts[r] = regime_counts.get(r, 0) + 1
        regime_freq = regime_counts.get(regime, 0) / len(self._regime_history)
        is_novel = regime_freq < 0.05 or surprise > self.novelty_threshold

        return UncertaintyEstimate(
            aleatoric=round(aleatoric, 4),
            epistemic=round(epistemic, 4),
            total=round(min(1.0, max(aleatoric, epistemic)), 4),
            surprise=round(surprise, 4),
            ambiguity_index=round(ambiguity_index, 4),
            is_novel=is_novel,
        )

    def kelly_discount(self, estimate: UncertaintyEstimate) -> float:
        return max(0.1, 1.0 - 0.9 * estimate.total)

    def is_ambiguity_zone(self, estimate: UncertaintyEstimate) -> bool:
        return estimate.ambiguity_index > 1.0
