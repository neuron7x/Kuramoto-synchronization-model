# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Cross-version compatibility and deterministic-clock utilities.

Canonical home for timezone-aware timestamping across GeoSync. Provides:

* ``UTC`` — stable reference to the IANA UTC tzinfo (independent of the
  ``datetime.UTC`` alias, which only exists on CPython >= 3.11).
* ``utc_now`` — timezone-aware now() wrapper used everywhere we currently
  write ``datetime.now(UTC)`` — single indirection makes the entire codebase
  monkey-patchable for deterministic tests and failure injection.
* ``monotonic_ns`` — nanosecond monotonic clock for latency instrumentation
  (wall-clock ``utc_now`` is unsafe for interval measurement due to NTP
  slew / leap-seconds).
* ``safe_isoformat`` — RFC 3339-style formatter that normalises the ``+00:00``
  suffix to ``Z`` (required by several of our downstream consumers and the
  localization coverage report).
* ``Clock`` — typing.Protocol decoupling consumers from wall-time so that
  event-sourcing, audit logging and incident response can be driven by a
  frozen clock in tests without monkey-patching globals.
* ``FrozenClock`` — reference test double, strictly monotonic and safe for
  concurrent reads.
* ``SystemClock`` — production implementation wrapping :func:`utc_now` and
  :func:`monotonic_ns`.
* ``default_clock`` / ``set_default_clock`` — process-wide override hook for
  integration tests, with a context-manager form for scoped substitution.

This module intentionally does **not** import anything from ``core`` or other
GeoSync runtime packages so that it is safe to import from the very bottom of
the dependency graph (observability, security audit, scripts).
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Iterator, Protocol, runtime_checkable

__all__ = [
    "UTC",
    "Clock",
    "FrozenClock",
    "HybridLogicalTimeSource",
    "SystemClock",
    "default_clock",
    "epoch_ns",
    "frozen_clock",
    "monotonic_ns",
    "safe_isoformat",
    "set_default_clock",
    "use_clock",
    "utc_now",
]


#: Canonical UTC tzinfo. Prefer this over ``datetime.UTC`` so that a single
#: symbol resolves identically on CPython 3.11+ and on any future alternate
#: interpreters which expose ``timezone.utc`` but not the ``UTC`` alias.
UTC: timezone = timezone.utc


def utc_now() -> datetime:
    """Return the current wall-clock time as a timezone-aware UTC ``datetime``.

    Prefer this helper to ``datetime.now(UTC)`` so that test suites can patch
    a single symbol (or better — inject a :class:`Clock`).
    """

    return datetime.now(UTC)


def monotonic_ns() -> int:
    """Return a monotonic nanosecond counter suitable for latency measurement.

    Unlike :func:`utc_now`, this value is immune to NTP adjustments, leap
    seconds, and manual clock changes. Absolute value has no meaning; only
    deltas between two calls are significant.
    """

    return time.monotonic_ns()


def safe_isoformat(ts: datetime) -> str:
    """Format a timezone-aware ``datetime`` as RFC 3339 with a ``Z`` suffix.

    Several downstream systems (localization coverage report, audit log
    consumers, MiFID II TRS fields) require the ``Z`` form rather than
    ``+00:00``. Naive datetimes are rejected — the caller must pass a
    tz-aware value.
    """

    if ts.tzinfo is None:
        raise ValueError("safe_isoformat requires a timezone-aware datetime; got naive")
    return ts.astimezone(UTC).isoformat().replace("+00:00", "Z")


