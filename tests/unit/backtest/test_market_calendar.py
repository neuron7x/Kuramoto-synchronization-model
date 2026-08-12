# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from backtest.market_calendar import MarketCalendar, SessionHours


def _calendar() -> MarketCalendar:
    hours = {idx: SessionHours(time(9, 30), time(16, 0)) for idx in range(5)}
    holidays = {date(2023, 7, 4)}
    return MarketCalendar("America/New_York", regular_hours=hours, holidays=holidays)


def test_calendar_is_open_and_holiday() -> None:
    calendar = _calendar()
    open_time = datetime(2023, 7, 3, 10, 0, tzinfo=ZoneInfo("America/New_York"))
    assert calendar.is_open(open_time)

    holiday_time = datetime(2023, 7, 4, 11, 0, tzinfo=ZoneInfo("America/New_York"))
    assert not calendar.is_open(holiday_time)


def test_calendar_next_open_handles_dst_transitions() -> None:
    calendar = _calendar()

    before_dst_start = datetime(2023, 3, 10, 20, 0, tzinfo=ZoneInfo("UTC"))
    next_open = calendar.next_open(before_dst_start)
    assert next_open.date() == date(2023, 3, 13)
    assert next_open.tzinfo is not None
    assert next_open.astimezone(ZoneInfo("UTC")).hour == 13  # 09:30 EDT

    before_dst_end = datetime(2023, 11, 3, 20, 0, tzinfo=ZoneInfo("UTC"))
    next_open = calendar.next_open(before_dst_end)
    assert next_open.date() == date(2023, 11, 6)
    assert next_open.astimezone(ZoneInfo("UTC")).hour == 14  # 09:30 EST


def test_calendar_sessions_between_range() -> None:
    calendar = _calendar()
    start = datetime(2023, 3, 9, 0, 0, tzinfo=ZoneInfo("UTC"))
    end = datetime(2023, 3, 14, 23, 59, tzinfo=ZoneInfo("UTC"))
    sessions = calendar.sessions_between(start, end)

    # Covers Thursday/Friday before DST and Monday/Tuesday after DST jump (holiday not in window).
    assert len(sessions) == 4
    open_hours = [session[0].astimezone(ZoneInfo("UTC")).hour for session in sessions]
    assert open_hours == [14, 14, 13, 13]
