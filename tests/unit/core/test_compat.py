# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit and property tests for :mod:`geosync.core.compat`.

Covers:
* tz-awareness of :func:`utc_now`
* strict monotonicity of :func:`monotonic_ns`
* RFC 3339 ``Z`` suffix from :func:`safe_isoformat`
* :class:`FrozenClock` determinism and safety invariants
* :func:`use_clock` / :func:`set_default_clock` context isolation
* identity parity between ``core.compat`` (legacy shim) and
  ``geosync.core.compat`` (canonical) — every public symbol must be the
  *same* object.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from hypothesis import given
from hypothesis import strategies as st

from geosync.core import compat
from geosync.core.compat import (
    UTC,
    Clock,
    FrozenClock,
    SystemClock,
    default_clock,
    frozen_clock,
    monotonic_ns,
    safe_isoformat,
    set_default_clock,
    use_clock,
    utc_now,
)


class TestUtcNow:
    def test_returns_tz_aware(self) -> None:
        now = utc_now()
        assert now.tzinfo is not None
        assert now.utcoffset() == timedelta(0)

    def test_uses_canonical_utc(self) -> None:
        assert utc_now().tzinfo is UTC

    def test_monotone_over_calls(self) -> None:
        first = utc_now()
        second = utc_now()
        assert second >= first


class TestMonotonicNs:
    def test_strictly_nondecreasing(self) -> None:
        samples = [monotonic_ns() for _ in range(64)]
        assert all(b >= a for a, b in zip(samples, samples[1:]))

    def test_returns_int(self) -> None:
        assert isinstance(monotonic_ns(), int)


class TestSafeIsoformat:
    def test_z_suffix(self) -> None:
        ts = datetime(2026, 4, 18, 12, 34, 56, tzinfo=UTC)
        assert safe_isoformat(ts) == "2026-04-18T12:34:56Z"

    def test_microseconds_preserved(self) -> None:
        ts = datetime(2026, 4, 18, 12, 34, 56, 123456, tzinfo=UTC)
        assert safe_isoformat(ts).endswith("Z")
        assert "123456" in safe_isoformat(ts)

    def test_naive_rejected(self) -> None:
        naive = datetime(2026, 4, 18, 12, 34, 56)
        with pytest.raises(ValueError, match="tz-aware|timezone-aware"):
            safe_isoformat(naive)

    def test_non_utc_tz_normalised(self) -> None:
        tokyo = timezone(timedelta(hours=9))
        ts = datetime(2026, 4, 18, 21, 34, 56, tzinfo=tokyo)
        assert safe_isoformat(ts) == "2026-04-18T12:34:56Z"


