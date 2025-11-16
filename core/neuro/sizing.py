"""Position sizing functions for neuro-adaptive trading systems.

This module implements volatility-targeted position sizing with dual modulation
from AMM pulse intensity and precision signals. The sizing logic dynamically
adjusts leverage based on market conditions and forecast confidence.

Key Components:
    SizerConfig: Configuration for target volatility and leverage limits
    pulse_weight: Convert AMM pulse to sizing weight [0, 1]
    precision_weight: Convert precision to sizing weight via log-sigmoid
    position_size: Main sizing function combining all factors

The sizing approach scales positions to achieve target portfolio volatility
while respecting maximum leverage constraints. Two additional factors modulate
the base size:
    1. Pulse weight: Only size positions when AMM pulse exceeds threshold
    2. Precision weight: Scale by forecast confidence (precision)

This creates a conservative sizing regime that allocates capital only when
the model exhibits both strong pulse signals and high prediction precision.

Example:
    >>> config = SizerConfig(target_vol=0.02, max_leverage=3.0)
    >>> direction = 1  # Long
    >>> size = position_size(direction, precision, pulse, est_vol, config)
    >>> print(f"Position size: {size:.2f}x leverage")
"""
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
