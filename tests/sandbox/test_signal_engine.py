from datetime import datetime, timezone

import pytest

from sandbox.models import PricePoint, PriceSeries, SignalDirection
from sandbox.signal.engine import SignalEngine


class StubMarketProvider:
    async def fetch(self, symbol: str, window: int) -> PriceSeries:
        base = 100.0
        points = [
            PricePoint(
                symbol=symbol, timestamp=datetime.now(timezone.utc), price=base + offset
            )
            for offset in (-2, -1, 0, 1, 2)
        ]
        return PriceSeries(symbol=symbol, points=points)


@pytest.mark.asyncio
async def test_signal_engine_detects_overbought_conditions() -> None:
    engine = SignalEngine(provider=StubMarketProvider(), sensitivity=0.005, window=5)
    signal = await engine.generate("btcusd")
    assert signal.direction is SignalDirection.SELL
    assert signal.rationale == "price_above_moving_average"
