from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Tuple

from tradepulse.core.neuro.numeric_config import STABILITY_EPSILON


@dataclass(slots=True)
class ThreatGateConfig:
    """Configuration for threat gating dynamics."""

    dd_soft: float = 0.14
    dd_hard: float = 0.18
    vol_ref: float = 0.028
    hpa_gain: float = 1.0
    reopen_hl: int = 90
    min_gate: float = 0.32


class ThreatGate:
    """Adaptive gating that reacts to drawdown, volatility and stress tone."""

    def __init__(self, cfg: ThreatGateConfig | None = None) -> None:
        self.cfg = cfg or ThreatGateConfig()
        self._gate = 1.0
        self._breached = False
        self._ticks = 0
        self._reopen_phase = 0.0

    def update(
        self,
        *,
        drawdown: float,
        vol: float,
        hpa_tone: float = 0.0,
    ) -> Tuple[float, Dict[str, float]]:
        """Compute the gate intensity for the current stress conditions."""

        dd = max(0.0, drawdown)
        vol_ratio = vol / max(STABILITY_EPSILON, self.cfg.vol_ref)
        danger = (
            dd / max(STABILITY_EPSILON, self.cfg.dd_soft)
            + 0.5 * math.log1p(vol_ratio)
            + self.cfg.hpa_gain * hpa_tone
        )
        gate = 1.0 / (1.0 + math.exp(danger - 1.2))
        gate = max(self.cfg.min_gate, min(1.0, gate))

        if dd >= self.cfg.dd_hard:
            self._breached = True
            gate = self.cfg.min_gate

        if self._breached and dd < self.cfg.dd_soft:
            lam = math.log(2.0) / max(1, self.cfg.reopen_hl)
            self._reopen_phase = min(
                1.0,
                self._reopen_phase
                + (1.0 - self._reopen_phase) * (1 - math.exp(-lam * 2)),
            )
            gate = self.cfg.min_gate + (1.0 - self.cfg.min_gate) * self._reopen_phase
            if self._reopen_phase >= 0.95:
                self._breached = False
                self._reopen_phase = 0.0

        self._ticks += 1
        self._gate = gate
        return gate, {
            "gate": gate,
            "danger": danger,
            "dd": dd,
            "vol_ratio": vol_ratio,
            "hpa_tone": hpa_tone,
            "breached": float(self._breached),
            "reopen_phase": self._reopen_phase,
        }
