"""Deterministic price generation for the sandbox market."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Iterable

from ..models import PricePoint, PriceSeries


class MockMarketDataGenerator:
    """Produces repeatable synthetic price series for demonstration purposes."""

    def __init__(self, *, window: int, base_price: float) -> None:
        self._window = window
        self._base_price = base_price

    def generate(self, symbol: str) -> PriceSeries:
        now = datetime.now(timezone.utc)
        points: list[PricePoint] = []
        for index in range(self._window):
            timestamp = now - timedelta(minutes=self._window - index)
            price = self._base_price + self._oscillation(symbol, index)
            points.append(
                PricePoint(symbol=symbol, timestamp=timestamp, price=round(price, 2))
            )
        return PriceSeries(symbol=symbol, points=points)

    def _oscillation(self, symbol: str, index: int) -> float:
        symbol_bias = sum(ord(char) for char in symbol) % 10
        seasonal = math.sin(index / 3.0) * 1.5
        trend = index * 0.05
        return seasonal + trend + symbol_bias


class MarketDataset:
    """Collection of generated markets keyed by symbol."""

    def __init__(self, symbols: Iterable[str], window: int) -> None:
        self._symbols = tuple(symbols)
        self._window = window

    def build(self) -> dict[str, PriceSeries]:
        data = {}
        for symbol in self._symbols:
            base_price = 50.0 + (sum(ord(char) for char in symbol) % 50)
            generator = MockMarketDataGenerator(
                window=self._window, base_price=base_price
            )
            data[symbol] = generator.generate(symbol)
        return data
