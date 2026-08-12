"""Tests for the P&L module and break-even solver."""

from __future__ import annotations

import numpy as np
import pytest

from research.microstructure.pnl import (
    DEFAULT_DECISION_SEC,
    CostModel,
    GrossTrades,
    SweepRow,
    breakeven_maker_fraction,
    compute_strategy_stats,
    simulate_gross_trades,
    sweep_maker_fractions,
)

_SEED = 42


def test_cost_model_roundtrip_taker_only_matches_9p8bp() -> None:
    cm = CostModel()
    symbols = (
        "BTCUSDT",
        "ETHUSDT",
        "SOLUSDT",
        "BNBUSDT",
        "XRPUSDT",
        "ADAUSDT",
        "AVAXUSDT",
        "LINKUSDT",
        "DOTUSDT",
        "POLUSDT",
    )
    # 2× taker_fee (4bp) + 2× avg half-spread (0.9 bp: 2×0.5 + 8×1.0)/10
    rtc = cm.round_trip_cost_bp(symbols, maker_fraction=0.0)
    assert abs(rtc - 9.8) < 1e-9, f"expected 9.8, got {rtc}"


def test_cost_model_roundtrip_monotone_in_maker_fraction() -> None:
    cm = CostModel()
    symbols = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
    previous = cm.round_trip_cost_bp(symbols, maker_fraction=0.0)
    for mf in (0.25, 0.5, 0.75, 1.0):
        current = cm.round_trip_cost_bp(symbols, maker_fraction=mf)
        assert current < previous, f"non-monotone at mf={mf}: {current} >= {previous}"
        previous = current


def test_cost_model_rejects_bad_maker_fraction() -> None:
    cm = CostModel()
    for bad in (-0.1, 1.1, 2.0):
        with pytest.raises(ValueError):
            cm.round_trip_cost_bp(("BTCUSDT",), maker_fraction=bad)


def test_breakeven_solver_linear_interpolation() -> None:
    # Known bracket: maker_fraction 0.25 → -1.887, 0.50 → +1.113  → zero-crossing
    # t = (0 - (-1.887)) / (1.113 - (-1.887)) = 1.887 / 3.000 = 0.629
    # breakeven = 0.25 + 0.629 * (0.50 - 0.25) = 0.25 + 0.15725 = 0.40725
    rows = [
        SweepRow("X", 0.25, 6.8, 10, 0.5, -1.887, 0.0, 0.0, 0.0),
        SweepRow("X", 0.50, 3.8, 10, 0.5, 1.113, 0.0, 0.0, 0.0),
    ]
    be = breakeven_maker_fraction(rows)
    assert be is not None
    assert abs(be - 0.40725) < 1e-4, f"expected 0.40725, got {be}"


def test_breakeven_solver_no_bracket_returns_none() -> None:
    rows = [
        SweepRow("X", 0.0, 10.0, 5, 0.5, -5.0, 0.0, 0.0, 0.0),
        SweepRow("X", 0.5, 5.0, 5, 0.5, -2.0, 0.0, 0.0, 0.0),
    ]
    assert breakeven_maker_fraction(rows) is None


def _synthetic_trades(seed: int, n: int = 120) -> GrossTrades:
    rng = np.random.default_rng(seed)
    gross = rng.normal(loc=3.5, scale=15.0, size=n).astype(float).tolist()
    return GrossTrades(name="TEST_SYN", gross_bp=gross, n_gated_out=0)


def test_sweep_maker_monotone_in_sharpe_when_strategy_is_mean_positive() -> None:
    cm = CostModel()
    symbols = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
    trades = _synthetic_trades(seed=_SEED)
    rows = sweep_maker_fractions(
        trades,
        symbols=symbols,
        cost_model=cm,
        maker_fractions=(0.0, 0.25, 0.5, 0.75, 1.0),
    )
    sharpes = [r.sharpe_per_trade for r in rows]
    for i in range(len(sharpes) - 1):
        assert sharpes[i] < sharpes[i + 1], (
            f"sharpe should increase with maker_fraction: "
            f"[{i}]={sharpes[i]} vs [{i + 1}]={sharpes[i + 1]}"
        )


