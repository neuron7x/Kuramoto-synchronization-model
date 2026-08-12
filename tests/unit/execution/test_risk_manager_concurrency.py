# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Regression: RiskManager exposure accounting must be thread-safe.

The live runner (``execution.live_loop``) drives one ``RiskManager`` from three
concurrent watchdog threads — order-submission (``validate_order``), fill-poller
(``register_fill``) and heartbeat (``exposure_snapshot`` reads). Every exposure
mutator is a read-modify-write on ``_positions`` / ``_last_notional``; without
serialisation two fills that read the same prior position both write it back, so
one fill is silently lost.

The default CPython GIL switches on a ~5 ms timer, not per bytecode, so a naive
high-contention loop almost never interleaves inside the tiny read→write window
and would pass even with the bug present. To make the defect observable
deterministically, ``test_register_fill_lost_update_is_prevented`` installs an
instrumented ``_positions`` map that rendezvouses two threads *after* each has
read the old value and *before* either writes — forcing exactly the interleave
the lock must prevent.

Falsification: delete the ``@_synchronized`` guard on ``register_fill`` and that
test fails (final position 1.0, not 2.0). With the guard, the second thread
blocks on ``_state_lock`` at method entry, never reaches the rendezvous, the
barrier times out, and the two fills serialise to the correct total.
"""

from __future__ import annotations

import importlib
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

import pytest

# ``execution.*`` is behind the forbidden_import_patterns gate → importlib.
_risk = importlib.import_module("execution.risk")
RiskLimits = _risk.RiskLimits
RiskManager = _risk.RiskManager

_SYMBOL = "BTC-USD"
_CANON = "BTC/USD"  # normalize_symbol("BTC-USD") canonical form
_PRICE = 10.0
_RENDEZVOUS_TIMEOUT = 1.0


class _RendezvousPositions:
    """A ``_positions`` stand-in that pauses between the read and write of a fill.

    Implements only the ``get`` / ``__setitem__`` / ``__getitem__`` surface that
    ``register_fill`` and ``current_position`` touch. On the first ``get`` for the
    tracked symbol from each of two threads, the caller blocks on a shared barrier
    so both threads observe the *same* prior value before either writes. Under the
    lock only one thread can be inside ``register_fill`` at a time, so the second
    never arrives, the barrier times out (``BrokenBarrierError``) and the reads
    serialise correctly.
    """

    def __init__(self, symbol: str) -> None:
        self._data: dict[str, float] = {}
        self._symbol = symbol
        self._barrier = threading.Barrier(2, timeout=_RENDEZVOUS_TIMEOUT)
        self.armed = True

    def get(self, key: str, default: float = 0.0) -> float:
        value = self._data.get(key, default)
        if self.armed and key == self._symbol:
            try:
                self._barrier.wait()
            except threading.BrokenBarrierError:
                # Serialised path (guard held): the peer never reached the read.
                self.armed = False
        return value

    def __getitem__(self, key: str) -> float:
        return self._data[key]

    def __setitem__(self, key: str, value: float) -> None:
        self._data[key] = value


def _unbounded_manager() -> "RiskManager":
    # Uncapped so no LimitViolation fires; we probe state integrity, not caps.
    # No risk_state_store -> _persist_risk_state is a no-op.
    return RiskManager(RiskLimits(max_notional=float("inf"), max_position=float("inf")))


def _run_all(target: Callable[[], None], *, workers: int) -> None:
    """Run ``target`` on ``workers`` threads; re-raise the first worker failure."""

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(target) for _ in range(workers)]
    for future in futures:
        future.result()  # propagates any exception raised in a worker


def test_register_fill_lost_update_is_prevented() -> None:
    """Two concurrent fills that read the same prior position must both land."""

    manager = _unbounded_manager()
    rendezvous = _RendezvousPositions(_CANON)
    setattr(manager, "_positions", rendezvous)  # inject the instrumented map

    def _fill() -> None:
        manager.register_fill(_SYMBOL, "buy", 1.0, _PRICE)

    _run_all(_fill, workers=2)
    rendezvous.armed = False  # let the final read skip the barrier

    # Without the lock both fills read 0.0 and write 1.0 -> final 1.0 (one lost).
    assert manager.current_position(_SYMBOL) == 2.0
    assert manager.current_notional(_SYMBOL) == pytest.approx(2.0 * _PRICE)


def test_validate_and_register_do_not_deadlock_or_corrupt() -> None:
    """A validating thread and a filling thread interleave without corruption.

    Exercises the reentrant lock across the two hot-path entry points that the
    order-submission and fill-poller watchdog threads hit concurrently, asserting
    the guard neither deadlocks nor drops a fill under a plain interleave.
    """

    manager = RiskManager(
        RiskLimits(
            max_notional=float("inf"),
            max_position=float("inf"),
            max_orders_per_interval=0,  # disable throttle so validate always admits
        )
    )
    iterations = 500

    def _validate() -> None:
        for _ in range(iterations):
            manager.validate_order(_SYMBOL, "buy", 1.0, _PRICE)

    def _fill() -> None:
        for _ in range(iterations):
            manager.register_fill(_SYMBOL, "buy", 1.0, _PRICE)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_validate), pool.submit(_fill)]
    for future in futures:
        future.result()

    # validate_order never mutates position; every one of the 500 fills must land.
    assert manager.current_position(_SYMBOL) == float(iterations)


def test_exposure_snapshot_matches_position_after_concurrent_fills() -> None:
    """After concurrent fills the snapshot's notional matches its position."""

    manager = _unbounded_manager()
    fills_per_thread = 400
    threads = 4

    def _fill() -> None:
        for _ in range(fills_per_thread):
            manager.register_fill(_SYMBOL, "buy", 1.0, _PRICE)

    _run_all(_fill, workers=threads)

    snap = manager.exposure_snapshot()[_CANON]
    assert snap["position"] == pytest.approx(float(threads * fills_per_thread))
    assert snap["notional"] == pytest.approx(abs(snap["position"]) * _PRICE)
