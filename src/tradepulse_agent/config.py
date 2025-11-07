"""Configuration dataclasses for TradePulse agent integrations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.data.models import InstrumentType


@dataclass(slots=True)
class AgentDataFeedConfig:
    """Describe the historical data feed used to drive the agent environment."""

    path: Path
    symbol: str
    venue: str
    instrument_type: InstrumentType = InstrumentType.SPOT
    timestamp_field: str = "ts"
    timestamp_unit: str | None = "s"
    price_field: str = "close"
    volume_field: str = "volume"
    required_fields: tuple[str, ...] = ("open", "high", "low", "close", "volume")

    def resolve_path(self) -> Path:
        """Return the canonical filesystem path to the data feed."""

        return self.path.expanduser().resolve()


@dataclass(slots=True)
class AgentEnvironmentConfig:
    """Runtime parameters controlling the reinforcement-learning environment."""

    lookback_window: int = 64
    initial_cash: float = 100_000.0
    max_position: float = 1.0
    position_increment: float = 0.25
    trading_fee_bps: float = 1.0
    reward_scaling: float = 1.0

    def __post_init__(self) -> None:
        if self.lookback_window < 2:
            raise ValueError("lookback_window must be at least 2")
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if self.max_position <= 0:
            raise ValueError("max_position must be positive")
        if self.position_increment <= 0:
            raise ValueError("position_increment must be positive")
        if self.position_increment > self.max_position:
            self.position_increment = self.max_position
        if self.trading_fee_bps < 0:
            raise ValueError("trading_fee_bps cannot be negative")
        if self.reward_scaling <= 0:
            raise ValueError("reward_scaling must be positive")


@dataclass(slots=True)
class AgentExecutionConfig:
    """Parameters used when translating agent actions into TradePulse orders."""

    min_confidence: float = 0.55
    confidence_scale: float = 1.0
    execute_hold: bool = False
    position_increment: float = 0.25
    max_position: float = 1.0
    flatten_threshold: float = 1e-6

    def __post_init__(self) -> None:
        if not 0.0 <= self.min_confidence <= 1.0:
            raise ValueError("min_confidence must be within [0, 1]")
        if self.confidence_scale <= 0:
            raise ValueError("confidence_scale must be positive")
        if self.position_increment <= 0:
            raise ValueError("position_increment must be positive")
        if self.max_position <= 0:
            raise ValueError("max_position must be positive")
        if self.position_increment > self.max_position:
            self.position_increment = self.max_position
        if self.flatten_threshold < 0:
            raise ValueError("flatten_threshold cannot be negative")
