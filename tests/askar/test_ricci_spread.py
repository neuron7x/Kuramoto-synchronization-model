"""Tests for the Askar Ricci Spread pair-trading study.

Required test checklist (6/6):
 1. no-lookahead in quintile positioning
 2. XAUUSD bad pre-2017 dates filtered
 3. timestamp alignment correct across SPY / GOLD / USA500
 4. Ricci spread values physically plausible (not all zeros)
 5. permutation test returns p > 0.20 on random signal
 6. result JSON contains IC_delta_vs_baseline
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from research.askar.ricci_spread import (
    DATA_DIR,
    RESULTS_DIR,
    THRESHOLD,
    WINDOW,
    forman_ricci_per_asset,
    load_askar,
    load_prices,
    permutation_test,
    quintile_position,
    z_score,
)

# ---------------------------------------------------------------- #
# 1. No-lookahead in expanding-window quintile positioning
# ---------------------------------------------------------------- #


def test_no_lookahead_quintile() -> None:
    """Position at bar t must depend only on signal[:t]."""
    rng = np.random.default_rng(0)
    base = pd.Series(rng.normal(size=500))

    pos_full = quintile_position(base, min_history=50)

    # Perturb bar 300 and ensure positions [0..299] are unchanged.
    perturbed = base.copy()
    perturbed.iloc[300:] += 1e6  # huge future perturbation
    pos_perturbed = quintile_position(perturbed, min_history=50)

    pd.testing.assert_series_equal(pos_full.iloc[:300], pos_perturbed.iloc[:300], check_names=False)


# ---------------------------------------------------------------- #
# 2. XAUUSD bad pre-2017 dates filtered
# ---------------------------------------------------------------- #


def test_xauusd_bad_dates_filtered() -> None:
    path = DATA_DIR / "XAUUSD_GMT_0_NO-DST.parquet"
    if not path.exists():
        pytest.skip("Askar XAUUSD data not staged in data/askar/")
    s = load_askar(path)
    assert s.index.min() >= pd.Timestamp("2017-01-01")


# ---------------------------------------------------------------- #
# 3. Timestamp alignment correct
# ---------------------------------------------------------------- #


def test_timestamp_alignment_correct() -> None:
    if not (DATA_DIR / "XAUUSD_GMT_0_NO-DST.parquet").exists():
        pytest.skip("Askar data not staged")
    prices = load_prices()
    assert list(prices.columns) == ["SPY", "GOLD", "USA500"]
    assert not prices.isnull().any().any()
    assert prices.index.is_monotonic_increasing
    assert prices.index.is_unique
    # All three series share the exact same index after .dropna()
    assert len(prices) > 0


# ---------------------------------------------------------------- #
# 4. Ricci spread values physically plausible
# ---------------------------------------------------------------- #


def test_ricci_spread_range() -> None:
    rng = np.random.default_rng(7)
    data = pd.DataFrame(rng.normal(size=(WINDOW, 3)), columns=["SPY", "GOLD", "USA500"])
    # Inject real correlation between SPY and USA500 to create edge variation.
    data["USA500"] = 0.8 * data["SPY"] + 0.2 * data["USA500"]

    per_asset, _ = forman_ricci_per_asset(data, THRESHOLD)
    assert set(per_asset.keys()) == {"SPY", "GOLD", "USA500"}

    values = list(per_asset.values())
    # For a 3-node graph, deg in {0,1,2}, so Ric_F(e) = 4 - d(u) - d(v) ∈ [0, 4]
    for v in values:
        assert -4.0 <= v <= 4.0
    # At least one non-zero value (since we injected correlation)
    assert any(abs(v) > 1e-9 for v in values)


# ---------------------------------------------------------------- #
# 5. Permutation test: random signal gives p > 0.20
# ---------------------------------------------------------------- #


def test_permutation_null_on_random() -> None:
    rng = np.random.default_rng(123)
    n = 1500
    signal = pd.Series(rng.normal(size=n))
    fwd = pd.Series(rng.normal(size=n))
    _ic, p = permutation_test(signal, fwd, n=300, seed=123)
    assert p > 0.20, f"random signal gave suspiciously low p={p:.3f}"


# ---------------------------------------------------------------- #
# 6. Result JSON contains IC_delta_vs_baseline
# ---------------------------------------------------------------- #


def test_ic_delta_reported() -> None:
    out = RESULTS_DIR / "askar_ricci_spread_result.json"
    if not out.exists():
        pytest.skip("result file not yet produced; run research/askar/ricci_spread.py")
    with out.open() as f:
        report = json.load(f)
    # Report is a dict-of-pairs. Every pair must carry the required keys.
    assert "primary_SPY_vs_GOLD" in report
    assert "alt_SPY_vs_USA500" in report
    assert "equity_curve_png" in report
    for pair_key in ("primary_SPY_vs_GOLD", "alt_SPY_vs_USA500"):
        block = report[pair_key]
        for key in (
            "IC_test",
            "IC_baseline_no_spread",
            "IC_delta_vs_baseline",
            "permutation_p",
            "test_sharpe",
            "verdict",
        ):
            assert key in block, f"missing key in {pair_key}: {key}"
        # Delta consistency
        assert (
            abs(block["IC_delta_vs_baseline"] - (block["IC_test"] - block["IC_baseline_no_spread"]))
            < 1e-6
        )


# ---------------------------------------------------------------- #
# Sanity: z_score behaves correctly
# ---------------------------------------------------------------- #


def test_z_score_basic() -> None:
    s = pd.Series(np.arange(200, dtype=float))
    z = z_score(s, 20)
    assert z.iloc[-1] == pytest.approx((199 - s.iloc[-20:].mean()) / s.iloc[-20:].std(), rel=1e-3)
