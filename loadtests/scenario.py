"""Market scenarios and property-based order generation for load tests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import cycle
from pathlib import Path
from typing import Iterable, Iterator, Sequence

import numpy as np
from hypothesis import strategies as st
from hypothesis.strategies import SearchStrategy, composite


@dataclass(frozen=True)
class MarketBar:
    """Simplified OHLCV bar derived from recorded tick data."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    bid_volume: float
    ask_volume: float
    signed_volume: float

    def to_payload(self) -> dict[str, float | str]:
        return {
            "timestamp": self.timestamp.isoformat().replace("+00:00", "Z"),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "bidVolume": self.bid_volume,
            "askVolume": self.ask_volume,
            "signedVolume": self.signed_volume,
        }


@dataclass(frozen=True)
class OrderCandidate:
    """Order payload used for both HTTP and gRPC load testing."""

    symbol: str
    side: str
    quantity: float
    price: float
    order_type: str = "market"

    @property
    def notional(self) -> float:
        return abs(self.quantity * self.price)


class MarketScenario:
    """Replay recorded data and generate safe order payloads."""

    def __init__(
        self,
        *,
        symbol: str,
        bars: Sequence[MarketBar],
        var_95: float,
    ) -> None:
        if not bars:
            raise ValueError("At least one bar is required to build a scenario")
        self.symbol = symbol
        self._bars: list[MarketBar] = list(bars)
        self.var_95 = float(var_95)
        self._bar_cycle: cycle[MarketBar] = cycle(self._bars)
        self._windows = self._prepare_windows()
        closes = np.array([bar.close for bar in self._bars], dtype=float)
        median_price = float(np.median(closes))
        self.median_price = median_price
        risk_percentile = abs(self.var_95) if self.var_95 else 0.02
        # Cap notional exposure to 5% of median price when volatility is tiny.
        baseline_notional = median_price * max(risk_percentile * 20.0, 0.05)
        self.max_position_notional = baseline_notional
        self.max_position_size = max(self.max_position_notional / median_price, 0.001)
        self._order_strategy = self._build_order_strategy()

    @classmethod
    def from_recording(
        cls,
        path: Path,
        *,
        symbol: str = "BTC-USD",
        ticks_per_bar: int = 25,
    ) -> "MarketScenario":
        ticks = _load_ticks(path)
        bars = list(_ticks_to_bars(ticks, ticks_per_bar))
        if len(bars) < 4:
            raise ValueError("Recording does not contain enough ticks to derive bars")
        returns = np.diff([bar.close for bar in bars]) / np.array(
            [bar.close for bar in bars[:-1]]
        )
        var_95 = float(np.percentile(returns, 5)) if returns.size else -0.02
        return cls(symbol=symbol, bars=bars, var_95=var_95)

    def _prepare_windows(self) -> Iterator[list[MarketBar]]:
        window: list[MarketBar] = []
        for bar in self._bar_cycle:
            window.append(bar)
            if len(window) >= 48:
                yield list(window)
                window = window[12:]

    def next_window(self, size: int = 32) -> list[MarketBar]:
        for candidate in self._windows:
            if len(candidate) >= size:
                return candidate[-size:]
        # Fallback if generator exhausted unexpectedly.
        return list(self._bars)[-size:]

    def build_feature_payload(self, size: int = 32) -> dict[str, object]:
        bars = [bar.to_payload() for bar in self.next_window(size)]
        return {"symbol": self.symbol, "bars": bars}

    @property
    def bars(self) -> Sequence[MarketBar]:
        return tuple(self._bars)

    def clone(self) -> "MarketScenario":
        return MarketScenario(symbol=self.symbol, bars=self._bars, var_95=self.var_95)

    def sample_order(self) -> OrderCandidate:
        candidate = self._order_strategy.example()
        if candidate.notional > self.max_position_notional:
            # Hypothesis guarantees bounds, but guard against float drift.
            scaled_quantity = self.max_position_notional / max(candidate.price, 1e-6)
            return OrderCandidate(
                symbol=candidate.symbol,
                side=candidate.side,
                quantity=float(min(scaled_quantity, self.max_position_size)),
                price=candidate.price,
                order_type=candidate.order_type,
            )
        return candidate

    def ticker_series(self) -> Iterable[tuple[str, float, float, datetime]]:
        for bar in self._bars:
            yield (self.symbol, bar.close, bar.volume, bar.timestamp)

    def _build_order_strategy(self) -> SearchStrategy[OrderCandidate]:
        price_samples = [bar.close for bar in self._bars]
        min_qty = min(0.01, self.max_position_size)
        max_qty = max(self.max_position_size, 0.01)

        @composite
        def _strategy(draw) -> OrderCandidate:
            side = draw(st.sampled_from(["buy", "sell"]))
            price = float(draw(st.sampled_from(price_samples)))
            quantity = float(
                draw(
                    st.floats(
                        min_value=min_qty,
                        max_value=max_qty,
                        allow_nan=False,
                        allow_infinity=False,
                    )
                )
            )
            return OrderCandidate(
                symbol=self.symbol,
                side=side,
                quantity=quantity,
                price=price,
            )

        return _strategy()


def _load_ticks(path: Path) -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        payloads.append(_normalise_tick(raw_line))
    return payloads


def _normalise_tick(raw_line: str) -> dict[str, object]:
    data = json.loads(raw_line)
    exchange_ts = datetime.fromisoformat(data["exchange_ts"].replace("Z", "+00:00"))
    return {
        "exchange_ts": exchange_ts.astimezone(timezone.utc),
        "bid": float(data["bid"]),
        "ask": float(data["ask"]),
        "last": float(data["last"]),
        "volume": float(data.get("volume", 0.0)),
    }


def _ticks_to_bars(
    ticks: Sequence[dict[str, object]],
    ticks_per_bar: int,
) -> Iterator[MarketBar]:
    for index in range(0, len(ticks), ticks_per_bar):
        chunk = ticks[index : index + ticks_per_bar]
        if not chunk:
            continue
        opens = chunk[0]["last"]
        closes = chunk[-1]["last"]
        high = max(max(entry["ask"], entry["last"]) for entry in chunk)
        low = min(min(entry["bid"], entry["last"]) for entry in chunk)
        volume = sum(entry["volume"] for entry in chunk)
        signed_volume = volume if closes >= opens else -volume
        timestamp = chunk[-1]["exchange_ts"]
        bid_volume = volume * 0.55
        ask_volume = volume * 0.45
        yield MarketBar(
            timestamp=timestamp,
            open=opens,
            high=high,
            low=low,
            close=closes,
            volume=volume,
            bid_volume=bid_volume,
            ask_volume=ask_volume,
            signed_volume=signed_volume,
        )


__all__ = [
    "MarketBar",
    "MarketScenario",
    "OrderCandidate",
]
