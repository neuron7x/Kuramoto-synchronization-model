# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Regression: RiskManager must count pending (reserved-but-unfilled) exposure.

Before this contract, ``validate_order`` checked the cap against *filled* exposure
only. Two orders each individually below the cap could both pass because neither
reserved anything until its fill registered — the reservation-lag bypass flagged
as the residual of the RiskManager lock fix. These tests pin the lifecycle:

    validate(reserve) -> hold pending
    register_fill(reservation_id) -> convert filled qty to actual (partial ok)
    release_reservation -> discharge remainder on reject/cancel/timeout

Falsification: drop the pending term from the cap check (or stop reserving) and
``test_combined_pending_exceeds_cap_second_rejects`` fails — the second order is
admitted and aggregate exposure exceeds the cap.
"""

from __future__ import annotations

import importlib

import pytest

# ``execution.*`` is behind the forbidden_import_patterns gate → importlib.
_risk = importlib.import_module("execution.risk")
RiskLimits = _risk.RiskLimits
RiskManager = _risk.RiskManager
LimitViolation = _risk.LimitViolation

_SYMBOL = "BTC-USD"
_CANON = "BTC/USD"


def _manager(max_position: float = 5.0, max_notional: float = float("inf")) -> "RiskManager":
    return RiskManager(RiskLimits(max_position=max_position, max_notional=max_notional))


def test_reserve_holds_pending_without_touching_actual() -> None:
    mgr = _manager()
    mgr.validate_order(_SYMBOL, "buy", 3.0, 10.0, reserve=True, reservation_id="r1")

    assert mgr.current_position(_SYMBOL) == 0.0  # nothing filled yet
    assert mgr.pending_position(_SYMBOL) == pytest.approx(3.0)
    assert mgr.pending_notional(_SYMBOL) == pytest.approx(30.0)
    assert mgr.open_reservation_count() == 1


def test_combined_pending_exceeds_cap_second_rejects() -> None:
    """Two orders each <= cap but jointly above it: the second must reject."""

    mgr = _manager(max_position=5.0)
    mgr.validate_order(_SYMBOL, "buy", 3.0, 10.0, reserve=True, reservation_id="r1")

    with pytest.raises(LimitViolation):
        mgr.validate_order(_SYMBOL, "buy", 3.0, 10.0, reserve=True, reservation_id="r2")

    # The rejected order left no hold behind.
    assert mgr.pending_position(_SYMBOL) == pytest.approx(3.0)
    assert mgr.open_reservation_count() == 1


def test_cancel_releases_reservation_and_unblocks_next() -> None:
    mgr = _manager(max_position=5.0)
    mgr.validate_order(_SYMBOL, "buy", 3.0, 10.0, reserve=True, reservation_id="r1")
    mgr.release_reservation("r1")

    assert mgr.pending_position(_SYMBOL) == 0.0
    assert mgr.open_reservation_count() == 0
    # Freed capacity: a second 3-lot order now fits under the 5 cap.
    mgr.validate_order(_SYMBOL, "buy", 3.0, 10.0, reserve=True, reservation_id="r2")
    assert mgr.pending_position(_SYMBOL) == pytest.approx(3.0)


def test_release_reservation_is_idempotent() -> None:
    mgr = _manager()
    mgr.validate_order(_SYMBOL, "buy", 2.0, 10.0, reserve=True, reservation_id="r1")
    mgr.release_reservation("r1")
    mgr.release_reservation("r1")  # no-op, no negative pending
    mgr.release_reservation("unknown")  # no-op
    assert mgr.pending_position(_SYMBOL) == 0.0
    assert mgr.open_reservation_count() == 0


def test_full_fill_converts_pending_to_actual_no_double_count() -> None:
    mgr = _manager()
    mgr.validate_order(_SYMBOL, "buy", 3.0, 10.0, reserve=True, reservation_id="r1")
    mgr.register_fill(_SYMBOL, "buy", 3.0, 10.0, reservation_id="r1")

    assert mgr.current_position(_SYMBOL) == pytest.approx(3.0)
    assert mgr.pending_position(_SYMBOL) == 0.0  # hold discharged, not added twice
    assert mgr.open_reservation_count() == 0


def test_partial_fill_converts_only_filled_amount() -> None:
    mgr = _manager(max_position=10.0)
    mgr.validate_order(_SYMBOL, "buy", 4.0, 10.0, reserve=True, reservation_id="r1")
    mgr.register_fill(_SYMBOL, "buy", 1.5, 10.0, reservation_id="r1")

    assert mgr.current_position(_SYMBOL) == pytest.approx(1.5)  # only filled part
    assert mgr.pending_position(_SYMBOL) == pytest.approx(2.5)  # remainder still held
    assert mgr.open_reservation_count() == 1
    # Total exposure (actual + pending) is conserved across the convert.
    snap = mgr.exposure_snapshot(include_pending=True)[_CANON]
    assert snap["total_position"] == pytest.approx(4.0)


def test_rejected_order_reserves_nothing() -> None:
    mgr = _manager(max_position=2.0)
    with pytest.raises(LimitViolation):
        mgr.validate_order(_SYMBOL, "buy", 5.0, 10.0, reserve=True, reservation_id="r1")
    assert mgr.pending_position(_SYMBOL) == 0.0
    assert mgr.open_reservation_count() == 0


def test_reserve_requires_fresh_reservation_id() -> None:
    mgr = _manager()
    with pytest.raises(ValueError):
        mgr.validate_order(_SYMBOL, "buy", 1.0, 10.0, reserve=True)  # id missing
    mgr.validate_order(_SYMBOL, "buy", 1.0, 10.0, reserve=True, reservation_id="r1")
    with pytest.raises(ValueError):
        # duplicate id would silently overwrite an outstanding hold
        mgr.validate_order(_SYMBOL, "buy", 1.0, 10.0, reserve=True, reservation_id="r1")


def test_fill_after_release_is_reconciled_explicitly() -> None:
    """A late fill whose reservation was released still updates actual exposure.

    Timeout/stale path: the hold is released first; a subsequent fill for that id
    finds no reservation and falls back to the legacy actual-only update rather
    than resurrecting pending — no negative pending, no silent drop.
    """

    mgr = _manager(max_position=10.0)
    mgr.validate_order(_SYMBOL, "buy", 3.0, 10.0, reserve=True, reservation_id="r1")
    mgr.release_reservation("r1")
    mgr.register_fill(_SYMBOL, "buy", 3.0, 10.0, reservation_id="r1")

    assert mgr.current_position(_SYMBOL) == pytest.approx(3.0)
    assert mgr.pending_position(_SYMBOL) == 0.0
    assert mgr.open_reservation_count() == 0


def test_legacy_register_fill_ignores_pending() -> None:
    """register_fill without a reservation_id keeps the pre-reservation behaviour."""

    mgr = _manager()
    mgr.register_fill(_SYMBOL, "buy", 2.0, 10.0)
    assert mgr.current_position(_SYMBOL) == pytest.approx(2.0)
    assert mgr.pending_position(_SYMBOL) == 0.0
    # Default snapshot shape is unchanged for legacy callers.
    assert mgr.exposure_snapshot() == {_CANON: {"position": 2.0, "notional": 20.0}}


def test_snapshot_include_pending_exposes_actual_pending_total() -> None:
    mgr = _manager(max_position=10.0)
    mgr.register_fill(_SYMBOL, "buy", 2.0, 10.0)  # actual = 2
    mgr.validate_order(_SYMBOL, "buy", 3.0, 10.0, reserve=True, reservation_id="r1")

    snap = mgr.exposure_snapshot(include_pending=True)[_CANON]
    assert snap["position"] == pytest.approx(2.0)
    assert snap["pending_position"] == pytest.approx(3.0)
    assert snap["total_position"] == pytest.approx(5.0)
    assert snap["total_notional"] == pytest.approx(snap["notional"] + snap["pending_notional"])
