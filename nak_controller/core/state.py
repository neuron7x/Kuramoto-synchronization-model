from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional, TypedDict, cast

Mode = Literal["GREEN", "AMBER", "RED"]

Diagnostics = TypedDict(
    "Diagnostics",
    {
        "err": float,
        "I": float,
        "r_tilde": float,
        "r_local": float,
        "DA": float,
        "NA": float,
        "5HT": float,
        "ACh": float,
        "mode": Mode,
        "risk_mult": float,
        "activity": float,
        "band_exp": float,
        "f_freq": float,
    },
    total=False,
)

def clip(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


@dataclass
class StrategyState:
    L: float = 0.0       # load [L_min, L_max]
    E: float = 0.5       # energy [0, E_max]
    EI: float = 0.5      # energy index [0,1]
    I: float = 0.0       # PI integral [-I_max, I_max]
    suspended: bool = False
    health: float = 0.5  # normalized EI
    debt: float = 0.0    # energy debt (for recovery dynamics)
    last_risk: Optional[float] = None
    last: Diagnostics = field(default_factory=lambda: cast(Diagnostics, {}))


__all__ = ["StrategyState", "clip", "Diagnostics", "Mode"]
