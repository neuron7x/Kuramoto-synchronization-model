# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Dynamic fractional deterministic annealing helper."""

from __future__ import annotations

import numpy as np


class DFGDA:
    """Update rule that adapts learning rates based on threat scores."""

    def __init__(self, eta0: float = 1e-3, frac0: float = 0.1, frac_max: float = 0.5) -> None:
        self.eta = float(eta0)
        self.frac = float(frac0)
        self.frac_max = float(frac_max)

    def step(self, threat_score: float) -> tuple[float, float]:
        if not 0.0 <= threat_score <= 1.0:
            raise ValueError("threat_score must lie in [0, 1]")
        self.frac = float(np.clip(self.frac + 0.1 * (threat_score - 0.5), 0.0, self.frac_max))
        self.eta = float(self.eta * (0.95 + 0.1 * (0.5 - abs(threat_score - 0.5))))
        return self.eta, self.frac
