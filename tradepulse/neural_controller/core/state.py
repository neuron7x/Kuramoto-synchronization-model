from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EMHState:
    H: float = 0.5
    M: float = 0.8
    E: float = 0.1
    S: float = 0.0
    V: float = 0.0
    mode: str = "GREEN"


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else hi if x > hi else x
