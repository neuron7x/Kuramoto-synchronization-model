# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Trading calendar utilities for deterministic backtests.

The calendar tracks regular trading hours, exchange holidays, and ad-hoc
session overrides while handling timezone daylight-saving transitions. The
intent is to provide deterministic scheduling utilities for backtests that need
to respect venue trading windows.

This module additionally exposes helpers to coordinate trading hours across
multiple venues. ``MarketCalendarCoordinator`` can derive shared trading
windows, build event calendars, and filter timestamps or signal-like payloads
so that downstream pipelines do not act on closed markets.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Callable, Iterable, Mapping, MutableMapping, Sequence
from zoneinfo import ZoneInfo

__all__ = [
    "SessionHours",
    "MarketCalendar",
    "MarketSessionEvent",
    "TradingWindow",
    "MarketCalendarCoordinator",
]


@dataclass(frozen=True)
class SessionHours:
    """Represents the open and close time (inclusive/exclusive) of a session."""

    open: time
    close: time

    @classmethod
    def from_value(cls, value: SessionHours | Sequence[time]) -> SessionHours:
        if isinstance(value, SessionHours):
            return value
        if (
            isinstance(value, Sequence)
            and len(value) == 2
            and isinstance(value[0], time)
            and isinstance(value[1], time)
        ):
            return cls(open=value[0], close=value[1])
        raise TypeError(
            "Session hours must be SessionHours or a (open, close) pair of time objects"
        )


