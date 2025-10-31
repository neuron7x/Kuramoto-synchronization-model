"""Domain models shared across sandbox services."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, PositiveFloat, constr


class PricePoint(BaseModel):
    """Single price observation for a traded instrument."""

    symbol: constr(strip_whitespace=True, to_lower=True, min_length=1)
    timestamp: datetime
    price: PositiveFloat


class PriceSeries(BaseModel):
    """Time-ordered collection of price points."""

    symbol: str
    points: list[PricePoint]

    @property
    def latest(self) -> PricePoint:
        return self.points[-1]

    @property
    def midpoint(self) -> float:
        return sum(point.price for point in self.points) / len(self.points)


class SignalDirection(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class TradingSignal(BaseModel):
    """Directional recommendation produced by the signal core."""

    symbol: str
    generated_at: datetime
    direction: SignalDirection
    strength: float = Field(ge=0.0)
    reference_price: PositiveFloat
    rationale: str


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderTicket(BaseModel):
    """Incoming order request flowing through the sandbox."""

    symbol: str
    side: OrderSide
    quantity: PositiveFloat


class RiskDecision(BaseModel):
    """Outcome of the risk layer evaluation."""

    approved: bool
    reason: str
    limit_consumption: float = Field(ge=0.0, le=1.0)


class ExecutionFill(BaseModel):
    """Single paper execution fill."""

    symbol: str
    side: OrderSide
    quantity: PositiveFloat
    price: PositiveFloat
    executed_at: datetime


class ExecutionReport(BaseModel):
    """Result returned by the execution service."""

    accepted: bool
    message: str
    signal: TradingSignal | None
    risk: RiskDecision | None
    fills: list[ExecutionFill] = Field(default_factory=list)


class KillSwitchState(BaseModel):
    """Represents the sandbox kill-switch state."""

    engaged: bool
    reason: str | None = None
    engaged_at: datetime | None = None


class AuditEvent(BaseModel):
    """Structured event submitted to the control API audit feed."""

    source: str
    category: str
    message: str
    created_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)
