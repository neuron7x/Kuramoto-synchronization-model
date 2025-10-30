# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Nightly stress tests for DST, holidays, and infrastructure outages."""
from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from backtest.market_calendar import MarketCalendar, SessionHours
from core.data.adapters.base import IngestionAdapter, RetryConfig
from core.data.connectors.market import DEFAULT_SCHEMA_ROOT, BaseMarketDataConnector
from core.data.models import DataKind, InstrumentType, MarketMetadata
from core.data.models import PriceTick as Ticker
from core.messaging.schema_registry import EventSchemaRegistry

pytestmark = [pytest.mark.nightly, pytest.mark.slow]


def _nyse_calendar() -> MarketCalendar:
    hours = {idx: SessionHours(time(9, 30), time(16, 0)) for idx in range(5)}
    holidays = {
        date(2024, 1, 1),
        date(2024, 7, 4),
        date(2024, 11, 28),
        date(2024, 12, 25),
    }
    special_sessions = {
        date(2024, 11, 29): SessionHours(
            time(9, 30), time(13, 0)
        ),  # Thanksgiving Friday
        date(2024, 3, 15): SessionHours(
            time(9, 30), time(12, 0)
        ),  # Simulated outage early close
    }
    return MarketCalendar(
        "America/New_York",
        regular_hours=hours,
        holidays=holidays,
        special_sessions=special_sessions,
    )


def test_calendar_dst_and_holiday_window() -> None:
    """Verify sessions across DST transitions and holiday closures."""

    calendar = _nyse_calendar()
    start = datetime(2024, 3, 7, 0, 0, tzinfo=ZoneInfo("UTC"))
    end = datetime(2024, 3, 18, 23, 59, tzinfo=ZoneInfo("UTC"))
    sessions = calendar.sessions_between(start, end)

    # March 7-8 (EST), weekend skip, March 11-15 (EDT with outage early close on 15th)
    assert len(sessions) == 8
    open_hours = [session[0].astimezone(ZoneInfo("UTC")).hour for session in sessions]
    assert open_hours == [14, 14, 13, 13, 13, 13, 13, 13]

    outage_session = sessions[-2]
    assert outage_session[1].astimezone(ZoneInfo("UTC")).hour == 16


def test_calendar_handles_consecutive_holiday_sequence() -> None:
    """Ensure holiday closures followed by special sessions are handled."""

    calendar = _nyse_calendar()
    thanksgiving_week = calendar.sessions_between(
        datetime(2024, 11, 25, 0, 0, tzinfo=ZoneInfo("UTC")),
        datetime(2024, 12, 2, 0, 0, tzinfo=ZoneInfo("UTC")),
    )
    assert len(thanksgiving_week) == 4
    close_hours = [
        session[1].astimezone(ZoneInfo("UTC")).hour for session in thanksgiving_week
    ]
    assert close_hours == [21, 21, 21, 18]

    friday_close = thanksgiving_week[-1][1] + timedelta(minutes=10)
    next_open = calendar.next_open(friday_close)
    assert next_open.date() == date(2024, 12, 2)


class _FlakyAdapter(IngestionAdapter):
    """Adapter that simulates network outages before recovering."""

    def __init__(self, *, failures: int, ticks: list[Ticker]) -> None:
        super().__init__(
            retry=RetryConfig(attempts=5, multiplier=0.01, max_backoff=0.05, jitter=0.0)
        )
        self._failures = failures
        self._ticks = ticks
        self.fetch_calls = 0
        self.stream_attempts = 0

    async def fetch(self, **kwargs: object):
        async def _operation():
            self.fetch_calls += 1
            if self._failures > 0:
                self._failures -= 1
                raise ConnectionError("snapshot outage")
            return list(self._ticks)

        return await self._run_with_policy(_operation)

    async def stream(self, **kwargs: object):
        if self.stream_attempts < 1:
            self.stream_attempts += 1
            raise ConnectionError("stream outage")
        for tick in self._ticks:
            yield tick


async def _collect_ticks(
    connector: BaseMarketDataConnector, expected: int
) -> list[dict[str, object]]:
    events = []
    async for event in connector.stream_ticks():
        events.append(event.model_dump())  # type: ignore[union-attr]
        if len(events) >= expected:
            break
    return events


@pytest.mark.asyncio
async def test_market_connector_recovers_from_outages() -> None:
    """Market connector should retry through outages and emit validated events."""

    metadata = MarketMetadata(
        symbol="AAPL",
        venue="NASDAQ",
        instrument_type=InstrumentType.SPOT,
    )
    base_ts = datetime(2024, 3, 11, tzinfo=timezone.utc)
    ticks = [
        Ticker(
            metadata=metadata,
            timestamp=base_ts + timedelta(minutes=i),
            kind=DataKind.TICK,
            price=Decimal("150.0"),
            volume=Decimal("10"),
        )
        for i in range(3)
    ]

    adapter = _FlakyAdapter(failures=2, ticks=ticks)
    registry = EventSchemaRegistry.from_directory(DEFAULT_SCHEMA_ROOT)
    connector = BaseMarketDataConnector(adapter, schema_registry=registry)

    snapshot = await adapter.fetch()
    assert len(snapshot) == 3
    assert adapter.fetch_calls >= 3

    events = await asyncio.wait_for(_collect_ticks(connector, expected=3), timeout=5)
    assert len(events) == 3
    assert adapter.stream_attempts == 1
    await connector.aclose()
