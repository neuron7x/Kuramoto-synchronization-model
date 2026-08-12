"""Tests for the diurnal-aware sign filter."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from research.microstructure.diurnal_filter import (
    DEFAULT_IC_GATE,
    DEFAULT_PVALUE_GATE,
    HourlyDirection,
    direction_per_row,
    load_hourly_direction_map,
    summarize_map,
)
from research.microstructure.pnl import GrossTrades, simulate_gross_trades


def _write_profile(tmp: Path, buckets: dict[str, dict[str, object]]) -> Path:
    """Helper: emit a minimal L2_DIURNAL_PROFILE.json with given buckets."""
    path = tmp / "profile.json"
    path.write_text(
        json.dumps(
            {
                "verdict": "SIGN_FLIP_CONFIRMED",
                "reasons": [],
                "horizon_sec": 180,
                "min_rows_per_hour": 300,
                "pvalue_gate": 0.05,
                "n_significant_positive": 1,
                "n_significant_negative": 1,
                "sessions_used": ["s1"],
                "hour_buckets": buckets,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_load_classifies_positive_significant_hour_as_plus_one(tmp_path: Path) -> None:
    profile = _write_profile(
        tmp_path,
        {
            "10": {
                "hour_utc": 10,
                "n_rows": 1000,
                "ic_signal": 0.12,
                "permutation_p": 0.002,
                "session_source": ["s1"],
            },
        },
    )
    m = load_hourly_direction_map(profile)
    assert m[10].direction == 1
    assert m[10].confidence == pytest.approx(0.12)


def test_load_classifies_negative_significant_hour_as_minus_one(tmp_path: Path) -> None:
    profile = _write_profile(
        tmp_path,
        {
            "22": {
                "hour_utc": 22,
                "n_rows": 1000,
                "ic_signal": -0.20,
                "permutation_p": 0.002,
                "session_source": ["s2"],
            },
        },
    )
    m = load_hourly_direction_map(profile)
    assert m[22].direction == -1
    assert m[22].confidence == pytest.approx(0.20)


def test_load_classifies_underpowered_hour_as_zero(tmp_path: Path) -> None:
    """Hour whose p-value exceeds the gate maps to direction=0 (flat)."""
    profile = _write_profile(
        tmp_path,
        {
            "20": {
                "hour_utc": 20,
                "n_rows": 500,
                "ic_signal": 0.15,
                "permutation_p": 0.95,
                "session_source": ["s1"],
            },
        },
    )
    m = load_hourly_direction_map(profile)
    assert m[20].direction == 0
    assert m[20].confidence == 0.0


def test_load_classifies_small_ic_as_zero(tmp_path: Path) -> None:
    """Significant but tiny IC (below ic_gate) maps to direction=0."""
    profile = _write_profile(
        tmp_path,
        {
            "09": {
                "hour_utc": 9,
                "n_rows": 5000,
                "ic_signal": 0.005,
                "permutation_p": 0.002,
                "session_source": ["s1"],
            },
        },
    )
    m = load_hourly_direction_map(profile)
    assert m[9].direction == 0


def test_load_handles_null_ic_or_null_p(tmp_path: Path) -> None:
    profile = _write_profile(
        tmp_path,
        {
            "05": {
                "hour_utc": 5,
                "n_rows": 0,
                "ic_signal": None,
                "permutation_p": None,
                "session_source": ["s3"],
            },
        },
    )
    m = load_hourly_direction_map(profile)
    assert m[5].direction == 0
    assert m[5].n_rows == 0


def test_load_rejects_malformed_profile_without_hour_buckets(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        load_hourly_direction_map(path)


def test_direction_per_row_fills_hours_correctly() -> None:
    """Direction array should carry each hour's assigned direction on the 1s grid."""
    # 8h → 9h → 10h: 3 hours, direction map assigns -1, 0, +1
    hourly_map = {
        8: HourlyDirection(8, -1, 0.15, n_rows=1000, ic_signal=-0.15, permutation_p=0.002),
        9: HourlyDirection(9, 0, 0.0, n_rows=1000, ic_signal=0.01, permutation_p=0.5),
        10: HourlyDirection(10, 1, 0.22, n_rows=1000, ic_signal=0.22, permutation_p=0.002),
    }
    start_ms = 8 * 3600 * 1000  # 08:00:00 UTC
    n_rows = 3 * 3600  # 3 hours
    direction = direction_per_row(hourly_map, start_ms=start_ms, n_rows=n_rows)
    # first 3600 rows in hour 8 → -1
    assert int(direction[0]) == -1
    assert int(direction[3599]) == -1
    # next 3600 in hour 9 → 0
    assert int(direction[3600]) == 0
    assert int(direction[7199]) == 0
    # final 3600 in hour 10 → +1
    assert int(direction[7200]) == 1
    assert int(direction[-1]) == 1


