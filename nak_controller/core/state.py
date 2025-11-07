"""State containers used by the NaK controller pipeline.

This module centralises immutable diagnostic snapshots together with the
mutable per-strategy state tracked by the runtime controller. The goal is to
provide a strongly typed representation for debugging, testing and telemetry
without sacrificing runtime efficiency.

Copyright (c) 2024 TradePulse Technologies. All rights reserved.
Licensed under the TradePulse Proprietary License Agreement (TPLA).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

Mode = Literal["GREEN", "AMBER", "RED"]


def clip(x: float, lo: float, hi: float) -> float:
    """Clamp *x* to ``[lo, hi]`` without incurring branching surprises."""

    return lo if x < lo else hi if x > hi else x


@dataclass(frozen=True)
class DiagnosticsSnapshot:
    """Immutable record of controller diagnostics for a single step."""

    err: float
    integral: float
    r_tilde: float
    r_local: float
    dopamine: float
    noradrenaline: float
    serotonin: float
    acetylcholine: float
    mode: Mode
    risk_mult: float
    activity: float
    band_expansion: float
    frequency: float


@dataclass
class StrategyState:
    """Mutable runtime state attached to a strategy identifier."""

    L: float = 0.0       # load [L_min, L_max]
    E: float = 0.5       # energy [0, E_max]
    EI: float = 0.5      # energy index [0,1]
    pi_integral: float = 0.0  # PI integral [-I_max, I_max]
    suspended: bool = False
    health: float = 0.5  # normalized EI
    debt: float = 0.0    # energy debt (for recovery dynamics)
    last_risk: Optional[float] = None
    last: Optional[DiagnosticsSnapshot] = field(default=None)


__all__ = ["StrategyState", "clip", "DiagnosticsSnapshot", "Mode"]
