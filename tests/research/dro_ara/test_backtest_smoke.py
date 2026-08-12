# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Smoke tests for the DRO-ARA purged walk-forward backtest harness."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from scripts.research.dro_ara_backtest import (
    _multiplier,
    backtest_symbol,
    build_positions,
    run,
    walk_forward,
)

SEED = 42


def _ou(seed: int, n: int) -> NDArray[np.float64]:
    rng = np.random.default_rng(seed)
    x = np.empty(n, dtype=np.float64)
    x[0] = 100.0
    for t in range(1, n):
        x[t] = x[t - 1] + 0.08 * (100.0 - x[t - 1]) + 0.6 * rng.normal()
    return x


def _gbm(seed: int, n: int) -> NDArray[np.float64]:
    rng = np.random.default_rng(seed)
    r = 0.002 + 0.01 * rng.normal(size=n)
    return 100.0 * np.exp(np.cumsum(r))


def test_multiplier_invalid_and_drift_are_zero() -> None:
    assert _multiplier("INVALID", "STABLE") == 0.0
    assert _multiplier("DRIFT", "CONVERGING") == 0.0


def test_multiplier_critical_converging_is_one() -> None:
    assert _multiplier("CRITICAL", "CONVERGING") == 1.0
    assert _multiplier("CRITICAL", "STABLE") == 1.0


def test_multiplier_transition_is_half() -> None:
    assert _multiplier("TRANSITION", "STABLE") == 0.5


def test_positions_no_lookahead_prefix_is_flat() -> None:
    price = _ou(SEED, 2000)
    positions = build_positions(price, window=512, step=64, momentum_lag=24)
    assert np.all(positions[: 512 + 64] == 0)


def test_positions_values_in_expected_range() -> None:
    price = _ou(SEED, 2000)
    positions = build_positions(price, window=512, step=64, momentum_lag=24)
    assert set(np.unique(positions).tolist()) <= {-1, 0, 1}


def test_backtest_symbol_schema() -> None:
    price = _ou(SEED, 2000)
    bt = backtest_symbol(price, window=512, step=64, momentum_lag=24, cost_bp=1.0)
    assert set(bt.keys()) == {"positions", "pnl_gross", "pnl_net", "turnover"}
    assert bt["pnl_gross"].shape == bt["pnl_net"].shape
    assert np.all(np.isfinite(bt["pnl_net"]))


def test_backtest_on_gbm_has_flat_and_active_bars_mix() -> None:
    """GBM with drift: filter admits TRANSITION/CRITICAL, zeroes DRIFT.

    Post-PR #345 RFC: ADF on returns, so GBM is no longer uniformly INVALID.
    Finite-sample H on GBM-drift clusters near 0.5 → regime distribution
    lands in {TRANSITION ≈ 67 %, CRITICAL ≈ 17 %, DRIFT ≈ 17 %, INVALID ≈ 0 %}.
    The filter still protects by zeroing DRIFT/INVALID (~17 % of windows),
    producing an expected flat-bar fraction > 10 % on the active timeline.
    """
    price = _gbm(SEED, 2000)
    positions = build_positions(price, window=512, step=64, momentum_lag=24)
    active_timeline = positions[512 + 64 :]
    flat_bars = int(np.sum(active_timeline == 0))
    flat_frac = flat_bars / max(len(active_timeline), 1)
    assert (
        flat_frac >= 0.10
    ), f"Filter must zero some GBM bars (DRIFT path), got flat_frac={flat_frac:.3f}"
    assert set(np.unique(positions).tolist()) <= {-1, 0, 1}


def test_walk_forward_on_synthetic_panel() -> None:
    panel = pd.DataFrame(
        {
            "SYN_OU": _ou(1, 3000),
            "SYN_GBM": _gbm(2, 3000),
        }
    )
    out = walk_forward(
        panel,
        symbols=("SYN_OU", "SYN_GBM"),
        k=3,
        window=512,
        step=64,
        momentum_lag=24,
        cost_bp=1.0,
        max_bars=None,
    )
    assert "per_symbol" in out and "pooled" in out
    assert "aggregate_sharpe" in out["pooled"] or "note" in out["pooled"]


def test_run_writes_payload(tmp_path: Path) -> None:
    panel = pd.DataFrame({"SYN_OU": _ou(SEED, 3000)})
    panel_path = tmp_path / "panel.parquet"
    panel.to_parquet(panel_path)
    out_path = tmp_path / "bt.json"

    payload = run(
        panel_path=panel_path,
        symbols=("SYN_OU",),
        k=3,
        window=512,
        step=64,
        momentum_lag=24,
        cost_bp=1.0,
        max_bars=None,
        out_path=out_path,
    )
    assert out_path.exists()
    on_disk = json.loads(out_path.read_text())
    assert on_disk["spike_name"] == "dro_ara_backtest"
    assert "replay_hash_short" in on_disk
    assert len(on_disk["replay_hash_short"]) == 16
    assert payload["verdict"] in {"ACCEPT", "HEADROOM_ONLY", "ABORT"}


def test_zero_multiplier_forces_zero_pnl() -> None:
    """If every bar has regime INVALID, positions stay flat and PnL stays zero."""
    price = _gbm(SEED, 2000)
    bt = backtest_symbol(price, window=512, step=64, momentum_lag=24, cost_bp=1.0)
    positions = bt["positions"]
    if np.all(positions == 0):
        assert float(np.sum(bt["pnl_net"])) == 0.0


def test_determinism(tmp_path: Path) -> None:
    panel = pd.DataFrame({"SYN_OU": _ou(SEED, 3000)})
    panel_path = tmp_path / "panel.parquet"
    panel.to_parquet(panel_path)

    out1 = tmp_path / "bt1.json"
    out2 = tmp_path / "bt2.json"
    p1 = run(
        panel_path=panel_path,
        symbols=("SYN_OU",),
        k=3,
        window=512,
        step=64,
        momentum_lag=24,
        cost_bp=1.0,
        max_bars=None,
        out_path=out1,
    )
    p2 = run(
        panel_path=panel_path,
        symbols=("SYN_OU",),
        k=3,
        window=512,
        step=64,
        momentum_lag=24,
        cost_bp=1.0,
        max_bars=None,
        out_path=out2,
    )
    assert p1["replay_hash_short"] == p2["replay_hash_short"]


def test_cost_reduces_pnl() -> None:
    price = _ou(SEED, 2000)
    no_cost = backtest_symbol(price, window=512, step=64, momentum_lag=24, cost_bp=0.0)
    with_cost = backtest_symbol(price, window=512, step=64, momentum_lag=24, cost_bp=10.0)
    assert float(np.sum(with_cost["pnl_net"])) <= float(np.sum(no_cost["pnl_net"])) + 1e-12
