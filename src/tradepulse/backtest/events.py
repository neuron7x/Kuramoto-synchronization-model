"""Event abstractions used by the event-driven backtest engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(slots=True)
class Event:
    """Base class for all events exchanged through the event queue."""

    type: str
    step: int


@dataclass(slots=True)
class MarketEvent(Event):
    """Market data update for a single instrument."""

    symbol: str
    price: float
    timestamp: Optional[datetime] = None

    def __init__(
        self, symbol: str, price: float, step: int, timestamp: Optional[datetime] = None
    ) -> None:
        Event.__init__(self, type="MARKET", step=step)
        self.symbol = symbol
        self.price = float(price)
        self.timestamp = timestamp


@dataclass(slots=True)
class SignalEvent(Event):
    """Trading signal produced by a strategy."""

    symbol: str
    target_position: float

    def __init__(self, symbol: str, target_position: float, step: int) -> None:
        Event.__init__(self, type="SIGNAL", step=step)
        self.symbol = symbol
        self.target_position = float(target_position)


@dataclass(slots=True)
class OrderEvent(Event):
    """Order submitted to the execution handler."""

    symbol: str
    quantity: float
    order_type: str = "market"

    def __init__(
        self, symbol: str, quantity: float, step: int, order_type: str = "market"
    ) -> None:
        Event.__init__(self, type="ORDER", step=step)
        self.symbol = symbol
        self.quantity = float(quantity)
        self.order_type = order_type


@dataclass(slots=True)
class FillEvent(Event):
    """Fill confirmation returned by the execution handler."""

    symbol: str
    quantity: float
    price: float
    fee: float
    slippage: float
    spread_cost: float = 0.0
    financing_cost: float = 0.0

    def __init__(
        self,
        symbol: str,
        quantity: float,
        price: float,
        fee: float,
        slippage: float,
        step: int,
        *,
        spread_cost: float = 0.0,
        financing_cost: float = 0.0,
    ) -> None:
        Event.__init__(self, type="FILL", step=step)
        self.symbol = symbol
        self.quantity = float(quantity)
        self.price = float(price)
        self.fee = float(fee)
        self.slippage = float(slippage)
        self.spread_cost = float(spread_cost)
        self.financing_cost = float(financing_cost)
