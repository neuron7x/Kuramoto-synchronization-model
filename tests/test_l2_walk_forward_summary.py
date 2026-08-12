"""Tests for walk-forward temporal-stability summary."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from research.microstructure.walk_forward import (
    WalkForwardSummary,
    summarize_walk_forward,
)


def _write(tmp: Path, payload: dict[str, object]) -> Path:
    p = tmp / "wf.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_summary_stable_positive_when_majority_pos_and_median_above_0p05(tmp_path: Path) -> None:
    rows = [{"ic_signal": 0.10 + 0.01 * (i % 3), "perm_p": 0.01} for i in range(30)]
    rows += [{"ic_signal": -0.02, "perm_p": 0.5} for _ in range(5)]  # 85.7% positive
    path = _write(tmp_path, {"rows": rows, "window_sec": 2400, "step_sec": 300})
    r = summarize_walk_forward(path)
    assert isinstance(r, WalkForwardSummary)
    assert r.verdict == "STABLE_POSITIVE"
    assert r.fraction_positive > 0.70
    assert r.ic_median > 0.05


def test_summary_mixed_when_positive_fraction_between_50_and_70(tmp_path: Path) -> None:
    rows = [{"ic_signal": 0.01, "perm_p": 0.3} for _ in range(12)]  # positive but small median
    rows += [{"ic_signal": -0.03, "perm_p": 0.3} for _ in range(8)]  # 60% positive
    path = _write(tmp_path, {"rows": rows, "window_sec": 2400, "step_sec": 300})
    r = summarize_walk_forward(path)
    assert r.verdict == "MIXED"
    assert 0.50 <= r.fraction_positive < 0.70


def test_summary_unstable_when_minority_positive(tmp_path: Path) -> None:
    rows = [{"ic_signal": -0.08, "perm_p": 0.05} for _ in range(15)]
    rows += [{"ic_signal": 0.04, "perm_p": 0.2} for _ in range(5)]  # 25% positive
    path = _write(tmp_path, {"rows": rows, "window_sec": 2400, "step_sec": 300})
    r = summarize_walk_forward(path)
    assert r.verdict == "UNSTABLE"
    assert r.fraction_positive < 0.50


def test_summary_handles_missing_and_null_entries(tmp_path: Path) -> None:
    rows = [
        {"ic_signal": 0.15, "perm_p": 0.01},
        {"ic_signal": None, "perm_p": None},
        {"ic_signal": 0.12, "perm_p": 0.02},
        {},  # completely missing
    ]
    path = _write(tmp_path, {"rows": rows, "window_sec": 2400, "step_sec": 300})
    r = summarize_walk_forward(path)
    assert r.n_windows == 4
    assert r.n_valid == 2


def test_summary_empty_returns_inconclusive(tmp_path: Path) -> None:
    path = _write(tmp_path, {"rows": [], "window_sec": 2400, "step_sec": 300})
    r = summarize_walk_forward(path)
    assert r.verdict == "INCONCLUSIVE"
    assert r.n_valid == 0


def test_summary_schema_complete_on_happy_path(tmp_path: Path) -> None:
    rows = [{"ic_signal": 0.10, "perm_p": 0.02} for _ in range(10)]
    path = _write(tmp_path, {"rows": rows, "window_sec": 2400, "step_sec": 300})
    r = summarize_walk_forward(path)
    for field in (
        r.ic_mean,
        r.ic_std,
        r.ic_median,
        r.ic_q25,
        r.ic_q75,
        r.ic_min,
        r.ic_max,
        r.fraction_positive,
        r.fraction_above_0p05,
        r.fraction_below_minus_0p05,
    ):
        assert isinstance(field, float)


def test_summary_matches_session1_artifact() -> None:
    """Regression against the live Session 1 walk-forward data."""
    artifact = Path("results/L2_WALK_FORWARD.json")
    if not artifact.exists():
        pytest.skip("Session 1 walk-forward artifact not present")
    r = summarize_walk_forward(artifact)
    assert r.n_valid >= 30
    assert r.verdict == "STABLE_POSITIVE"
    assert r.fraction_positive > 0.70
