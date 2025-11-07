"""Homeostatic pressure helper."""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np


@dataclass
class HomeoConfig:
    """Configuration for the homeostatic module."""

    M_target: float = 0.8
    k_sigmoid: float = 5.0

    def __post_init__(self) -> None:
        self.M_target = float(self.M_target)
        self.k_sigmoid = float(self.k_sigmoid)


class HomeostaticModule:
    """Sigmoid pressure that nudges allocation scale toward the target."""

    def __init__(self, cfg: HomeoConfig = HomeoConfig()):
        self.cfg = cfg

    def pressure(self, M: float) -> float:
        deficit = max(0.0, self.cfg.M_target - float(M))
        return float(1.0 / (1.0 + np.exp(-self.cfg.k_sigmoid * deficit)))