class MarketCalendar:
    """Lightweight trading calendar with DST-aware session calculations."""

    def __init__(
        self,
        timezone: str,
        regular_hours: Mapping[int, SessionHours | Sequence[time]],
        *,
        holidays: Iterable[date] | None = None,
        special_sessions: Mapping[date, SessionHours | Sequence[time]] | None = None,
    ) -> None:
        self._tz = ZoneInfo(timezone)
        self._regular_hours = {
            int(weekday): SessionHours.from_value(session)
            for weekday, session in regular_hours.items()
        }
        self._holidays = {d for d in (holidays or [])}
        self._special_sessions = {
            session_date: SessionHours.from_value(session)
            for session_date, session in (special_sessions or {}).items()
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def is_open(self, timestamp: datetime) -> bool:
        """Return True if ``timestamp`` falls inside a trading session."""

        local_ts = self._localize(timestamp)
        session = self._session_for_date(local_ts.date())
        if session is None:
            return False

        open_dt = self._combine(local_ts.date(), session.open)
        close_dt = self._combine(local_ts.date(), session.close)
        if close_dt <= open_dt:
            close_dt += timedelta(days=1)
        return open_dt <= local_ts < close_dt

    def next_open(self, timestamp: datetime) -> datetime:
        """Return the next session open strictly after ``timestamp``."""

        search_dt = self._localize(timestamp)
        while True:
            session = self._session_for_date(search_dt.date())
            if session is not None:
                open_dt = self._combine(search_dt.date(), session.open)
                close_dt = self._combine(search_dt.date(), session.close)
                if close_dt <= open_dt:
                    close_dt += timedelta(days=1)
                if search_dt < open_dt:
                    return open_dt
                if search_dt < close_dt:
                    search_dt = close_dt + timedelta(microseconds=1)
                    continue
            search_dt = self._combine(search_dt.date() + timedelta(days=1), time(0, 0))

    def previous_close(self, timestamp: datetime) -> datetime:
        """Return the most recent session close at or before ``timestamp``."""

        search_dt = self._localize(timestamp)
        while True:
            session = self._session_for_date(search_dt.date())
            if session is not None:
                open_dt = self._combine(search_dt.date(), session.open)
                close_dt = self._combine(search_dt.date(), session.close)
                if close_dt <= open_dt:
                    close_dt += timedelta(days=1)
                if search_dt >= close_dt:
                    return close_dt
                if search_dt >= open_dt:
                    return close_dt
            search_dt = self._combine(
                search_dt.date() - timedelta(days=1), time(23, 59, 59, 999999)
            )

    def sessions_between(self, start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
        """Enumerate sessions intersecting the inclusive ``[start, end]`` window."""

        if end < start:
            raise ValueError("end must be greater than or equal to start")

        start_local = self._localize(start)
        end_local = self._localize(end)
        sessions: list[tuple[datetime, datetime]] = []

        cursor_date = start_local.date()
        while True:
            session = self._session_for_date(cursor_date)
            if session is not None:
                open_dt = self._combine(cursor_date, session.open)
                close_dt = self._combine(cursor_date, session.close)
                if close_dt <= open_dt:
                    close_dt += timedelta(days=1)
                if close_dt < start_local:
                    # Session ends before our start time, skip it
                    cursor_date += timedelta(days=1)
                    continue
                elif open_dt > end_local:
                    break
                else:
                    sessions.append((open_dt, close_dt))
                    if close_dt >= end_local:
                        break

            cursor_midnight = self._combine(cursor_date, time(0, 0))
            if cursor_midnight > end_local:
                break
            cursor_date += timedelta(days=1)

        return sessions

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _session_for_date(self, session_date: date) -> SessionHours | None:
        if session_date in self._holidays:
            return None
        if session_date in self._special_sessions:
            return self._special_sessions[session_date]
        weekday = session_date.weekday()
        return self._regular_hours.get(weekday)

    def _localize(self, timestamp: datetime) -> datetime:
        if timestamp.tzinfo is None:
            return timestamp.replace(tzinfo=self._tz)
        return timestamp.astimezone(self._tz)

    def _combine(self, session_date: date, when: time) -> datetime:
        return datetime.combine(session_date, when, tzinfo=self._tz)


@dataclass(frozen=True)
class MarketSessionEvent:
    """Represents an opening or closing event for a market session."""

    market: str
    kind: str
    timestamp: datetime
    local_timestamp: datetime

    def __post_init__(self) -> None:
        if self.kind not in {"open", "close"}:
            raise ValueError("kind must be 'open' or 'close'")
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        if self.local_timestamp.tzinfo is None:
            raise ValueError("local_timestamp must be timezone-aware")

    def as_timezone(self, zone: ZoneInfo) -> datetime:
        """Return the event timestamp converted to ``zone``."""

        return self.timestamp.astimezone(zone)


@dataclass(frozen=True)
class TradingWindow:
    """Defines a coordinated trading window across one or more markets."""

    start: datetime
    end: datetime
    markets: frozenset[str]

    def __post_init__(self) -> None:
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("start and end must be timezone-aware")
        if self.end <= self.start:
            raise ValueError("end must be after start")
        if not self.markets:
            raise ValueError("markets must be a non-empty collection")

    def duration(self) -> timedelta:
        """Return the length of the trading window."""

        return self.end - self.start

    def as_timezone(self, zone: ZoneInfo) -> tuple[datetime, datetime]:
        """Return the window bounds converted to ``zone``."""

        return self.start.astimezone(zone), self.end.astimezone(zone)


class MarketCalendarCoordinator:
    """Coordinates trading hours across multiple :class:`MarketCalendar`s."""

    def __init__(self, calendars: Mapping[str, MarketCalendar]) -> None:
        if not calendars:
            raise ValueError("at least one market calendar must be provided")
        self._calendars: MutableMapping[str, MarketCalendar] = {
            name: calendar for name, calendar in calendars.items()
        }

    # ------------------------------------------------------------------
    # Event calendar construction
    # ------------------------------------------------------------------
    def session_events(
        self,
        start: datetime,
        end: datetime,
        *,
        markets: Iterable[str] | None = None,
    ) -> list[MarketSessionEvent]:
        """Enumerate session open/close events within ``[start, end]``.

        Event timestamps are normalised to UTC to simplify downstream ordering
        and comparisons while ``local_timestamp`` retains the venue-local
        representation.
        """

        start_utc, end_utc = self._normalize_range(start, end)
        subset = self._select_markets(markets)

        events: list[MarketSessionEvent] = []
        for market, calendar in subset.items():
            for open_dt, close_dt in calendar.sessions_between(start, end):
                open_utc = self._to_utc(open_dt)
                close_utc = self._to_utc(close_dt)
                if start_utc <= open_utc <= end_utc:
                    events.append(
                        MarketSessionEvent(
                            market=market,
                            kind="open",
                            timestamp=open_utc,
                            local_timestamp=open_dt,
                        )
                    )
                if start_utc <= close_utc <= end_utc:
                    events.append(
                        MarketSessionEvent(
                            market=market,
                            kind="close",
                            timestamp=close_utc,
                            local_timestamp=close_dt,
                        )
                    )

        events.sort(key=lambda evt: (evt.timestamp, 0 if evt.kind == "open" else 1, evt.market))
        return events

    # ------------------------------------------------------------------
    # Trading window alignment
    # ------------------------------------------------------------------
    def trading_windows(
        self,
        start: datetime,
        end: datetime,
        *,
        mode: str = "union",
        markets: Iterable[str] | None = None,
    ) -> list[TradingWindow]:
        """Return trading windows across the selected markets.

        ``mode`` can be ``"union"`` (any market open) or ``"intersection"``
        (all selected markets open). Windows are normalised to UTC.
        """

        start_utc, end_utc = self._normalize_range(start, end)
        subset = self._select_markets(markets)
        events = self._ordered_events(start, end, subset)

        if mode not in {"union", "intersection"}:
            raise ValueError("mode must be 'union' or 'intersection'")

        required = frozenset(subset.keys())
        active = {
            market
            for market, open_dt, close_dt in self._collect_sessions(start, end, subset)
            if self._to_utc(open_dt) <= start_utc < self._to_utc(close_dt)
        }

        windows: list[TradingWindow] = []
        last_ts = start_utc

        def condition() -> bool:
            if mode == "union":
                return bool(active)
            return required.issubset(active)

        for market, kind, timestamp in events:
            if timestamp < start_utc:
                if kind == "open":
                    active.add(market)
                else:
                    active.discard(market)
                continue
            if timestamp > end_utc:
                break
            if condition() and last_ts < timestamp:
                windows.append(
                    TradingWindow(
                        start=last_ts,
                        end=timestamp,
                        markets=frozenset(active),
                    )
                )
            if kind == "open":
                active.add(market)
            else:
                active.discard(market)
            last_ts = max(last_ts, timestamp)

        if condition() and last_ts < end_utc:
            windows.append(TradingWindow(start=last_ts, end=end_utc, markets=frozenset(active)))

        return windows

    def aligned_windows(
        self,
        start: datetime,
        end: datetime,
        *,
        markets: Iterable[str] | None = None,
    ) -> list[TradingWindow]:
        """Return windows where all selected markets are simultaneously open."""

        return self.trading_windows(
            start,
            end,
            mode="intersection",
            markets=markets,
        )

    # ------------------------------------------------------------------
    # Filtering helpers
    # ------------------------------------------------------------------
    def filter_timestamps(
        self,
        timestamps: Iterable[datetime],
        *,
        mode: str = "union",
        markets: Iterable[str] | None = None,
    ) -> list[datetime]:
        """Return timestamps that fall inside the configured trading hours."""

        subset = self._select_markets(markets)
        self._validate_mode(mode)
        filtered: list[datetime] = []
        for ts in timestamps:
            self._ensure_aware(ts)
            if self._is_open(ts, subset, mode):
                filtered.append(ts)
        return filtered

    def filter_signals(
        self,
        signals: Iterable[object],
        *,
        timestamp_getter: Callable[[object], datetime] | None = None,
        mode: str = "union",
        markets: Iterable[str] | None = None,
    ) -> list[object]:
        """Filter signal-like payloads based on trading hours.

        ``timestamp_getter`` should return a timezone-aware ``datetime`` for the
        provided signal. When omitted, an attribute named ``timestamp`` is
        accessed.
        """

        subset = self._select_markets(markets)
        self._validate_mode(mode)

        if timestamp_getter is None:
            timestamp_getter = self._default_timestamp_getter

        filtered: list[object] = []
        for signal in signals:
            ts = timestamp_getter(signal)
            self._ensure_aware(ts)
            if self._is_open(ts, subset, mode):
                filtered.append(signal)
        return filtered

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _default_timestamp_getter(self, signal: object) -> datetime:
        ts = getattr(signal, "timestamp", None)
        if ts is None:
            raise AttributeError(
                "signal does not provide a 'timestamp' attribute and no getter was supplied"
            )
        return ts

    def _validate_mode(self, mode: str) -> None:
        if mode not in {"union", "intersection"}:
            raise ValueError("mode must be 'union' or 'intersection'")

    def _is_open(
        self,
        timestamp: datetime,
        calendars: Mapping[str, MarketCalendar],
        mode: str,
    ) -> bool:
        if mode == "union":
            return any(calendar.is_open(timestamp) for calendar in calendars.values())
        return all(calendar.is_open(timestamp) for calendar in calendars.values())

    def _select_markets(self, markets: Iterable[str] | None) -> Mapping[str, MarketCalendar]:
        if markets is None:
            return self._calendars
        subset = {name: self._calendars[name] for name in markets}
        if not subset:
            raise ValueError("markets must reference at least one configured calendar")
        return subset

    def _normalize_range(self, start: datetime, end: datetime) -> tuple[datetime, datetime]:
        self._ensure_aware(start)
        self._ensure_aware(end)
        if end < start:
            raise ValueError("end must be greater than or equal to start")
        return start.astimezone(timezone.utc), end.astimezone(timezone.utc)

    def _ensure_aware(self, timestamp: datetime) -> None:
        if timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")

    def _to_utc(self, timestamp: datetime) -> datetime:
        self._ensure_aware(timestamp)
        return timestamp.astimezone(timezone.utc)

    def _collect_sessions(
        self,
        start: datetime,
        end: datetime,
        calendars: Mapping[str, MarketCalendar],
    ) -> list[tuple[str, datetime, datetime]]:
        sessions: list[tuple[str, datetime, datetime]] = []
        for market, calendar in calendars.items():
            sessions.extend(
                (market, open_dt, close_dt)
                for open_dt, close_dt in calendar.sessions_between(start, end)
            )
        return sessions

    def _ordered_events(
        self,
        start: datetime,
        end: datetime,
        calendars: Mapping[str, MarketCalendar],
    ) -> list[tuple[str, str, datetime]]:
        events: list[tuple[str, str, datetime]] = []
        for market, open_dt, close_dt in self._collect_sessions(start, end, calendars):
            events.append((market, "open", self._to_utc(open_dt)))
            events.append((market, "close", self._to_utc(close_dt)))
        events.sort(key=lambda evt: (evt[2], 0 if evt[1] == "open" else 1, evt[0]))
        return events
