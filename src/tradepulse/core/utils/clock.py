"""Clock helpers used to keep tests reproducible."""

from __future__ import annotations

# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from contextlib import ExitStack, contextmanager
from datetime import date, datetime, timezone
from typing import Iterator
from unittest import mock

FrozenTimeInput = datetime | float | int


def _normalize_datetime(value: FrozenTimeInput) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromtimestamp(float(value), tz=timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@contextmanager
def freeze_time(target: FrozenTimeInput) -> Iterator[datetime]:
    """Freeze common clock sources to a fixed moment in time."""

    frozen = _normalize_datetime(target)
    frozen_epoch = frozen.timestamp()
    frozen_naive = frozen.astimezone(timezone.utc).replace(tzinfo=None)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz: timezone | None = None) -> datetime:
            if tz is None:
                return frozen_naive
            return frozen.astimezone(tz)

        @classmethod
        def utcnow(cls) -> datetime:
            return frozen_naive

    class FrozenDate(date):
        @classmethod
        def today(cls) -> date:
            return frozen.date()

    with ExitStack() as stack:
        stack.enter_context(mock.patch("time.time", lambda: frozen_epoch))
        stack.enter_context(
            mock.patch("time.time_ns", lambda: int(frozen_epoch * 1_000_000_000))
        )
        stack.enter_context(mock.patch("time.monotonic", lambda: 1.0))
        stack.enter_context(mock.patch("time.monotonic_ns", lambda: 1_000_000_000))
        stack.enter_context(mock.patch("time.perf_counter", lambda: 1.0))
        stack.enter_context(mock.patch("time.perf_counter_ns", lambda: 1_000_000_000))
        stack.enter_context(mock.patch("datetime.datetime", FrozenDateTime))
        stack.enter_context(mock.patch("datetime.date", FrozenDate))
        yield frozen


__all__ = ["freeze_time"]
