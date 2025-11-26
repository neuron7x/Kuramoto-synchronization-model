from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

import pytest

from backtest.market_calendar import (
    MarketCalendar,
    MarketCalendarCoordinator,
    SessionHours,
    TradingWindow,
)


@pytest.fixture()
def coordinator() -> MarketCalendarCoordinator:
    ny_hours = {idx: SessionHours(time(9, 30), time(16, 0)) for idx in range(5)}
    ldn_hours = {idx: SessionHours(time(8, 0), time(16, 30)) for idx in range(5)}

    ny_calendar = MarketCalendar("America/New_York", regular_hours=ny_hours)
    ldn_calendar = MarketCalendar("Europe/London", regular_hours=ldn_hours)

    return MarketCalendarCoordinator({"NYSE": ny_calendar, "LSE": ldn_calendar})


def test_session_events_return_local_and_utc(
    coordinator: MarketCalendarCoordinator,
) -> None:
    start = datetime(2023, 7, 3, 11, 0, tzinfo=timezone.utc)
    end = datetime(2023, 7, 3, 20, 30, tzinfo=timezone.utc)

    events = coordinator.session_events(start, end)

    assert [(event.market, event.kind) for event in events] == [
        ("NYSE", "open"),
        ("LSE", "close"),
        ("NYSE", "close"),
    ]

    first = events[0]
    assert first.timestamp.tzinfo == timezone.utc
    assert first.local_timestamp.tzinfo == ZoneInfo("America/New_York")


def test_trading_windows_union_mode(coordinator: MarketCalendarCoordinator) -> None:
    start = datetime(2023, 7, 3, 11, 0, tzinfo=timezone.utc)
    end = datetime(2023, 7, 3, 21, 0, tzinfo=timezone.utc)

    windows = coordinator.trading_windows(start, end, mode="union")

    assert [window.markets for window in windows] == [
        frozenset({"LSE"}),
        frozenset({"LSE", "NYSE"}),
        frozenset({"NYSE"}),
    ]

    assert [window.start for window in windows] == [
        datetime(2023, 7, 3, 11, 0, tzinfo=timezone.utc),
        datetime(2023, 7, 3, 13, 30, tzinfo=timezone.utc),
        datetime(2023, 7, 3, 15, 30, tzinfo=timezone.utc),
    ]

    assert [window.end for window in windows] == [
        datetime(2023, 7, 3, 13, 30, tzinfo=timezone.utc),
        datetime(2023, 7, 3, 15, 30, tzinfo=timezone.utc),
        datetime(2023, 7, 3, 20, 0, tzinfo=timezone.utc),
    ]


def test_trading_windows_intersection_mode(
    coordinator: MarketCalendarCoordinator,
) -> None:
    start = datetime(2023, 7, 3, 11, 0, tzinfo=timezone.utc)
    end = datetime(2023, 7, 3, 21, 0, tzinfo=timezone.utc)

    windows = coordinator.aligned_windows(start, end)

    assert windows == [
        TradingWindow(
            start=datetime(2023, 7, 3, 13, 30, tzinfo=timezone.utc),
            end=datetime(2023, 7, 3, 15, 30, tzinfo=timezone.utc),
            markets=frozenset({"LSE", "NYSE"}),
        )
    ]


def test_filter_helpers(coordinator: MarketCalendarCoordinator) -> None:
    timestamps = [
        datetime(2023, 7, 3, 12, 0, tzinfo=timezone.utc),
        datetime(2023, 7, 3, 14, 0, tzinfo=timezone.utc),
        datetime(2023, 7, 3, 21, 0, tzinfo=timezone.utc),
    ]

    assert coordinator.filter_timestamps(timestamps, mode="union") == timestamps[:2]
    assert coordinator.filter_timestamps(timestamps, mode="intersection") == [
        timestamps[1]
    ]

    @dataclass
    class Signal:
        timestamp: datetime
        payload: str

    signals = [
        Signal(timestamp=timestamps[0], payload="ldn-only"),
        Signal(timestamp=timestamps[1], payload="overlap"),
        Signal(timestamp=timestamps[2], payload="closed"),
    ]

    filtered = coordinator.filter_signals(signals, mode="intersection")
    assert [signal.payload for signal in filtered] == ["overlap"]


def test_requires_timezone_aware_inputs(coordinator: MarketCalendarCoordinator) -> None:
    end = datetime(2023, 7, 3, 20, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        coordinator.session_events(datetime(2023, 7, 3, 11, 0), end)
