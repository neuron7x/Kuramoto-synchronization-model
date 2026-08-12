# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from core.neuro.amm import AdaptiveMarketMind, AMMConfig
from core.neuro.quantile import P2Quantile
from core.neuro.sizing import SizerConfig, position_size

Float = np.float32


@dataclass
class AMMStrategyConfig:
    amm: AMMConfig = field(default_factory=AMMConfig)
    q_lo: float = 0.2
    q_hi: float = 0.8
    R_min: float = 0.45
    use_external_entropy: bool = False
    sizer: SizerConfig = field(default_factory=SizerConfig)


class AMMComboStrategy:
    """AMM + (R, kappa) фільтри + онлайн P² квантилі + ризикований сайзинг."""

    def __init__(self, cfg: AMMStrategyConfig):
        self.cfg = cfg
        self.amm = AdaptiveMarketMind(cfg.amm, use_internal_entropy=not cfg.use_external_entropy)
        self._qlo = P2Quantile(cfg.q_lo)
        self._qhi = P2Quantile(cfg.q_hi)
        self._sigma = Float(1e-4)

    def on_step(self, x_t: float, R_t: float, kappa_t: float, H_t: float | None = None) -> dict:
        out = self.amm.update(x_t, R_t, kappa_t, H_t)
        S = Float(out["amm_pulse"])
        qlo = self._qlo.update(S)
        qhi = self._qhi.update(S)

        action = "HOLD"
        direction = 0
        if S <= qlo:
            action = "EXIT_ALL"
            direction = 0
        elif R_t >= self.cfg.R_min and S >= qhi:
            direction = +1 if out["amm_valence"] > 0 else -1
            action = "ENTER_LONG" if direction > 0 else "ENTER_SHORT"

        self._sigma = Float(0.98) * self._sigma + Float(0.02) * Float(abs(out["pe"]))

        size = position_size(
            direction,
            out["amm_precision"],
            float(S),
            float(self._sigma),
            self.cfg.sizer,
        )
        return {
            "action": action,
            "direction": direction,
            "size": float(size),
            "pulse": float(S),
            "precision": out["amm_precision"],
            "valence": out["amm_valence"],
            "q_lo": float(qlo),
            "q_hi": float(qhi),
            "est_sigma": float(self._sigma),
        }