@runtime_checkable
class Clock(Protocol):
    """Minimal clock protocol.

    Any object providing ``now()``, ``monotonic_ns()`` and ``epoch_ns()``
    can stand in for the system clock. This decouples event sourcing,
    audit logging, incident response, and cortex regime modulation from
    direct wall-time access.

    ``now()`` is a tz-aware ``datetime`` (human-readable, microsecond
    resolution). ``monotonic_ns()`` is a monotonic counter safe for
    latency measurement but meaningless in absolute terms. ``epoch_ns()``
    is a wall-clock Unix timestamp in nanoseconds — machine-orderable
    across processes, immune to timezone / microsecond quantisation, and
    the canonical persistence format for event-store ordering.
    """

    def now(self) -> datetime:
        """Return the current wall-clock time as tz-aware ``datetime``."""
        ...

    def monotonic_ns(self) -> int:
        """Return a nanosecond monotonic counter."""
        ...

    def epoch_ns(self) -> int:
        """Return the current wall-clock time as a Unix-epoch nanosecond integer."""
        ...


def epoch_ns() -> int:
    """Module-level default for :meth:`Clock.epoch_ns`.

    Equivalent to :func:`time.time_ns` on CPython. Use this only when
    the caller is explicitly outside the DI boundary; production code
    should route through an injected :class:`Clock` so that tests can
    freeze the value.
    """

    return time.time_ns()


class SystemClock:
    """Production :class:`Clock` backed by :func:`utc_now`, :func:`monotonic_ns`, :func:`epoch_ns`."""

    __slots__ = ()

    def now(self) -> datetime:
        return utc_now()

    def monotonic_ns(self) -> int:
        return monotonic_ns()

    def epoch_ns(self) -> int:
        return epoch_ns()


@dataclass
class FrozenClock:
    """Deterministic :class:`Clock` for tests.

    * :meth:`now` returns the current ``instant`` (advanceable via
      :meth:`advance` / :meth:`set`).
    * :meth:`monotonic_ns` returns a strictly monotonic nanosecond counter
      that is independent of ``instant`` so that tests can exercise
      latency-sensitive code paths without time travel side effects.

    The implementation is thread-safe; it is legal to drive the clock from
    a test thread while the system-under-test reads from worker threads.
    """

    instant: datetime = field(default_factory=lambda: datetime(2024, 1, 1, tzinfo=UTC))
    _mono_ns: int = field(default=0, init=False, repr=False)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.instant.tzinfo is None:
            raise ValueError("FrozenClock requires a timezone-aware instant")

    def now(self) -> datetime:
        with self._lock:
            return self.instant

    def monotonic_ns(self) -> int:
        with self._lock:
            self._mono_ns += 1
            return self._mono_ns

    def epoch_ns(self) -> int:
        """Return the current ``instant`` as a Unix-epoch nanosecond integer.

        This is wall-clock (advances with :meth:`advance` / :meth:`set`) and
        therefore distinct from :meth:`monotonic_ns`. Two FrozenClocks pinned
        to the same ``instant`` return the same value; that is the property
        tests rely on when comparing persisted events across replays.
        """

        with self._lock:
            return int(self.instant.timestamp() * 1_000_000_000)

    def advance(self, *, seconds: float = 0.0, nanoseconds: int = 0) -> datetime:
        """Move the wall-clock forward. Negative deltas are rejected."""

        if seconds < 0 or nanoseconds < 0:
            raise ValueError("FrozenClock cannot move backwards")
        delta_ns = int(seconds * 1_000_000_000) + nanoseconds
        with self._lock:
            self.instant = self.instant.fromtimestamp(
                self.instant.timestamp() + delta_ns / 1_000_000_000, tz=UTC
            )
            self._mono_ns += delta_ns
            return self.instant

    def set(self, instant: datetime) -> None:
        """Replace the wall-clock. Monotonic counter is unaffected."""

        if instant.tzinfo is None:
            raise ValueError("FrozenClock.set requires a tz-aware datetime")
        with self._lock:
            self.instant = instant.astimezone(UTC)


_DEFAULT_CLOCK_LOCK: Lock = Lock()
_DEFAULT_CLOCK: Clock = SystemClock()


def default_clock() -> Clock:
    """Return the currently-installed default :class:`Clock`."""

    return _DEFAULT_CLOCK


