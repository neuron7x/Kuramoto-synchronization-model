"""Shared dataclasses exchanged between TradePulse microservices."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from core.data.models import InstrumentType
from domain import Signal


@dataclass(slots=True)
class MarketDataSource:
    """Declarative description of a market data CSV source."""

    path: Path
    symbol: str
    venue: str
    instrument_type: InstrumentType = InstrumentType.SPOT
    market: str | None = None


@dataclass(slots=True)
class StrategyRun:
    """Result of executing a strategy over ingested market data."""

    market_frame: pd.DataFrame
    feature_frame: pd.DataFrame
    signals: list[Signal]
    payloads: list[dict[str, object]]


StrategyCallable = Callable[[np.ndarray], np.ndarray]


@dataclass(slots=True)
class ExecutionRequest:
    """Parameters required to hand a signal over to execution."""

    signal: Signal
    venue: str
    quantity: float
    price: float | None = None
    order_type: str | None = None
    correlation_id: str | None = None
