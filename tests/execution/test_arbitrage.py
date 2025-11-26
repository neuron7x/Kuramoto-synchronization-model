from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import AsyncIterator, Sequence

import pytest

from execution.arbitrage import (
    ArbitrageOpportunity,
    AtomicCapitalMover,
    CapitalTransferPlan,
    CrossExchangeArbitrageEngine,
    LatencyTracker,
    LiquidityLedger,
    Quote,
)
from execution.arbitrage.capital import SettlementGateway


class InMemoryGateway(SettlementGateway):
    def __init__(self) -> None:
        self.reservations: dict[str, tuple[str, str, Decimal]] = {}
        self.committed: set[str] = set()
        self.released: set[str] = set()
        self._counter = 0

    async def reserve(
        self, exchange_id: str, asset: str, amount: Decimal, transfer_id: str
    ) -> str:
        token = f"{exchange_id}:{asset}:{self._counter}"
        self._counter += 1
        self.reservations[token] = (exchange_id, asset, amount)
        return token

    async def commit(self, reservation_token: str) -> None:
        if reservation_token not in self.reservations:
            raise RuntimeError("unknown reservation")
        self.committed.add(reservation_token)

    async def release(self, reservation_token: str) -> None:
        if reservation_token not in self.reservations:
            return
        self.released.add(reservation_token)


class FailingCommitGateway(InMemoryGateway):
    async def commit(self, reservation_token: str) -> None:  # type: ignore[override]
        raise RuntimeError("commit failure")


class StaticQuoteProvider:
    def __init__(self, quotes: Sequence[Quote]) -> None:
        self._quotes = quotes

    async def stream_quotes(self, symbols: Sequence[str]) -> AsyncIterator[Quote]:
        for quote in self._quotes:
            yield quote
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_latency_tracker_percentiles() -> None:
    tracker = LatencyTracker(max_samples=5)
    tracker.extend([timedelta(milliseconds=value) for value in (5, 7, 9, 11, 13, 15)])
    assert tracker.percentile(50) == timedelta(milliseconds=11)
    assert tracker.percentile(90) > tracker.percentile(50)
    assert tracker.average() == timedelta(milliseconds=11)
    assert tracker.max_latency() == timedelta(milliseconds=15)
    assert tracker.min_latency() == timedelta(milliseconds=7)


@pytest.mark.asyncio
async def test_liquidity_ledger_reserve_commit_cycle() -> None:
    ledger = LiquidityLedger()
    ledger.set_balance(
        "EX1",
        "BTCUSDT",
        base_available=Decimal("10"),
        quote_available=Decimal("50000"),
    )
    reservation = ledger.reserve(
        "res-1",
        "EX1",
        "BTCUSDT",
        base_amount=Decimal("1"),
        quote_amount=Decimal("1000"),
    )
    assert reservation.base_amount == Decimal("1")
    assert reservation.quote_amount == Decimal("1000")
    ledger.commit(reservation.reservation_id)
    balances = ledger.available_balances()[("EX1", "BTCUSDT")]
    assert balances == (Decimal("9"), Decimal("49000"))


@pytest.mark.asyncio
async def test_atomic_capital_mover_success_and_failure() -> None:
    success_gateway = InMemoryGateway()
    failing_gateway = FailingCommitGateway()
    mover = AtomicCapitalMover({"EX1": success_gateway, "EX2": failing_gateway})
    plan = CapitalTransferPlan(
        transfer_id="test-transfer",
        legs={
            ("EX1", "USDT"): Decimal("1000"),
            ("EX2", "BTC"): Decimal("1"),
        },
        initiated_at=datetime.now(timezone.utc),
    )
    result = await mover.execute(plan)
    assert result.committed is False
    assert any(
        token in failing_gateway.released for token in failing_gateway.reservations
    )


@pytest.mark.asyncio
async def test_arbitrage_engine_detects_opportunity_and_executes() -> None:
    now = datetime.now(timezone.utc)
    quotes_a = [
        Quote(
            exchange_id="EX1",
            symbol="BTCUSDT",
            bid=Decimal("99"),
            ask=Decimal("100"),
            bid_size=Decimal("1"),
            ask_size=Decimal("1"),
            timestamp=now,
        )
    ]
    quotes_b = [
        Quote(
            exchange_id="EX2",
            symbol="BTCUSDT",
            bid=Decimal("102"),
            ask=Decimal("103"),
            bid_size=Decimal("1"),
            ask_size=Decimal("1"),
            timestamp=now,
        )
    ]
    provider_a = StaticQuoteProvider(quotes_a)
    provider_b = StaticQuoteProvider(quotes_b)
    ledger = LiquidityLedger()
    ledger.set_balance(
        "EX1", "BTCUSDT", base_available=Decimal("5"), quote_available=Decimal("500")
    )
    ledger.set_balance(
        "EX2", "BTCUSDT", base_available=Decimal("5"), quote_available=Decimal("500")
    )
    gateway = InMemoryGateway()
    mover = AtomicCapitalMover({"EX1": gateway, "EX2": gateway})
    engine = CrossExchangeArbitrageEngine(
        {"EX1": provider_a, "EX2": provider_b},
        ledger,
        mover,
        pair_config={"BTCUSDT": ("BTC", "USDT")},
        fee_schedule={"EX1": Decimal("0"), "EX2": Decimal("0")},
        staleness_tolerance=timedelta(seconds=5),
    )
    captured: list[ArbitrageOpportunity] = []

    async def capture(opportunity: ArbitrageOpportunity) -> None:
        captured.append(opportunity)

    await engine.run(["BTCUSDT"], opportunity_callback=capture)
    assert len(captured) == 1
    opportunity = captured[0]
    assert opportunity.buy_exchange == "EX1"
    assert opportunity.sell_exchange == "EX2"
    assert opportunity.expected_profit == Decimal("2")
    executed = await engine.execute_opportunity(opportunity)
    assert executed is True


@pytest.mark.asyncio
async def test_arbitrage_engine_ignores_stale_quotes() -> None:
    now = datetime.now(timezone.utc)
    stale = Quote(
        exchange_id="EX1",
        symbol="BTCUSDT",
        bid=Decimal("101"),
        ask=Decimal("102"),
        bid_size=Decimal("1"),
        ask_size=Decimal("1"),
        timestamp=now - timedelta(seconds=10),
        received_at=now,
    )
    fresh = Quote(
        exchange_id="EX2",
        symbol="BTCUSDT",
        bid=Decimal("103"),
        ask=Decimal("104"),
        bid_size=Decimal("1"),
        ask_size=Decimal("1"),
        timestamp=now,
    )
    provider_a = StaticQuoteProvider([stale])
    provider_b = StaticQuoteProvider([fresh])
    ledger = LiquidityLedger()
    ledger.set_balance(
        "EX1", "BTCUSDT", base_available=Decimal("5"), quote_available=Decimal("500")
    )
    ledger.set_balance(
        "EX2", "BTCUSDT", base_available=Decimal("5"), quote_available=Decimal("500")
    )
    gateway = InMemoryGateway()
    mover = AtomicCapitalMover({"EX1": gateway, "EX2": gateway})
    engine = CrossExchangeArbitrageEngine(
        {"EX1": provider_a, "EX2": provider_b},
        ledger,
        mover,
        pair_config={"BTCUSDT": ("BTC", "USDT")},
        staleness_tolerance=timedelta(seconds=2),
    )
    captured: list[ArbitrageOpportunity] = []

    async def capture(_: ArbitrageOpportunity) -> None:
        captured.append(_)

    await engine.run(["BTCUSDT"], opportunity_callback=capture)
    assert not captured