def test_direction_per_row_hours_not_in_map_default_to_zero() -> None:
    hourly_map = {
        10: HourlyDirection(10, 1, 0.2, n_rows=3600, ic_signal=0.2, permutation_p=0.002),
    }
    # start in hour 08; 4 hours of data
    direction = direction_per_row(hourly_map, start_ms=8 * 3600 * 1000, n_rows=4 * 3600)
    # hour 8 absent → 0
    assert int(direction[0]) == 0
    # hour 9 absent → 0
    assert int(direction[3600]) == 0
    # hour 10 present, direction +1
    assert int(direction[7200]) == 1
    # hour 11 absent → 0
    assert int(direction[10800]) == 0


def test_direction_per_row_rejects_negative_rows() -> None:
    with pytest.raises(ValueError):
        direction_per_row({}, start_ms=0, n_rows=-1)


def test_summarize_map_counts_correctly() -> None:
    m = {
        1: HourlyDirection(1, 1, 0.1, 1000, 0.1, 0.01),
        2: HourlyDirection(2, -1, 0.1, 1000, -0.1, 0.01),
        3: HourlyDirection(3, 0, 0.0, 100, 0.01, 0.5),
    }
    summary = summarize_map(m)
    assert summary == {"+1": 1, "-1": 1, "0": 1, "total": 3}


def test_pnl_direction_override_uses_map_not_median() -> None:
    """simulate_gross_trades with direction_override ignores rolling median."""
    rng = np.random.default_rng(42)
    n_rows = 2000
    signal = rng.normal(0.0, 1.0, size=n_rows)
    log_mid_base = 100.0 + rng.normal(0.0, 0.01, size=n_rows).cumsum()
    mid = np.stack([log_mid_base, log_mid_base + 0.1, log_mid_base + 0.2], axis=1)
    decision_idx = np.arange(600, n_rows, 180, dtype=np.int64)
    # All-minus-one direction override: every trade should be short
    override = -np.ones(n_rows, dtype=np.int64)
    # Force the default sign logic to go long: strictly ascending signal
    # means signal[i] > rolling_median(signal[:i]) everywhere past warmup.
    signal = np.arange(n_rows, dtype=np.float64)
    t_default = simulate_gross_trades(
        signal,
        mid,
        decision_idx=decision_idx,
        hold_rows=180,
        median_window_rows=600,
    )
    t_override = simulate_gross_trades(
        signal,
        mid,
        decision_idx=decision_idx,
        hold_rows=180,
        median_window_rows=600,
        direction_override=override,
    )
    # default basket-sign with all-above-median → all +1 long
    # override = -1 → all short; returns negated
    assert t_default.gross_bp, "default strategy should produce trades"
    for d, o in zip(t_default.gross_bp, t_override.gross_bp, strict=False):
        assert o == pytest.approx(-d)


def test_pnl_direction_override_zero_gates_trade() -> None:
    rng = np.random.default_rng(42)
    n_rows = 2000
    signal = rng.normal(0.0, 1.0, size=n_rows)
    mid = np.stack([100.0 + rng.normal(0.0, 0.01, size=n_rows).cumsum() for _ in range(2)], axis=1)
    decision_idx = np.arange(600, n_rows, 180, dtype=np.int64)
    # First half of rows forced to direction 0 (flat); decision indices in
    # first half are gated-out, those in second half trade long.
    override = np.where(np.arange(n_rows) >= n_rows // 2, 1, 0).astype(np.int64)
    t = simulate_gross_trades(
        signal,
        mid,
        decision_idx=decision_idx,
        hold_rows=180,
        median_window_rows=600,
        direction_override=override,
    )
    assert t.n_gated_out > 0
    for bp in t.gross_bp:
        assert np.isfinite(bp)


def test_pnl_direction_override_shape_validation() -> None:
    rng = np.random.default_rng(42)
    n_rows = 500
    signal = rng.normal(0.0, 1.0, size=n_rows)
    mid = np.stack([100.0 + rng.normal(0.0, 0.01, size=n_rows).cumsum()], axis=1)
    decision_idx = np.arange(0, n_rows, 180, dtype=np.int64)
    bad_override = np.ones(n_rows + 10, dtype=np.int64)
    with pytest.raises(ValueError):
        simulate_gross_trades(
            signal,
            mid,
            decision_idx=decision_idx,
            hold_rows=180,
            median_window_rows=300,
            direction_override=bad_override,
        )


def test_default_gate_constants_match_spine() -> None:
    """IC and p-value gate defaults must match killtest._IC_GATE / _PERM_PVALUE_GATE."""
    assert DEFAULT_IC_GATE == 0.03
    assert DEFAULT_PVALUE_GATE == 0.05


def test_grosstrades_dataclass_default_initialized() -> None:
    t = GrossTrades(name="X")
    assert t.gross_bp == []
    assert t.n_gated_out == 0
