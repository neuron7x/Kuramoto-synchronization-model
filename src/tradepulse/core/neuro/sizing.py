from __future__ import annotations

import math

import numpy as np

Float = np.float32


class SizerConfig:
    def __init__(
        self,
        target_vol: float = 0.02,
        max_leverage: float = 3.0,
        min_pulse: float = 0.0,
        max_pulse: float = 0.25,
        clip: float = 1.0,
    ):
        self.target_vol = Float(target_vol)
        self.max_leverage = Float(max_leverage)
        self.min_pulse = Float(min_pulse)
        self.max_pulse = Float(max_pulse)
        self.clip = Float(clip)


def pulse_weight(S: float, cfg: SizerConfig) -> float:
    S = Float(S)
    if S <= cfg.min_pulse:
        return 0.0
    w = float((S - cfg.min_pulse) / max(1e-8, (cfg.max_pulse - cfg.min_pulse)))
    return float(min(max(w, 0.0), 1.0))


def precision_weight(pi: float) -> float:
    z = math.log(max(pi, 1e-8))
    return float(1.0 / (1.0 + math.exp(-z)))


def position_size(
    direction: int, pi: float, S: float, est_sigma: float, cfg: SizerConfig
) -> float:
    if direction == 0:
        return 0.0
    w = pulse_weight(S, cfg) * precision_weight(pi)
    if est_sigma <= 1e-12:
        return 0.0
    L = float(w * (cfg.target_vol / float(est_sigma)))
    return float(np.clip(direction * L, -cfg.max_leverage, cfg.max_leverage))
