# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Iterable, Tuple

import numpy as np


@dataclass(slots=True)
class SensoryHabituationConfig:
    """Control the rate of sensory gating adaptation."""

    half_life: int = 150
    min_sensitivity: float = 0.3
    recovery_hl: int = 600


class SensoryHabituation:
    """Context-aware sensitivity modulation using cosine similarity."""

    def __init__(self, cfg: SensoryHabituationConfig | None = None) -> None:
        self.cfg = cfg or SensoryHabituationConfig()
        self._ctx_vec: np.ndarray | None = None
        self._sensitivity: float = 1.0
        self._ticks_in_ctx: int = 0

    def _normalize(self, vec: np.ndarray) -> np.ndarray:
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec

    def _cosine_sim(self, features: Iterable[float]) -> float:
        vec = self._normalize(np.asarray(features, dtype=float))
        if self._ctx_vec is None:
            return 1.0
        return float(np.dot(vec, self._ctx_vec))

    def update(self, features: Iterable[float]) -> Tuple[float, Dict[str, float]]:
        """Update sensitivity given the current feature context."""

        sim = self._cosine_sim(features)
        if self._ctx_vec is None:
            self._ctx_vec = self._normalize(np.asarray(features, dtype=float))
            self._ticks_in_ctx = 0
            sim = 1.0

        if sim > 0.95:
            self._ticks_in_ctx += 1
            lam = math.log(2.0) / max(1, self.cfg.half_life)
            self._sensitivity = max(self.cfg.min_sensitivity, self._sensitivity * math.exp(-lam))
        else:
            vec = self._normalize(np.asarray(features, dtype=float))
            self._ctx_vec = vec
            lam = math.log(2.0) / max(1, self.cfg.recovery_hl)
            self._sensitivity = min(1.0, 1.0 - (1.0 - self._sensitivity) * math.exp(-lam))
            self._ticks_in_ctx = 0

        return self._sensitivity, {
            "sensitivity": self._sensitivity,
            "ticks_in_ctx": float(self._ticks_in_ctx),
            "similarity": sim,
        }