class TestFrozenClock:
    def test_default_instant_tz_aware(self) -> None:
        clock = FrozenClock()
        assert clock.now().tzinfo is not None

    def test_now_is_stable_without_advance(self) -> None:
        clock = FrozenClock()
        assert clock.now() == clock.now()

    def test_monotonic_advances_on_read(self) -> None:
        clock = FrozenClock()
        samples = [clock.monotonic_ns() for _ in range(32)]
        assert all(b > a for a, b in zip(samples, samples[1:]))

    def test_advance_moves_wall_clock(self) -> None:
        clock = FrozenClock()
        start = clock.now()
        clock.advance(seconds=1.5)
        assert clock.now() == start + timedelta(seconds=1.5)

    def test_advance_negative_rejected(self) -> None:
        clock = FrozenClock()
        with pytest.raises(ValueError, match="cannot move backwards"):
            clock.advance(seconds=-1)
        with pytest.raises(ValueError, match="cannot move backwards"):
            clock.advance(nanoseconds=-1)

    def test_set_requires_tz_aware(self) -> None:
        clock = FrozenClock()
        with pytest.raises(ValueError, match="tz-aware"):
            clock.set(datetime(2026, 1, 1))

    def test_rejects_naive_constructor(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            FrozenClock(instant=datetime(2026, 1, 1))

    def test_implements_clock_protocol(self) -> None:
        assert isinstance(FrozenClock(), Clock)

    def test_system_clock_implements_protocol(self) -> None:
        assert isinstance(SystemClock(), Clock)


class TestClockInjection:
    def test_default_clock_is_system(self) -> None:
        assert isinstance(default_clock(), SystemClock)

    def test_use_clock_restores_previous(self) -> None:
        before = default_clock()
        with use_clock(FrozenClock()):
            assert isinstance(default_clock(), FrozenClock)
        assert default_clock() is before

    def test_set_default_clock_rejects_non_clock(self) -> None:
        with pytest.raises(TypeError):
            set_default_clock(object())

    def test_frozen_clock_context_yields_instance(self) -> None:
        pin = datetime(2030, 6, 1, tzinfo=UTC)
        with frozen_clock(instant=pin) as clock:
            assert clock.now() == pin
            assert default_clock() is clock
        assert not isinstance(default_clock(), FrozenClock)


class TestShimParity:
    """Legacy ``core.compat`` must re-export identical objects."""

    @pytest.mark.parametrize(
        "name",
        [
            "UTC",
            "Clock",
            "FrozenClock",
            "SystemClock",
            "default_clock",
            "frozen_clock",
            "monotonic_ns",
            "safe_isoformat",
            "set_default_clock",
            "use_clock",
            "utc_now",
        ],
    )
    def test_symbol_identity(self, name: str) -> None:
        from core import compat as legacy

        assert getattr(legacy, name) is getattr(compat, name)


# ---------------------------------------------------------------------------
# Property-based tests (Hypothesis)
# ---------------------------------------------------------------------------


@given(seconds=st.floats(min_value=0, max_value=86_400, allow_nan=False, allow_infinity=False))
def test_frozen_clock_advance_is_additive(seconds: float) -> None:
    clock = FrozenClock()
    start = clock.now()
    clock.advance(seconds=seconds)
    delta = (clock.now() - start).total_seconds()
    # Tolerate float rounding up to microsecond scale — advance uses int(ns).
    assert abs(delta - seconds) < 1e-6


@given(
    year=st.integers(min_value=1900, max_value=9000),
    month=st.integers(min_value=1, max_value=12),
    day=st.integers(min_value=1, max_value=28),
    hour=st.integers(min_value=0, max_value=23),
    minute=st.integers(min_value=0, max_value=59),
    second=st.integers(min_value=0, max_value=59),
)
def test_safe_isoformat_always_ends_in_z(
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int,
    second: int,
) -> None:
    ts = datetime(year, month, day, hour, minute, second, tzinfo=UTC)
    formatted = safe_isoformat(ts)
    assert formatted.endswith("Z")
    assert "+" not in formatted


@given(
    year=st.integers(min_value=2000, max_value=2099),
    month=st.integers(min_value=1, max_value=12),
    day=st.integers(min_value=1, max_value=28),
    hour=st.integers(min_value=0, max_value=23),
    minute=st.integers(min_value=0, max_value=59),
    second=st.integers(min_value=0, max_value=59),
    micro=st.integers(min_value=0, max_value=999_999),
)
def test_safe_isoformat_round_trip(
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int,
    second: int,
    micro: int,
) -> None:
    """``safe_isoformat`` output parses back to the original instant."""
    ts = datetime(year, month, day, hour, minute, second, micro, tzinfo=UTC)
    formatted = safe_isoformat(ts)
    # fromisoformat needs "+00:00" not "Z" — swap it back for the parse.
    parsed = datetime.fromisoformat(formatted.replace("Z", "+00:00"))
    assert parsed == ts


def test_frozen_clock_advance_by_zero_is_identity() -> None:
    """advance(0) must not mutate the wall instant."""
    clock = FrozenClock()
    before = clock.now()
    clock.advance(seconds=0, nanoseconds=0)
    assert clock.now() == before


def test_system_clock_never_goes_backwards_in_short_loop() -> None:
    """Two successive SystemClock reads are monotonic in practice."""
    clock = SystemClock()
    samples = [clock.now() for _ in range(256)]
    assert all(b >= a for a, b in zip(samples, samples[1:]))


@given(
    n=st.integers(min_value=1, max_value=1000),
)
def test_monotonic_ns_strictly_nondecreasing_under_load(n: int) -> None:
    """``monotonic_ns`` never reports a value smaller than a prior one."""
    samples = [monotonic_ns() for _ in range(n)]
    assert all(b >= a for a, b in zip(samples, samples[1:]))
