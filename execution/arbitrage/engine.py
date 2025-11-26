"""Cross-exchange arbitrage coordination engine."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import AsyncIterator, Awaitable, Callable, Dict, Mapping, Protocol, Sequence

from .capital import AtomicCapitalMover, CapitalTransferPlan
from .liquidity import LiquidityLedger
from .metrics import LatencyTracker
from .models import ExchangePriceState, Quote

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class ArbitrageOpportunity:
    """Represents a synchronised cross-venue arbitrage candidate."""

    symbol: str
    buy_exchange: str
    sell_exchange: str
    buy_price: Decimal
    sell_price: Decimal
    base_size: Decimal
    notional: Decimal
    expected_profit: Decimal
    spread: Decimal
    buy_timestamp: datetime
    sell_timestamp: datetime
    generated_at: datetime
    latency_snapshot: Mapping[str, timedelta]


class QuoteStream(Protocol):
    """Protocol implemented by exchange quote sources."""

    async def stream_quotes(self, symbols: Sequence[str]) -> AsyncIterator[Quote]: ...


class CrossExchangeArbitrageEngine:
    """Consumes multi-venue quotes and surfaces actionable opportunities."""

    def __init__(
        self,
        quote_providers: Mapping[str, QuoteStream],
        liquidity_ledger: LiquidityLedger,
        capital_mover: AtomicCapitalMover,
        *,
        pair_config: Mapping[str, tuple[str, str]],
        fee_schedule: Mapping[str, Decimal] | None = None,
        min_edge: Decimal = Decimal("0.0005"),
        min_profit: Decimal = Decimal("0"),
        staleness_tolerance: timedelta = timedelta(seconds=2),
        max_clock_skew: timedelta = timedelta(milliseconds=250),
        queue_maxsize: int = 4096,
    ) -> None:
        if not quote_providers:
            raise ValueError("At least one quote provider is required")
        if staleness_tolerance <= timedelta(0):
            raise ValueError("staleness_tolerance must be positive")
        if max_clock_skew <= timedelta(0):
            raise ValueError("max_clock_skew must be positive")
        self._providers: Dict[str, QuoteStream] = dict(quote_providers)
        self._ledger = liquidity_ledger
        self._capital_mover = capital_mover
        self._pair_config = dict(pair_config)
        self._fee_schedule = defaultdict(lambda: Decimal("0"))
        if fee_schedule:
            self._fee_schedule.update(fee_schedule)
        self._min_edge = min_edge
        self._min_profit = min_profit
        self._staleness = staleness_tolerance
        self._max_clock_skew = max_clock_skew
        self._queue: asyncio.Queue[Quote | None] = asyncio.Queue(maxsize=queue_maxsize)
        self._states: Dict[str, Dict[str, ExchangePriceState]] = defaultdict(dict)
        self._latencies: Dict[str, LatencyTracker] = defaultdict(LatencyTracker)
        self._running = asyncio.Event()
        self._stop_requested = asyncio.Event()

    async def run(
        self,
        symbols: Sequence[str],
        *,
        opportunity_callback: Callable[[ArbitrageOpportunity], Awaitable[None]],
    ) -> None:
        if not symbols:
            raise ValueError("symbols must not be empty")
        for symbol in symbols:
            if symbol not in self._pair_config:
                raise ValueError(
                    f"pair_config missing base/quote definition for {symbol}"
                )
        if self._running.is_set():
            raise RuntimeError("Engine already running")
        self._running.set()
        self._stop_requested.clear()
        async with asyncio.TaskGroup() as task_group:
            for exchange_id, provider in self._providers.items():
                task_group.create_task(
                    self._consume_quotes(exchange_id, provider, symbols)
                )
            task_group.create_task(self._process_quotes(symbols, opportunity_callback))
        self._running.clear()

    async def stop(self) -> None:
        self._stop_requested.set()
        await self._queue.join()

    async def _consume_quotes(
        self,
        exchange_id: str,
        provider: QuoteStream,
        symbols: Sequence[str],
    ) -> None:
        try:
            async for quote in provider.stream_quotes(symbols):
                if self._stop_requested.is_set():
                    break
                if quote.exchange_id != exchange_id:
                    raise ValueError(
                        f"Mismatched exchange_id: expected {exchange_id}, got {quote.exchange_id}"
                    )
                await self._queue.put(quote)
        finally:
            await self._queue.put(None)

    async def _process_quotes(
        self,
        symbols: Sequence[str],
        callback: Callable[[ArbitrageOpportunity], Awaitable[None]],
    ) -> None:
        sentinel_count = 0
        required_sentinels = len(self._providers)
        while sentinel_count < required_sentinels:
            quote = await self._queue.get()
            try:
                if quote is None:
                    sentinel_count += 1
                    continue
                if quote.symbol not in symbols:
                    continue
                opportunity = self._handle_quote(quote)
                if opportunity is not None:
                    await callback(opportunity)
            finally:
                self._queue.task_done()
        while not self._queue.empty():
            self._queue.get_nowait()
            self._queue.task_done()

    def _handle_quote(self, quote: Quote) -> ArbitrageOpportunity | None:
        exchange_state = self._states[quote.symbol].get(quote.exchange_id)
        if exchange_state is None:
            exchange_state = ExchangePriceState(exchange_id=quote.exchange_id)
            self._states[quote.symbol][quote.exchange_id] = exchange_state
        exchange_state.record_quote(quote)
        latency = quote.received_at - quote.timestamp
        if latency < timedelta(0):
            latency = timedelta(0)
        self._latencies[quote.exchange_id].record(latency)
        return self._find_opportunity(quote.symbol)

    def _find_opportunity(self, symbol: str) -> ArbitrageOpportunity | None:
        states = self._states.get(symbol)
        if not states:
            return None
        best_bid_state: ExchangePriceState | None = None
        best_ask_state: ExchangePriceState | None = None
        now = datetime.now(timezone.utc)
        for state in states.values():
            quote = state.last_quote
            if quote is None:
                continue
            if now - quote.received_at > self._staleness:
                continue
            if state.last_latency and state.last_latency > self._staleness:
                continue
            if best_bid_state is None or quote.bid > best_bid_state.last_quote.bid:  # type: ignore[union-attr]
                best_bid_state = state
            if best_ask_state is None or quote.ask < best_ask_state.last_quote.ask:  # type: ignore[union-attr]
                best_ask_state = state
        if not best_bid_state or not best_ask_state:
            return None
        if best_bid_state.exchange_id == best_ask_state.exchange_id:
            return None
        bid_quote = best_bid_state.last_quote
        ask_quote = best_ask_state.last_quote
        if bid_quote is None or ask_quote is None:
            _LOGGER.error(
                "Exchange state missing quote despite selection",
                extra={
                    "symbol": symbol,
                    "bid_exchange": best_bid_state.exchange_id,
                    "ask_exchange": best_ask_state.exchange_id,
                },
            )
            return None
        if bid_quote.bid <= ask_quote.ask:
            return None
        if abs(bid_quote.timestamp - ask_quote.timestamp) > self._max_clock_skew:
            return None
        base_asset, _ = self._pair_config[symbol]
        buy_liquidity = self._ledger.get_snapshot(best_ask_state.exchange_id, symbol)
        sell_liquidity = self._ledger.get_snapshot(best_bid_state.exchange_id, symbol)
        base_size = min(ask_quote.ask_size, bid_quote.bid_size)
        if buy_liquidity is not None:
            quote_balance = buy_liquidity.quote_available
            if quote_balance <= Decimal("0"):
                return None
            base_size = min(base_size, quote_balance / ask_quote.ask)
        if sell_liquidity is not None:
            base_balance = sell_liquidity.base_available
            if base_balance <= Decimal("0"):
                return None
            base_size = min(base_size, base_balance)
        if base_size <= Decimal("0"):
            return None
        notional = base_size * ask_quote.ask
        fee_buy = self._fee_schedule[best_ask_state.exchange_id]
        fee_sell = self._fee_schedule[best_bid_state.exchange_id]
        fees = notional * fee_buy + (base_size * bid_quote.bid) * fee_sell
        gross_profit = (bid_quote.bid - ask_quote.ask) * base_size
        net_profit = gross_profit - fees
        if net_profit <= Decimal("0"):
            return None
        if notional > Decimal("0"):
            edge = net_profit / notional
            if edge < self._min_edge:
                return None
        if net_profit < self._min_profit:
            return None
        latency_snapshot = {
            exchange_id: tracker.percentile(50)
            for exchange_id, tracker in self._latencies.items()
        }
        return ArbitrageOpportunity(
            symbol=symbol,
            buy_exchange=best_ask_state.exchange_id,
            sell_exchange=best_bid_state.exchange_id,
            buy_price=ask_quote.ask,
            sell_price=bid_quote.bid,
            base_size=base_size,
            notional=notional,
            expected_profit=net_profit,
            spread=bid_quote.bid - ask_quote.ask,
            buy_timestamp=ask_quote.timestamp,
            sell_timestamp=bid_quote.timestamp,
            generated_at=datetime.now(timezone.utc),
            latency_snapshot=latency_snapshot,
        )

    async def execute_opportunity(self, opportunity: ArbitrageOpportunity) -> bool:
        plan = CapitalTransferPlan(
            transfer_id=f"arb-{opportunity.symbol}-{int(opportunity.generated_at.timestamp())}",
            legs={
                (
                    opportunity.buy_exchange,
                    self._pair_config[opportunity.symbol][1],
                ): opportunity.notional,
                (
                    opportunity.sell_exchange,
                    self._pair_config[opportunity.symbol][0],
                ): opportunity.base_size,
            },
            initiated_at=datetime.now(timezone.utc),
            metadata={
                "symbol": opportunity.symbol,
                "buy_price": str(opportunity.buy_price),
                "sell_price": str(opportunity.sell_price),
            },
        )
        result = await self._capital_mover.execute(plan)
        return result.committed
