# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import math
from collections import deque
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable

import numpy as np

from geosync.core.neuro.numeric_config import STABILITY_EPSILON

from ..desensitization.sensory_habituation import SensoryHabituation
from .desensitization import DesensitizationModule


def _softsign(x: float) -> float:
    return x / (1.0 + abs(x))


@dataclass(slots=True)
class NaKConfig:
    dd_soft_base: float = 0.14
    vol_ref_base: float = 0.028
    burst_z: float = 2.1
    refractory_ticks: int = 5
    reopen_hl: int = 90
    min_gate: float = 0.32
    p_exp_default: float = 0.05
    K_p: float = 2.8
    K_i: float = 0.9
    I_scale: float = 4.5
    E_max: float = 12.0
    E_init: float = 6.0
    rec_gain_base: float = 0.015
    enable_sens_habituation: bool = True


class NaKControllerV4_2:
    """Homeostatic controller with neuro-inspired gating heuristics."""

    def __init__(self, strategy_id: int, cfg: NaKConfig | None = None) -> None:
        self.cfg = cfg or NaKConfig()
        self.strategy_id = strategy_id
        self.E = self.cfg.E_init
        self.I_integral = 0.0
        self.scale = 1.0
        self.lambda_ = 0.05
        self._p_hist: deque[float] = deque(maxlen=50)
        self._refr_ticks = 0
        self.sensory = SensoryHabituation() if self.cfg.enable_sens_habituation else None
        self.desens = DesensitizationModule()
        self._sens = 1.0
        self.r_mode = 1.0
        self._breached = False
        self._reopen_phase = 0.0

    def _act(self, x: float) -> float:
        return _softsign(x)

    def snapshot(self) -> Dict[str, Any]:
        return {
            "E": self.E,
            "I": self.I_integral,
            "lambda_": self.lambda_,
            "scale": self.scale,
            "r_mode": self.r_mode,
            "reopen_phase": self._reopen_phase,
        }

    def update(
        self,
        *,
        p: float,
        v: float,
        drawdown: float,
        features: Iterable[float] | None = None,
        p_exp_for_stim: float | None = None,
        hpa_tone: float = 0.0,
    ) -> tuple[float, Dict[str, float]]:
        """Advance the controller state for one market tick."""

        log: Dict[str, float] = {}
        features = features or [v]
        drawdown = max(drawdown, -1.0)
        p_exp = (
            p_exp_for_stim
            if p_exp_for_stim is not None
            else (float(np.mean(self._p_hist)) if self._p_hist else self.cfg.p_exp_default)
        )
        self._p_hist.append(p)

        if len(self._p_hist) > 1:
            std_p = float(np.std(self._p_hist)) or STABILITY_EPSILON
            z = (p - p_exp) / std_p
            if abs(z) >= self.cfg.burst_z:
                self._refr_ticks = self.cfg.refractory_ticks
        log["z"] = locals().get("z", 0.0)
        log["rpe_proxy"] = p - p_exp

        kp_eff = self.cfg.K_p * (0.5 if self._refr_ticks > 0 else 1.0)
        self._refr_ticks = max(0, self._refr_ticks - 1)
        log["refractory_left"] = float(self._refr_ticks)

        err = p_exp - p
        pi_p = kp_eff * self._act(err / max(STABILITY_EPSILON, self.scale))
        pi_i = self.cfg.K_i * self._act(self.I_integral / max(STABILITY_EPSILON, self.cfg.I_scale))
        u = pi_p + pi_i
        self.I_integral += err

        rec_gain = self.cfg.rec_gain_base * (1.0 + hpa_tone - 0.3 * (drawdown < -0.02))
        self.E += rec_gain
        self.E = float(np.clip(self.E, 0.0, self.cfg.E_max))

        if self.sensory:
            sens_mult, _ = self.sensory.update(features)
            self._sens = max(0.65, sens_mult) if v > 0.045 else sens_mult
        log["sens_mult"] = self._sens

        regime_mult = 1.8 if v > 0.045 else 1.0
        dd_soft = self.cfg.dd_soft_base * regime_mult
        vol_ref = self.cfg.vol_ref_base * regime_mult
        danger = (
            (-drawdown / max(STABILITY_EPSILON, dd_soft))
            + 0.5 * math.log1p(v / max(STABILITY_EPSILON, vol_ref))
            + hpa_tone
        )
        gate = 1.0 / (1.0 + math.exp(danger - 1.2))
        gate = max(self.cfg.min_gate, min(1.0, gate))

        if -drawdown >= dd_soft * 1.3:
            self._breached = True
            gate = self.cfg.min_gate

        if self._breached and -drawdown < dd_soft * 0.7:
            lam = math.log(2.0) / max(1, self.cfg.reopen_hl)
            self._reopen_phase += (1.0 - self._reopen_phase) * (1 - math.exp(-lam * 2))
            gate = self.cfg.min_gate + (1.0 - self.cfg.min_gate) * self._reopen_phase
            if self._reopen_phase >= 0.95:
                self._breached = False
                self._reopen_phase = 0.0

        self.r_mode = gate
        log["reopen_phase"] = self._reopen_phase
        log["suspend"] = float(gate < 0.5)
        log["danger"] = danger
        log["r_mode"] = self.r_mode

        ei_current = self.E / max(STABILITY_EPSILON, self.I_integral + 1.0)
        self.scale, self.lambda_ = self.desens.update(p, ei_current, ht5=hpa_tone)
        log["lambda_"] = log["lambda"] = self.lambda_
        log["scale"] = self.scale
        log["EI"] = ei_current

        r_final = u * self.r_mode * self._sens * self.lambda_
        log["r_final"] = r_final
        return r_final, log

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self.cfg) | {"state": self.snapshot()}

    @classmethod
    def from_dict(cls, data: Dict[str, Any], strategy_id: int) -> "NaKControllerV4_2":
        cfg_data = {k: v for k, v in data.items() if k in NaKConfig.__annotations__}
        cfg = NaKConfig(**cfg_data)
        ctrl = cls(strategy_id, cfg)
        state = data.get("state", {})
        ctrl.E = state.get("E", ctrl.E)
        ctrl.I_integral = state.get("I", ctrl.I_integral)
        ctrl.lambda_ = state.get("lambda_", ctrl.lambda_)
        ctrl._reopen_phase = state.get("reopen_phase", ctrl._reopen_phase)
        return ctrl
