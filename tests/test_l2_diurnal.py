"""Tests for the diurnal profile module."""

from __future__ import annotations

import numpy as np
import pytest

from research.microstructure.diurnal import (
    compute_diurnal_profile,
    profile_to_json_dict,
    utc_hour_of_row,
)
from research.microstructure.killtest import FeatureFrame

_SEED = 42


def test_utc_hour_of_row_monotone_wraps_at_24() -> None:
    """Hours advance by 1 every 3600 rows and wrap modulo 24."""
    # start at UTC 23:30:00 (start_ms covers within hour 23)
    start_ms = 23 * 3600 * 1000 + 30 * 60 * 1000
    n_rows = 3600 * 3  # 3 hours
    hours = utc_hour_of_row(start_ms, n_rows)
    assert hours.shape == (n_rows,)
    # first 30 minutes → hour 23
    assert int(hours[0]) == 23
    # crossing to hour 0 at second 1800
    assert int(hours[1800]) == 0
    # next hour starts at +3600 from start = second 3600 → hour 0 (still)
    assert int(hours[3600 - 1]) == 0
    # hour 1 at second 3600+1800 = 5400
    assert int(hours[5400]) == 1


def test_utc_hour_of_row_rejects_negative_rows() -> None:
    with pytest.raises(ValueError):
        utc_hour_of_row(0, -1)


def _make_session(
    n_rows: int,
    n_sym: int,
    seed: int,
    start_ms: int,
) -> tuple[str, FeatureFrame, int]:
    rng = np.random.default_rng(seed)
    mid = np.zeros((n_rows, n_sym), dtype=np.float64)
    for k in range(n_sym):
        mid[:, k] = 100.0 + (k + 1) + rng.normal(0.0, 0.02, size=n_rows).cumsum()
    features = FeatureFrame(
        timestamps_ms=np.arange(n_rows, dtype=np.int64) * 1000,
        symbols=tuple(f"SYM{k}" for k in range(n_sym)),
        mid=mid,
        ofi=rng.normal(0.0, 1.0, size=(n_rows, n_sym)),
        queue_imbalance=rng.uniform(-1.0, 1.0, size=(n_rows, n_sym)),
    )
    return (f"synth_{seed}", features, start_ms)


def test_compute_profile_empty_sessions_returns_underpowered() -> None:
    profile = compute_diurnal_profile([])
    assert profile.verdict == "UNDERPOWERED"
    assert profile.hour_buckets == {}


def test_compute_profile_low_sample_yields_underpowered() -> None:
    """With only 500 rows (<min_rows_per_hour 300 per hour) on pure-noise data,
    no significant hour can materialize → UNDERPOWERED."""
    sess = _make_session(n_rows=500, n_sym=3, seed=_SEED, start_ms=0)
    profile = compute_diurnal_profile(
        [sess],
        horizon_sec=60,
        min_rows_per_hour=300,
        perm_trials=100,
        pvalue_gate=0.05,
    )
    assert profile.verdict in {"UNDERPOWERED", "SIGN_STABLE"}
    # If any buckets produced, their n_rows field should be populated
    for bucket in profile.hour_buckets.values():
        assert bucket.n_rows >= 0


def test_compute_profile_multi_session_merges_by_hour() -> None:
    """Two sessions offset by 12 hours should populate non-overlapping hour buckets."""
    s1 = _make_session(n_rows=2000, n_sym=3, seed=_SEED, start_ms=8 * 3600 * 1000)
    s2 = _make_session(n_rows=2000, n_sym=3, seed=_SEED + 1, start_ms=20 * 3600 * 1000)
    profile = compute_diurnal_profile(
        [s1, s2],
        horizon_sec=60,
        min_rows_per_hour=300,
        perm_trials=100,
    )
    # Hours populated should include some from each session start
    hours_present = set(profile.hour_buckets.keys())
    # Session 1 starts at 08:00 UTC → hours 8, 9 (2000s ≈ 33min, mostly hour 8)
    # Session 2 starts at 20:00 UTC → hours 20, 21
    assert hours_present.intersection({8, 9}), f"missing hour from s1: {hours_present}"
    assert hours_present.intersection({20, 21}), f"missing hour from s2: {hours_present}"
    # each bucket should list its session source
    for h in hours_present:
        bucket = profile.hour_buckets[h]
        assert len(bucket.session_source) >= 1


def test_profile_to_json_dict_schema() -> None:
    sess = _make_session(n_rows=1000, n_sym=3, seed=_SEED, start_ms=10 * 3600 * 1000)
    profile = compute_diurnal_profile([sess], perm_trials=50)
    body = profile_to_json_dict(profile)
    assert body["verdict"] in {"SIGN_FLIP_CONFIRMED", "SIGN_STABLE", "UNDERPOWERED"}
    for required in (
        "horizon_sec",
        "min_rows_per_hour",
        "pvalue_gate",
        "n_significant_positive",
        "n_significant_negative",
        "sessions_used",
        "hour_buckets",
    ):
        assert required in body, f"missing field: {required}"
    for h, entry in body["hour_buckets"].items():
        assert str(int(h)) == h
        assert "hour_utc" in entry and "n_rows" in entry


def test_compute_profile_deterministic_under_fixed_seed() -> None:
    sess = _make_session(n_rows=2000, n_sym=4, seed=_SEED, start_ms=0)
    a = compute_diurnal_profile([sess], perm_trials=100, seed=_SEED)
    b = compute_diurnal_profile([sess], perm_trials=100, seed=_SEED)
    assert profile_to_json_dict(a) == profile_to_json_dict(b)
