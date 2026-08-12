# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from datetime import datetime, timezone

import pytest

from sandbox.models import PricePoint, PriceSeries, SignalDirection
from sandbox.signal.engine import SignalEngine


class StubMarketProvider:
    async def fetch(self, symbol: str, window: int) -> PriceSeries:
        base = 100.0
        points = [
            PricePoint(symbol=symbol, timestamp=datetime.now(timezone.utc), price=base + offset)
            for offset in (-2, -1, 0, 1, 2)
        ]
        return PriceSeries(symbol=symbol, points=points)


class StableMarketProvider:
    """Provider that returns prices at the average (no directional signal)."""

    async def fetch(self, symbol: str, window: int) -> PriceSeries:
        base = 100.0
        points = [
            PricePoint(symbol=symbol, timestamp=datetime.now(timezone.utc), price=base)
            for _ in range(5)
        ]
        return PriceSeries(symbol=symbol, points=points)


class OversoldMarketProvider:
    """Provider that returns declining prices (buy signal)."""

    async def fetch(self, symbol: str, window: int) -> PriceSeries:
        points = [
            PricePoint(
                symbol=symbol,
                timestamp=datetime.now(timezone.utc),
                price=105.0 - i * 2,
            )
            for i in range(5)
        ]
        return PriceSeries(symbol=symbol, points=points)


@pytest.mark.asyncio
async def test_signal_engine_detects_overbought_conditions() -> None:
    engine = SignalEngine(provider=StubMarketProvider(), sensitivity=0.005, window=5)
    signal = await engine.generate("btcusd")
    assert signal.direction is SignalDirection.SELL
    assert signal.rationale == "price_above_moving_average"


@pytest.mark.asyncio
async def test_signal_engine_detects_hold_conditions() -> None:
    """Test that stable prices generate HOLD signal."""
    engine = SignalEngine(provider=StableMarketProvider(), sensitivity=0.005, window=5)
    signal = await engine.generate("ethusd")
    assert signal.direction is SignalDirection.HOLD
    assert signal.rationale == "price_near_moving_average"


@pytest.mark.asyncio
async def test_signal_engine_detects_oversold_conditions() -> None:
    """Test that declining prices generate BUY signal."""
    engine = SignalEngine(provider=OversoldMarketProvider(), sensitivity=0.005, window=5)
    signal = await engine.generate("solusd")
    assert signal.direction is SignalDirection.BUY
    assert signal.rationale == "price_below_moving_average"


@pytest.mark.asyncio
async def test_signal_engine_normalizes_symbol() -> None:
    """Test that the signal symbol is normalized to lowercase."""
    engine = SignalEngine(provider=StubMarketProvider(), sensitivity=0.005, window=5)
    signal = await engine.generate("BTCUSD")
    assert signal.symbol == "btcusd"


@pytest.mark.asyncio
async def test_signal_engine_reports_strength() -> None:
    """Test that signal strength is calculated."""
    engine = SignalEngine(provider=StubMarketProvider(), sensitivity=0.005, window=5)
    signal = await engine.generate("btcusd")
    assert signal.strength >= 0.0
    assert signal.strength <= 1.0
