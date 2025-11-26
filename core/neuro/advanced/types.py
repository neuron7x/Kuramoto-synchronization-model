"""Shared domain types for the advanced neuro module."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional


class TradeOutcome(str, Enum):
    """Outcome of a trade execution."""

    WIN = "win"
    LOSS = "loss"
    NEUTRAL = "neutral"


@dataclass(slots=True)
class TradeResult:
    """Result of a trade used for reinforcement learning."""

    asset: str
    strategy: str
    outcome: TradeOutcome
    pnl_percentage: float
    signal_strength: float
    strategy_complexity: float = 1.0
    loss_magnitude: float = 0.0
    expected_reward: Optional[float] = None
    profit_magnitude: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset": self.asset,
            "strategy": self.strategy,
            "outcome": self.outcome.value,
            "pnl_percentage": self.pnl_percentage,
            "signal_strength": self.signal_strength,
            "strategy_complexity": self.strategy_complexity,
            "loss_magnitude": self.loss_magnitude,
            "expected_reward": self.expected_reward,
            "profit_magnitude": self.profit_magnitude,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass(slots=True)
class MarketContext:
    """Minimal market context required by the control networks."""

    volatility: float
    trend_strength: float
    liquidity: float = 1.0
    regime: str = "normal"
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "volatility": self.volatility,
            "trend_strength": self.trend_strength,
            "liquidity": self.liquidity,
            "regime": self.regime,
            "timestamp": self.timestamp.isoformat(),
        }