def set_default_clock(clock: Clock) -> Clock:
    """Install ``clock`` as the process-wide default, returning the previous one.

    Use via :func:`use_clock` where possible; direct replacement is intended
    for long-running integration harnesses (e.g. the resilience test suite
    that spins a FrozenClock for the full session).
    """

    global _DEFAULT_CLOCK
    if not isinstance(clock, Clock):
        raise TypeError(f"clock must implement Clock protocol, got {type(clock)!r}")
    with _DEFAULT_CLOCK_LOCK:
        previous = _DEFAULT_CLOCK
        _DEFAULT_CLOCK = clock
    return previous


@contextmanager
def use_clock(clock: Clock) -> Iterator[Clock]:
    """Scoped replacement of the default clock for a single test/code block."""

    previous = set_default_clock(clock)
    try:
        yield clock
    finally:
        set_default_clock(previous)


@contextmanager
def frozen_clock(
    instant: datetime | None = None,
) -> Iterator[FrozenClock]:
    """Convenience context manager: install a :class:`FrozenClock` and yield it."""

    clock = FrozenClock(instant=instant) if instant is not None else FrozenClock()
    with use_clock(clock):
        yield clock


# ---------------------------------------------------------------------------
# Hybrid Logical Clock (HLC) adapter
# ---------------------------------------------------------------------------


@dataclass
class HybridLogicalTimeSource:
    """Hybrid Logical Clock — wall time plus a monotone logical counter.

    HLC combines two pieces of information into each tick:

    * ``physical_ns`` — the backing wall-clock reading (from ``base`` Clock),
      floored so that two adjacent events with indistinguishable wall time
      still strictly order.
    * ``logical`` — monotone counter advanced whenever the physical side
      would otherwise produce equality.

    Guarantees (valid across multi-writer deployments where each writer
    holds its own instance seeded from a shared wall clock):

    * **Monotone**: ``tick`` values returned from one instance are
      strictly increasing.
    * **Causal**: ``observe(remote_ns, remote_logical)`` adopts the max
      of the local and remote readings, so an event seen on this node
      after it was observed elsewhere never orders before its cause.
    * **Deterministic under a FrozenClock**: the same ``(base, update
      sequence)`` yields the same ``tick`` sequence, which is what
      event-store replay needs.

    This is the primitive callers reach for when ordering across
    distributed writers matters (eg. cross-service event correlation).
    Local single-writer persistence continues to use ``Clock.epoch_ns``.
    """

    base: Clock = field(default_factory=SystemClock)
    _physical_ns: int = field(default=0, init=False, repr=False)
    _logical: int = field(default=0, init=False, repr=False)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False, compare=False)

    def tick(self) -> tuple[int, int]:
        """Generate the next HLC reading: ``(physical_ns, logical)``."""
        with self._lock:
            wall = self.base.epoch_ns()
            if wall > self._physical_ns:
                self._physical_ns = wall
                self._logical = 0
            else:
                self._logical += 1
            return self._physical_ns, self._logical

    def observe(self, remote_physical_ns: int, remote_logical: int) -> tuple[int, int]:
        """Merge a remote HLC reading into the local clock and emit the next tick.

        Preserves causality: a tick emitted after ``observe`` strictly
        dominates both the local and remote readings that preceded it.
        """
        with self._lock:
            wall = self.base.epoch_ns()
            max_physical = max(wall, self._physical_ns, remote_physical_ns)
            if max_physical == self._physical_ns == remote_physical_ns:
                self._logical = max(self._logical, remote_logical) + 1
            elif max_physical == self._physical_ns:
                self._logical += 1
            elif max_physical == remote_physical_ns:
                self._logical = remote_logical + 1
            else:  # wall dominates
                self._logical = 0
            self._physical_ns = max_physical
            return self._physical_ns, self._logical

    def snapshot(self) -> tuple[int, int]:
        """Return the current ``(physical_ns, logical)`` without advancing."""
        with self._lock:
            return self._physical_ns, self._logical
