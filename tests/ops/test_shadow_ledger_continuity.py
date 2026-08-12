# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""G1 ledger-continuity guard for the cross-asset Kuramoto shadow evaluator.

NON_PHYSICS: admissibility infrastructure (ACCEPTANCE_GATES.md G1
"daily run success rate = 100%"), not a registered physics invariant.

The live bar count must advance one evaluation at a time. A gap, a counter
reset, or a conflicting duplicate row means the bar count overstates the number
of actually-evaluated bars, so the 90-bar deployment verdict must fail closed.
These tests pin the guard against the exact failure modes observed in the live
ledger (a 15 -> 37 stall of 22 bars; conflicting duplicate appends).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

_EVAL = (
    Path(__file__).resolve().parents[2] / "scripts" / "evaluate_cross_asset_kuramoto_shadow.py"
)
_spec = importlib.util.spec_from_file_location("shadow_eval", _EVAL)
assert _spec is not None and _spec.loader is not None
ev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ev)


def _row(date: str, bar: int, **metrics: object) -> dict[str, object]:
    base: dict[str, object] = {c: "" for c in ev.SCOREBOARD_COLUMNS}
    base["eval_date"] = date
    base["live_bars_completed"] = bar
    base["sharpe_live"] = metrics.get("sharpe_live", 0.1)
    base["status_label"] = metrics.get("status_label", "WITHIN_EXPECTATION")
    return base


def _board(rows: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=list(ev.SCOREBOARD_COLUMNS))


def test_clean_daily_ledger_is_continuous() -> None:
    rows = [_row(f"2026-04-{10 + i:02d}", i + 1) for i in range(8)]
    ok, violations = ev.audit_ledger_continuity(_board(rows))
    assert ok is True, f"clean +1/day ledger flagged: {violations}"
    assert violations == []


def test_empty_ledger_is_vacuously_continuous() -> None:
    ok, violations = ev.audit_ledger_continuity(_board([]))
    assert ok is True
    assert violations == []


def test_multi_week_stall_is_flagged() -> None:
    # The live failure mode: bar count jumps 15 -> 37 with no evaluations between.
    rows = [_row("2026-05-06", 15), _row("2026-06-13", 37)]
    ok, violations = ev.audit_ledger_continuity(_board(rows))
    assert ok is False
    assert any("stall" in v and "37" in v for v in violations), violations


def test_counter_reset_is_flagged() -> None:
    rows = [_row("2026-04-21", 6), _row("2026-05-05", 3)]
    ok, violations = ev.audit_ledger_continuity(_board(rows))
    assert ok is False
    assert any("non-monotone" in v for v in violations), violations


def test_conflicting_duplicate_rows_flagged() -> None:
    # Same (date, bar) with different sharpe — a non-idempotent duplicate append.
    rows = [
        _row("2026-06-19", 42, sharpe_live=-3.7652),
        _row("2026-06-19", 42, sharpe_live=-4.1003),
    ]
    ok, violations = ev.audit_ledger_continuity(_board(rows))
    assert ok is False
    assert any("conflicting" in v for v in violations), violations


def test_small_catchup_within_step_is_tolerated() -> None:
    # A weekend/holiday catch-up of <= MAX_BAR_STEP is not a stall.
    rows = [_row("2026-04-20", 5), _row("2026-04-23", 5 + ev.MAX_BAR_STEP)]
    ok, violations = ev.audit_ledger_continuity(_board(rows))
    assert ok is True, violations


def test_gate_blocks_deployment_candidate_on_discontinuity() -> None:
    """Even a clean 90-bar run inside the envelope cannot deploy on a broken ledger."""
    metrics = {"max_dd_live": 0.0, "sharpe_live": 1.0}
    status, gate = ev._decide_status_and_gate(
        bars=90,
        metrics=metrics,
        env_pos="p25_p75",
        op_unsafe=False,
        inv_fail=False,
        sub_p05_streak=0,
        ledger_discontinuous=True,
    )
    assert status == "OPERATIONALLY_UNSAFE"
    assert gate == "ESCALATE_REVIEW"
    # Sanity: the same inputs with a continuous ledger DO reach the candidate.
    status_ok, gate_ok = ev._decide_status_and_gate(
        bars=90,
        metrics=metrics,
        env_pos="p25_p75",
        op_unsafe=False,
        inv_fail=False,
        sub_p05_streak=0,
        ledger_discontinuous=False,
    )
    assert gate_ok == "DEPLOYMENT_CANDIDATE_PENDING_OWNER"


@pytest.mark.parametrize("step", [1, 2, ev.MAX_BAR_STEP])
def test_advances_up_to_step_are_continuous(step: int) -> None:
    rows = [_row("2026-04-20", 10), _row("2026-04-21", 10 + step)]
    ok, _ = ev.audit_ledger_continuity(_board(rows))
    assert ok is True
