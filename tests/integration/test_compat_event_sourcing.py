# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Integration test: the Clock protocol pays for itself.

The DomainEvent base class resolves ``default_clock().now()`` at field
instantiation time, so installing a :class:`FrozenClock` via
:func:`use_clock` produces fully deterministic ``occurred_at`` timestamps
— which is the property we actually wanted when we went through the
compat migration.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from core.compat import UTC, FrozenClock, SystemClock, default_clock, frozen_clock
from core.events.sourcing import OrderCreated
from domain.order import OrderSide, OrderType


def _build_event(order_id: str = "o-1") -> OrderCreated:
    return OrderCreated(
        order_id=order_id,
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        quantity=1.0,
        order_type=OrderType.LIMIT,
    )


def test_frozen_clock_makes_occurred_at_deterministic() -> None:
    """Two events emitted under the same FrozenClock have identical occurred_at."""

    pin = datetime(2026, 4, 18, 12, 0, 0, tzinfo=UTC)
    with frozen_clock(instant=pin):
        event_a = _build_event("o-1")
        event_b = _build_event("o-2")

    assert event_a.occurred_at == pin
    assert event_b.occurred_at == pin


def test_advancing_frozen_clock_shifts_occurred_at_monotonically() -> None:
    """After advance(), a new event sees the advanced instant."""

    pin = datetime(2026, 4, 18, 12, 0, 0, tzinfo=UTC)
    with frozen_clock(instant=pin) as clock:
        first = _build_event("o-1")
        clock.advance(seconds=5)
        second = _build_event("o-2")

    assert second.occurred_at - first.occurred_at == timedelta(seconds=5)


def test_use_clock_context_restores_system_clock() -> None:
    """After the with-block, the process-wide default reverts to SystemClock."""

    pin = datetime(1970, 1, 1, tzinfo=UTC)
    with frozen_clock(instant=pin) as clock:
        assert default_clock() is clock
    assert isinstance(default_clock(), SystemClock)


def test_system_clock_occurred_at_is_tz_aware_and_recent() -> None:
    """Without any clock override, events get wall-time tz-aware timestamps."""

    before = SystemClock().now()
    event = _build_event("o-wall")
    after = SystemClock().now()

    assert event.occurred_at.tzinfo is not None
    assert before <= event.occurred_at <= after


def test_frozen_clock_is_usable_via_pure_api_without_monkeypatch() -> None:
    """FrozenClock.now() returns exactly what we gave it — no drift."""

    pin = datetime(2100, 1, 1, 0, 0, 0, tzinfo=UTC)
    clock = FrozenClock(instant=pin)
    assert clock.now() == pin
    assert clock.now() == pin  # stable across reads
    first = clock.monotonic_ns()
    second = clock.monotonic_ns()
    assert second > first  # monotonic counter advances independently of wall time
    assert clock.now() == pin  # wall clock remains frozen