def test_simulate_gross_trades_deterministic_under_fixed_seed() -> None:
    """Same inputs → identical gross bp list (simulation has no randomness)."""
    rng = np.random.default_rng(_SEED)
    n_rows, n_sym = 2000, 4
    signal = rng.normal(0.0, 1.0, size=n_rows)
    log_mid_base = 100.0 + rng.normal(0.0, 0.01, size=n_rows).cumsum()
    mid = np.stack([log_mid_base + 0.1 * k for k in range(n_sym)], axis=1)
    decision_idx = np.arange(0, n_rows, 180, dtype=np.int64)
    a = simulate_gross_trades(
        signal,
        mid,
        decision_idx=decision_idx,
        hold_rows=180,
        median_window_rows=600,
        regime_mask=None,
    )
    b = simulate_gross_trades(
        signal,
        mid,
        decision_idx=decision_idx,
        hold_rows=180,
        median_window_rows=600,
        regime_mask=None,
    )
    assert a.gross_bp == b.gross_bp
    assert a.n_gated_out == b.n_gated_out


def test_simulate_regime_mask_reduces_trades_and_increases_gated() -> None:
    rng = np.random.default_rng(_SEED)
    n_rows, n_sym = 2000, 4
    signal = rng.normal(0.0, 1.0, size=n_rows)
    log_mid_base = 100.0 + rng.normal(0.0, 0.01, size=n_rows).cumsum()
    mid = np.stack([log_mid_base + 0.1 * k for k in range(n_sym)], axis=1)
    decision_idx = np.arange(0, n_rows, 180, dtype=np.int64)
    unmasked = simulate_gross_trades(
        signal,
        mid,
        decision_idx=decision_idx,
        hold_rows=180,
        median_window_rows=600,
        regime_mask=None,
    )
    # Turn mask on only at even-numbered 180-s boundaries
    # (= every other decision index), guaranteeing fewer trades.
    mask = np.zeros(n_rows, dtype=bool)
    mask[::360] = True
    masked = simulate_gross_trades(
        signal,
        mid,
        decision_idx=decision_idx,
        hold_rows=180,
        median_window_rows=600,
        regime_mask=mask,
    )
    assert len(masked.gross_bp) < len(unmasked.gross_bp)
    assert masked.n_gated_out > 0
    assert (
        masked.n_gated_out + len(masked.gross_bp) <= len(unmasked.gross_bp) + unmasked.n_gated_out
    )


def test_compute_stats_zero_trades_returns_nan() -> None:
    stats = compute_strategy_stats(
        GrossTrades(name="EMPTY", gross_bp=[], n_gated_out=0),
        cost_bp=9.8,
        decision_sec=DEFAULT_DECISION_SEC,
    )
    assert stats.n_trades == 0
    assert np.isnan(stats.sharpe_per_trade)
    assert np.isnan(stats.mean_return_net_bp)
    assert stats.cost_per_trade_bp == 9.8


def test_ic_to_gross_bp_sanity_scaling() -> None:
    """Scale sanity: with realized-return std ~20 bp over 180-s horizon,
    gross-per-trade magnitude on a random signal must stay O(std)."""
    rng = np.random.default_rng(_SEED)
    n_rows = 5000
    # per-second log-return increments sized so 180-sec cum std ≈ 20 bp
    inc = rng.normal(0.0, 1.0, size=n_rows) * (20.0 / np.sqrt(180.0)) * 1.0e-4
    log_mid_base = inc.cumsum()
    mid = np.exp(np.stack([log_mid_base, log_mid_base + 0.01], axis=1))
    signal = rng.normal(0.0, 1.0, size=n_rows)  # uncorrelated to prevent artefact
    decision_idx = np.arange(600, n_rows - 180, 180, dtype=np.int64)
    trades = simulate_gross_trades(
        signal,
        mid,
        decision_idx=decision_idx,
        hold_rows=180,
        median_window_rows=600,
        regime_mask=None,
    )
    arr = np.array(trades.gross_bp)
    assert arr.size > 5
    # Random signal on 20bp/180s substrate → |mean gross| well under 1 std of realized.
    assert abs(arr.mean()) < 20.0, f"gross mean {arr.mean()} exceeds plausible magnitude"
    # Individual trades should live in ±100 bp band (5× std headroom)
    assert np.max(np.abs(arr)) < 100.0, f"outlier trade magnitude {np.max(np.abs(arr))}"
