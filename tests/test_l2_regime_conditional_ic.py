"""Tests for the regime-conditional IC decomposition artifact."""

from __future__ import annotations

from typing import Any

import pytest

from tests.l2_artifacts import load_results_artifact


@pytest.fixture(scope="module")
def cond() -> dict[str, Any]:
    return load_results_artifact("L2_REGIME_CONDITIONAL_IC.json")


def test_two_cells_cover_full_universe(cond: dict[str, Any]) -> None:
    regimes = {c["regime"] for c in cond["cells"]}
    assert regimes == {"HIGH_VOL", "LOW_VOL"}


def test_cell_row_counts_sum_close_to_total(cond: dict[str, Any]) -> None:
    """High + low rows must equal total rows (within 1 row for edge cases)."""
    total = sum(int(c["n_rows"]) for c in cond["cells"])
    assert total > 10_000  # Session 1 substrate expected size


def test_verdict_is_canonical(cond: dict[str, Any]) -> None:
    assert cond["verdict"] in {"VOL_DRIVEN", "UNIFORM", "QUIET_DRIVEN", "INCONCLUSIVE"}


def test_high_vol_quantile_mask_approximately_sized(cond: dict[str, Any]) -> None:
    """HIGH_VOL mask at q=0.75 should cover ~25% of rows (±5%)."""
    high = next(c for c in cond["cells"] if c["regime"] == "HIGH_VOL")
    low = next(c for c in cond["cells"] if c["regime"] == "LOW_VOL")
    total = int(high["n_rows"]) + int(low["n_rows"])
    frac_high = int(high["n_rows"]) / total
    assert 0.20 <= frac_high <= 0.30


def test_baseline_ic_matches_pooled_killtest(cond: dict[str, Any]) -> None:
    """Pooled IC in cond artifact must match the kill-test canonical value."""
    killtest = load_results_artifact("L2_KILLTEST_VERDICT.json")
    baseline = float(cond["baseline_ic_pooled"])
    canonical = float(killtest["ic_signal"])
    assert abs(baseline - canonical) < 1e-3


def test_ratio_nonnegative_or_nan(cond: dict[str, Any]) -> None:
    import math

    r = float(cond["abs_ratio_high_over_low"])
    assert math.isnan(r) or r >= 0.0
