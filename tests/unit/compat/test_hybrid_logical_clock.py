# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for ``HybridLogicalTimeSource`` — Phase 1, T-axis extension.

Contract summary
----------------
HLC-1  ``tick()`` emits strictly-increasing readings on one instance.
HLC-2  When the wall clock does not advance between calls, the logical
       counter strictly increases so total order holds.
HLC-3  ``observe(remote)`` dominates both local and remote readings.
HLC-4  Deterministic under a FrozenClock base: identical construction
       + update sequence → identical tick sequence.
HLC-5  Causality: emitting a tick after observing a remote reading
       produces an output that strictly dominates the remote in the
       lex order ``(physical_ns, logical)``.
"""

from __future__ import annotations

from datetime import datetime, timezone

from geosync.core.compat import FrozenClock, HybridLogicalTimeSource


def _hlc_at(instant: datetime) -> HybridLogicalTimeSource:
    return HybridLogicalTimeSource(base=FrozenClock(instant=instant))


class TestMonotonicity:
    def test_ticks_strictly_increase(self) -> None:
        hlc = _hlc_at(datetime(2026, 1, 1, tzinfo=timezone.utc))
        readings = [hlc.tick() for _ in range(10)]
        for earlier, later in zip(readings[:-1], readings[1:], strict=True):
            assert later > earlier

    def test_logical_counter_advances_under_frozen_wall_clock(self) -> None:
        hlc = _hlc_at(datetime(2026, 1, 1, tzinfo=timezone.utc))
        # Base clock is frozen; the wall-clock reading never changes,
        # so the logical counter must carry the monotonicity.
        a = hlc.tick()
        b = hlc.tick()
        assert a[0] == b[0]  # same physical ns
        assert b[1] == a[1] + 1


class TestObserveDominates:
    def test_observe_of_future_reading_catches_up(self) -> None:
        hlc = _hlc_at(datetime(2026, 1, 1, tzinfo=timezone.utc))
        hlc.tick()  # local = (W, 0)
        future_physical = 10**20  # far future
        merged = hlc.observe(future_physical, 42)
        assert merged[0] == future_physical
        assert merged[1] == 43  # remote_logical + 1

    def test_observe_strictly_dominates_remote(self) -> None:
        hlc = _hlc_at(datetime(2026, 1, 1, tzinfo=timezone.utc))
        remote = (10**20, 5)
        merged = hlc.observe(*remote)
        assert merged > remote


class TestDeterminism:
    def test_two_instances_same_seed_same_trace(self) -> None:
        instant = datetime(2026, 1, 1, tzinfo=timezone.utc)
        a = _hlc_at(instant)
        b = _hlc_at(instant)

        trace_a = [a.tick() for _ in range(5)]
        trace_a.append(a.observe(10**19, 3))
        trace_a.append(a.tick())

        trace_b = [b.tick() for _ in range(5)]
        trace_b.append(b.observe(10**19, 3))
        trace_b.append(b.tick())

        assert trace_a == trace_b

    def test_snapshot_does_not_advance(self) -> None:
        hlc = _hlc_at(datetime(2026, 1, 1, tzinfo=timezone.utc))
        hlc.tick()
        snap_before = hlc.snapshot()
        snap_again = hlc.snapshot()
        assert snap_before == snap_again
