"""TradePulse-QLW: Quantum-like Wave Model for Liquidity and Execution Risk.

This module implements a physics-based liquidity and order execution risk model
that interprets market dynamics as a damped stochastic wave with absorbing boundaries.
"""

from .config import QLWConfig
from .engine import QLWEngine
from .types import EngineResult

__version__ = "1.1.0"

__all__ = [
    "QLWConfig",
    "QLWEngine",
    "EngineResult",
]
