"""Tests for the hold-time ablation artifact."""

from __future__ import annotations

from typing import Any

import pytest

from tests.l2_artifacts import load_results_artifact


@pytest.fixture(scope="module")
def ablation() -> dict[str, Any]:
    return load_results_artifact("L2_HOLD_ABLATION.json")


def test_canonical_hold_in_grid(ablation: dict[str, Any]) -> None:
    canonical = int(ablation["canonical_hold_sec"])
    cells = ablation["cells"]
    found = [c for c in cells if int(c["hold_sec"]) == canonical]
    assert len(found) == 1


def test_every_cell_is_viable(ablation: dict[str, Any]) -> None:
    """Every hold-time cell either brackets or is already profitable at f=0."""
    unviable = [c for c in ablation["cells"] if c["status"] == "UNVIABLE"]
    assert not unviable, f"unviable cells: {unviable}"


def test_cells_per_status_sum_to_total(ablation: dict[str, Any]) -> None:
    n_bracketed = int(ablation["n_bracketed"])
    n_already = int(ablation["n_already_profitable"])
    n_cells = int(ablation["n_cells"])
    assert n_bracketed + n_already <= n_cells  # UNVIABLE is residual
    assert int(ablation["n_viable"]) == n_bracketed + n_already


def test_verdict_is_canonical(ablation: dict[str, Any]) -> None:
    assert ablation["verdict"] in {"ROBUST", "MIXED", "COLLAPSING"}


def test_bracketed_cells_have_numeric_breakeven(ablation: dict[str, Any]) -> None:
    for cell in ablation["cells"]:
        if cell["status"] == "BRACKET":
            assert cell["bracketed"] is True
            assert cell["breakeven_maker_fraction"] is not None
            assert 0.0 <= float(cell["breakeven_maker_fraction"]) <= 1.0


def test_already_profitable_cells_have_positive_f0_bp(ablation: dict[str, Any]) -> None:
    for cell in ablation["cells"]:
        if cell["status"] == "ALREADY_PROFITABLE":
            assert cell["profitable_at_f0"] is True
            assert float(cell["mean_net_bp_at_f0"]) > 0.0
            assert cell["breakeven_maker_fraction"] is None


def test_max_breakeven_within_robust_ceiling(ablation: dict[str, Any]) -> None:
    """Any bracketed cell must break even below the robust threshold 0.50."""
    if int(ablation["n_bracketed"]) > 0:
        assert float(ablation["max_breakeven"]) <= 0.50
