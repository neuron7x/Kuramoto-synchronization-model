"""Tests for the hyperparameter ablation sweep artifact."""

from __future__ import annotations

from typing import Any

import pytest

from tests.l2_artifacts import load_results_artifact


@pytest.fixture(scope="module")
def ablation() -> dict[str, Any]:
    return load_results_artifact("L2_ABLATION_SENSITIVITY.json")


def test_every_cell_has_fields(ablation: dict[str, Any]) -> None:
    for cell in ablation["cells"]:
        assert "regime_quantile" in cell
        assert "regime_window_sec" in cell
        assert "breakeven_maker_fraction" in cell
        assert "bracketed" in cell


def test_canonical_cell_is_in_grid(ablation: dict[str, Any]) -> None:
    cells = ablation["cells"]
    found = [
        c
        for c in cells
        if abs(float(c["regime_quantile"]) - 0.75) < 1e-9 and int(c["regime_window_sec"]) == 300
    ]
    assert len(found) == 1
    canonical_cell = found[0]
    assert canonical_cell["bracketed"] is True
    canonical_f = float(canonical_cell["breakeven_maker_fraction"])
    assert abs(canonical_f - float(ablation["canonical_breakeven"])) < 1e-6


def test_all_cells_are_economically_viable(ablation: dict[str, Any]) -> None:
    """Even under hyperparameter perturbation, every cell breaks even
    below the realistic production maker fill rate (≤ 0.70)."""
    for cell in ablation["cells"]:
        assert cell["bracketed"] is True, f"cell {cell} did not bracket"
        f_star = float(cell["breakeven_maker_fraction"])
        assert 0.0 <= f_star <= 0.70, f"cell {cell} outside viable band"


def test_verdict_one_of_canonical_set(ablation: dict[str, Any]) -> None:
    assert ablation["verdict"] in {"ROBUST", "MIXED", "SENSITIVE", "NO_BRACKET_FOUND"}


def test_n_cells_matches_grid_product(ablation: dict[str, Any]) -> None:
    """Grid of 3 quantiles × 3 windows = 9 cells."""
    assert int(ablation["n_cells"]) == 9
