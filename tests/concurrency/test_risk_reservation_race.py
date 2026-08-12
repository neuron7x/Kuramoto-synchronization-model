# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Deterministic race: pending reservations close the cap-bypass window.

Two watchdog-style threads each submit an order that is individually within the
position cap but jointly above it. ``validate_order`` holds ``_state_lock`` and
reserves admitted exposure atomically, so the second thread — whichever loses the
race for the lock — observes the first thread's pending hold and is rejected. The
outcome is deterministic on the *count*: exactly one admission, exactly one
``LimitViolation``, regardless of which thread wins.

Falsification: stop counting pending in the cap check (or stop reserving) and both
threads read a zero prior position, both pass, and the assertion of "exactly one
admission" fails — the reservation-lag bypass is back.
"""

from __future__ import annotations

import importlib
from concurrent.futures import ThreadPoolExecutor

# ``execution.*`` is behind the forbidden_import_patterns gate → importlib.
_risk = importlib.import_module("execution.risk")
RiskLimits = _risk.RiskLimits
RiskManager = _risk.RiskManager
LimitViolation = _risk.LimitViolation

_SYMBOL = "BTC-USD"
_CANON = "BTC/USD"


def _admit(manager: "RiskManager", reservation_id: str) -> str:
    """Attempt an admission; return 'admitted' or 'rejected'."""

    try:
        manager.validate_order(
            _SYMBOL, "buy", 3.0, 10.0, reserve=True, reservation_id=reservation_id
        )
    except LimitViolation:
        return "rejected"
    return "admitted"


def test_two_concurrent_orders_below_cap_but_combined_above_cannot_both_pass() -> None:
    # cap 5, two orders of 3 each: one fits, two do not.
    manager = RiskManager(RiskLimits(max_position=5.0, max_notional=float("inf")))

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_admit, manager, f"r{i}") for i in range(2)]
    outcomes = sorted(f.result() for f in futures)

    assert outcomes == ["admitted", "rejected"], outcomes
    # Exactly one hold survived; aggregate pending never exceeded the cap.
    assert manager.pending_position(_SYMBOL) == 3.0
    assert manager.open_reservation_count() == 1


def test_many_concurrent_orders_admit_only_up_to_cap() -> None:
    """Eight threads race for a cap of 5 lots of 1: exactly five may be admitted."""

    manager = RiskManager(RiskLimits(max_position=5.0, max_notional=float("inf")))

    def _admit_one(reservation_id: str) -> str:
        try:
            manager.validate_order(
                _SYMBOL, "buy", 1.0, 10.0, reserve=True, reservation_id=reservation_id
            )
        except LimitViolation:
            return "rejected"
        return "admitted"

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(_admit_one, f"r{i}") for i in range(8)]
    outcomes = [f.result() for f in futures]

    assert outcomes.count("admitted") == 5
    assert outcomes.count("rejected") == 3
    assert manager.pending_position(_SYMBOL) == 5.0
    assert manager.open_reservation_count() == 5
