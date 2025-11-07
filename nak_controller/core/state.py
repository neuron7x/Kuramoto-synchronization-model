"""State containers used by the NaK controller."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


def clip(value: float, lower: float, upper: float) -> float:
    """Clamp *value* to the inclusive range ``[lower, upper]``."""
    if value < lower:
        return lower
    if value > upper:
        return upper
    return value


@dataclass
class StrategyState:
    """Mutable per-strategy state tracked by :class:`NaKController`."""

    L: float = 0.0
    E: float = 0.5
    EI: float = 0.5
    integral: float = 0.0
    suspended: bool = False
    health: float = 0.5
    debt: float = 0.0
    last_risk: float = 1.0
    last: Dict[str, float | str] = field(default_factory=dict)


__all__ = ["StrategyState", "clip"]
