"""Tests for the slippage stress-test artifact."""

from __future__ import annotations

from itertools import pairwise
from typing import Any

import pytest

from tests.l2_artifacts import load_results_artifact


@pytest.fixture(scope="module")
def stress() -> dict[str, Any]:
    return load_results_artifact("L2_SLIPPAGE_STRESS.json")


def test_baseline_cell_brackets_at_canonical_gate(stress: dict[str, Any]) -> None:
    """Δ=0 slippage must reproduce the canonical gate fixture (f* = 0.23167)."""
    zero_cells = [c for c in stress["cells"] if float(c["slippage_bp"]) == 0.0]
    assert len(zero_cells) == 1
    cell = zero_cells[0]
    assert cell["status"] == "BRACKET"
    assert abs(float(cell["breakeven_maker_fraction"]) - 0.23167) < 1e-3


def test_rtc_increases_monotonically_with_slippage(stress: dict[str, Any]) -> None:
    """Adding slippage bp must strictly increase round-trip cost."""
    cells = sorted(stress["cells"], key=lambda c: float(c["slippage_bp"]))
    rtcs = [float(c["total_rtc_at_f0_bp"]) for c in cells]
    diffs = [b - a for a, b in pairwise(rtcs)]
    assert all(d > 0 for d in diffs), f"RTC not monotone: {rtcs}"


def test_breakeven_rises_monotonically_with_slippage(stress: dict[str, Any]) -> None:
    """Higher slippage → higher break-even maker fraction (when bracketed)."""
    bracketed = [c for c in stress["cells"] if c["status"] == "BRACKET"]
    bracketed.sort(key=lambda c: float(c["slippage_bp"]))
    fs = [float(c["breakeven_maker_fraction"]) for c in bracketed]
    diffs = [b - a for a, b in pairwise(fs)]
    assert all(d > 0 for d in diffs), f"break-even not monotone in slippage: {fs}"


def test_verdict_is_canonical(stress: dict[str, Any]) -> None:
    assert stress["verdict"] in {"RESILIENT", "BOUND", "FRAGILE"}


def test_baseline_must_be_viable(stress: dict[str, Any]) -> None:
    """Canonical zero-slippage cell must at minimum bracket or be profitable."""
    zero_cells = [c for c in stress["cells"] if float(c["slippage_bp"]) == 0.0]
    assert zero_cells[0]["status"] in {"BRACKET", "ALREADY_PROFITABLE"}


def test_max_viable_slippage_nonnegative(stress: dict[str, Any]) -> None:
    assert float(stress["max_slippage_still_viable_bp"]) >= 0.0
