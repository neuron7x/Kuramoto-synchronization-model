"""Domain models supporting cross-exchange arbitrage orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, getcontext
from typing import Mapping

getcontext().prec = 28  # ensure high precision for monetary arithmetic


def _ensure_utc(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


@dataclass(slots=True, frozen=True)
class Quote:
    """Top-of-book quote from an exchange for a given symbol."""

    exchange_id: str
    symbol: str
    bid: Decimal
    ask: Decimal
    bid_size: Decimal
    ask_size: Decimal
    timestamp: datetime
    received_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not self.exchange_id:
            raise ValueError("exchange_id must be provided")
        if not self.symbol:
            raise ValueError("symbol must be provided")
        if self.bid <= Decimal("0"):
            raise ValueError("bid must be positive")
        if self.ask <= Decimal("0"):
            raise ValueError("ask must be positive")
        if self.bid_size <= Decimal("0"):
            raise ValueError("bid_size must be positive")
        if self.ask_size <= Decimal("0"):
            raise ValueError("ask_size must be positive")
        if self.ask < self.bid:
            raise ValueError("ask must be greater than or equal to bid")
        object.__setattr__(self, "timestamp", _ensure_utc(self.timestamp))
        object.__setattr__(self, "received_at", _ensure_utc(self.received_at))

    @property
    def mid_price(self) -> Decimal:
        return (self.ask + self.bid) / Decimal("2")

    @property
    def spread(self) -> Decimal:
        return self.ask - self.bid

    @property
    def age(self) -> timedelta:
        return self.received_at - self.timestamp


@dataclass(slots=True)
class ExchangePriceState:
    """Tracks the latest quote and exchange-level diagnostics."""

    exchange_id: str
    latency_window: int = 256
    max_clock_skew: timedelta = timedelta(milliseconds=250)
    last_quote: Quote | None = None
    last_latency: timedelta | None = None
    clock_offset: timedelta | None = None
    last_sequence: int = 0
    _latency_samples: list[timedelta] = field(default_factory=list, init=False)

    def record_quote(self, quote: Quote) -> None:
        now = quote.received_at
        latency = now - quote.timestamp
        self.last_quote = quote
        self.last_latency = latency
        self.last_sequence += 1
        if len(self._latency_samples) >= self.latency_window:
            self._latency_samples.pop(0)
        self._latency_samples.append(latency)

    @property
    def latency_samples(self) -> tuple[timedelta, ...]:
        return tuple(self._latency_samples)

    def compute_average_latency(self) -> timedelta | None:
        if not self._latency_samples:
            return None
        total = sum((sample for sample in self._latency_samples), timedelta())
        return total / len(self._latency_samples)


@dataclass(slots=True, frozen=True)
class LiquiditySnapshot:
    """Snapshot of liquidity available on an exchange for a symbol."""

    exchange_id: str
    symbol: str
    base_available: Decimal
    quote_available: Decimal
    bid_liquidity: Decimal
    ask_liquidity: Decimal
    timestamp: datetime


@dataclass(slots=True, frozen=True)
class CapitalTransferPlan:
    """Detailed plan describing a movement of capital between venues."""

    transfer_id: str
    legs: Mapping[tuple[str, str], Decimal]
    initiated_at: datetime
    metadata: Mapping[str, str] | None = None


@dataclass(slots=True, frozen=True)
class TransferResult:
    """Outcome of a capital transfer orchestration."""

    transfer_id: str
    committed: bool
    committed_at: datetime
    reason: str | None = None
