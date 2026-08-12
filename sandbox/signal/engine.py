# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Signal generation logic for the sandbox."""

from __future__ import annotations

from datetime import datetime, timezone
from statistics import mean

from ..models import PricePoint, PriceSeries, SignalDirection, TradingSignal


class MarketDataProviderProtocol:
    async def fetch(
        self, symbol: str, window: int
    ) -> PriceSeries:  # pragma: no cover - protocol definition
        raise NotImplementedError


class SignalEngine:
    def __init__(
        self, provider: MarketDataProviderProtocol, *, sensitivity: float, window: int
    ) -> None:
        self._provider = provider
        self._sensitivity = sensitivity
        self._window = window

    async def generate(self, symbol: str) -> TradingSignal:
        series = await self._provider.fetch(symbol, self._window)
        latest: PricePoint = series.latest
        average_price = mean(point.price for point in series.points)
        delta = (latest.price - average_price) / average_price
        if delta >= self._sensitivity:
            direction = SignalDirection.SELL
            rationale = "price_above_moving_average"
        elif delta <= -self._sensitivity:
            direction = SignalDirection.BUY
            rationale = "price_below_moving_average"
        else:
            direction = SignalDirection.HOLD
            rationale = "price_near_moving_average"
        strength = abs(delta)
        return TradingSignal(
            symbol=symbol.lower(),
            generated_at=datetime.now(timezone.utc),
            direction=direction,
            strength=round(strength, 4),
            reference_price=latest.price,
            rationale=rationale,
        )
