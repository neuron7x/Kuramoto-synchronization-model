# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Regression: AtomicCapitalMover must never release a committed leg.

Bug: `execute` reserved all legs then committed them in a second loop; on ANY
exception `_rollback(legs)` called `gateway.release(...)` over ALL legs —
including ones already committed. A commit-phase failure after leg 0 settled thus
tried to reverse a settled transfer AND reported `committed=False`, so the caller
believed nothing happened while capital was actually imbalanced across venues.

Fix: roll back only the still-reserved (uncommitted) legs and surface the partial
(non-atomic) outcome (`partial=True`, `committed_legs`).

`execution.*` is behind the forbidden_import_patterns gate, so it is loaded via
importlib (repo-sanctioned pattern).
"""

from __future__ import annotations

import importlib
from datetime import datetime, timezone
from decimal import Decimal

import pytest

_arb = importlib.import_module("execution.arbitrage")
AtomicCapitalMover = _arb.AtomicCapitalMover
CapitalTransferPlan = _arb.CapitalTransferPlan


class _Gateway:
    """Records reserve/commit/release; commit can be forced to fail."""

    def __init__(self, *, fail_commit: bool = False) -> None:
        self.reservations: set[str] = set()
        self.committed: set[str] = set()
        self.released: set[str] = set()
        self._fail = fail_commit
        self._n = 0

    async def reserve(self, exchange_id: str, asset: str, amount: Decimal, transfer_id: str) -> str:
        token = f"{exchange_id}:{asset}:{self._n}"
        self._n += 1
        self.reservations.add(token)
        return token

    async def commit(self, token: str) -> None:
        if self._fail:
            raise RuntimeError("commit failure")
        self.committed.add(token)

    async def release(self, token: str) -> None:
        self.released.add(token)


def _plan() -> "CapitalTransferPlan":
    return CapitalTransferPlan(
        transfer_id="t",
        legs={("EX1", "USDT"): Decimal("1000"), ("EX2", "BTC"): Decimal("1")},
        initiated_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_partial_commit_does_not_release_committed_leg() -> None:
    ok = _Gateway()
    failing = _Gateway(fail_commit=True)
    mover = AtomicCapitalMover({"EX1": ok, "EX2": failing})

    result = await mover.execute(_plan())

    assert ok.committed, "EX1 leg should have committed"
    assert not ok.released, "a committed leg must NEVER be released on rollback"
    # The uncommitted EX2 reservation IS rolled back.
    assert failing.reservations == failing.released
    assert result.committed is False
    assert result.partial is True
    assert result.committed_legs == 1


@pytest.mark.asyncio
async def test_reserve_phase_failure_is_clean_not_partial() -> None:
    ok = _Gateway()
    mover = AtomicCapitalMover({"EX1": ok})  # no gateway for EX2 -> reserve-phase failure

    result = await mover.execute(_plan())

    assert result.committed is False
    assert result.partial is False
    assert result.committed_legs == 0
    assert ok.reservations == ok.released  # all (only EX1) rolled back
