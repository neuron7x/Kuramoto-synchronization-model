# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the ``epoch_ns()`` extension of the ``Clock`` protocol.

Contract summary
----------------
C-CLK-1  ``SystemClock``, ``FrozenClock``, and any duck-typed object with
         ``now() / monotonic_ns() / epoch_ns()`` all satisfy ``isinstance(
         obj, Clock)`` under runtime-checkable ``Protocol``.
C-CLK-2  ``SystemClock.epoch_ns()`` is strictly positive and within a
         10-second window of ``time.time_ns()``.
C-CLK-3  ``FrozenClock.epoch_ns()`` is deterministic: two clocks pinned to
         the same ``instant`` return identical values.
C-CLK-4  ``FrozenClock.advance(seconds=n)`` advances ``epoch_ns`` by
         ``n * 1e9`` (within 1 ns rounding).
C-CLK-5  Naive ``instant`` is rejected at construction.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest

from geosync.core.compat import Clock, FrozenClock, SystemClock, epoch_ns


class TestClockProtocolConformance:
    def test_system_clock_satisfies_protocol(self) -> None:
        assert isinstance(SystemClock(), Clock)

    def test_frozen_clock_satisfies_protocol(self) -> None:
        assert isinstance(FrozenClock(), Clock)


class TestSystemClockEpochNs:
    def test_value_near_wall_clock(self) -> None:
        before = time.time_ns()
        observed = SystemClock().epoch_ns()
        after = time.time_ns()
        # Allow generous slack (10 s) — CI hosts can be arbitrarily slow.
        assert before - 10_000_000_000 <= observed <= after + 10_000_000_000

    def test_module_level_epoch_ns_agrees(self) -> None:
        # ``epoch_ns()`` module function is the default implementation
        # used by ``SystemClock``; both must agree to within ~1 ms.
        a = epoch_ns()
        b = SystemClock().epoch_ns()
        assert abs(b - a) < 1_000_000


class TestFrozenClockEpochNsDeterminism:
    def test_same_instant_identical_epoch_ns(self) -> None:
        instant = datetime(2026, 1, 1, tzinfo=timezone.utc)
        a = FrozenClock(instant=instant).epoch_ns()
        b = FrozenClock(instant=instant).epoch_ns()
        assert a == b

    def test_advance_by_seconds_increments_epoch_ns(self) -> None:
        clock = FrozenClock(instant=datetime(2026, 1, 1, tzinfo=timezone.utc))
        initial = clock.epoch_ns()
        clock.advance(seconds=7.5)
        delta = clock.epoch_ns() - initial
        assert abs(delta - 7_500_000_000) <= 1

    def test_naive_instant_rejected(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            FrozenClock(instant=datetime(2026, 1, 1))


class TestCustomClockImplementation:
    def test_duck_typed_clock_satisfies_protocol(self) -> None:
        class _MyClock:
            def now(self) -> datetime:
                return datetime(2030, 6, 1, tzinfo=timezone.utc)

            def monotonic_ns(self) -> int:
                return 42

            def epoch_ns(self) -> int:
                return 1_893_456_000_000_000_000

        assert isinstance(_MyClock(), Clock)
