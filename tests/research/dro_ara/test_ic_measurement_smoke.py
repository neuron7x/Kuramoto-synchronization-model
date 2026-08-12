# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Smoke tests for the DRO-ARA IC measurement harness.

These tests keep the script honest (no silent code drift) without invoking
external data loading in CI. They exercise each internal helper deterministically
on a synthetic OU + GBM mixture so that pooled IC is always measurable.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts.research.dro_ara_ic_fx import (
    IC_GATE,
    _bootstrap_ic,
    _observe_at,
    _signed_signal,
    _spearman_ic,
    build_verdict,
    measure_symbol,
    pool_symbols,
    run,
)

SEED = 42


def _ou(
    seed: int, n: int, mu: float = 100.0, theta: float = 0.08, sigma: float = 0.6
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    x = np.empty(n, dtype=np.float64)
    x[0] = mu
    for t in range(1, n):
        x[t] = x[t - 1] + theta * (mu - x[t - 1]) + sigma * rng.normal()
    return x


def _gbm(seed: int, n: int, mu: float = 0.0005, sigma: float = 0.01) -> np.ndarray:
    rng = np.random.default_rng(seed)
    r = mu + sigma * rng.normal(size=n)
    return 100.0 * np.exp(np.cumsum(r))


def test_signed_signal_positive_when_mean_reverting() -> None:
    out = {"H": 0.2, "risk_scalar": 0.8, "regime": "CRITICAL"}
    assert _signed_signal(out) > 0.0


def test_signed_signal_negative_when_persistent() -> None:
    out = {"H": 0.8, "risk_scalar": 0.8, "regime": "DRIFT"}
    assert _signed_signal(out) < 0.0


def test_signed_signal_zero_when_rs_zero() -> None:
    out = {"H": 0.3, "risk_scalar": 0.0, "regime": "INVALID"}
    assert _signed_signal(out) == 0.0


def test_observe_at_rejects_anchor_below_minimum() -> None:
    price = _ou(SEED, 2048)
    assert _observe_at(price, anchor=10, window=512, step=64) is None


def test_observe_at_returns_state_at_valid_anchor() -> None:
    price = _ou(SEED, 2048)
    out = _observe_at(price, anchor=1024, window=512, step=64)
    assert out is not None
    assert "regime" in out and "H" in out and "risk_scalar" in out


def test_spearman_ic_perfect_rank() -> None:
    f = np.arange(100, dtype=np.float64)
    r = 2.0 * f + 3.0
    assert _spearman_ic(f, r) == pytest.approx(1.0)


def test_bootstrap_ic_returns_three_floats() -> None:
    rng = np.random.default_rng(1)
    f = rng.normal(size=500)
    r = 0.1 * f + rng.normal(size=500)
    med, lo, hi = _bootstrap_ic(f, r, n_boot=200, seed=1)
    assert np.isfinite(med) and np.isfinite(lo) and np.isfinite(hi)
    assert lo <= med <= hi


def test_measure_symbol_on_ou_produces_signals() -> None:
    price = _ou(SEED, 3072)
    result = measure_symbol(price, horizons=(1, 4, 24), window=512, step=64)
    assert result["n_signals"] >= 20
    assert "horizons" in result


def test_pool_symbols_on_synthetic_panel(tmp_path: Path) -> None:
    panel = pd.DataFrame(
        {
            "SYN_OU": _ou(1, 3072),
            "SYN_GBM": _gbm(2, 3072),
        }
    )
    out = pool_symbols(
        panel=panel,
        symbols=("SYN_OU", "SYN_GBM"),
        horizons=(1, 4, 24),
        window=512,
        step=64,
        max_bars=None,
    )
    assert set(out.keys()) == {"per_symbol", "pooled"}
    assert "h4" in out["pooled"]


def test_build_verdict_headroom_when_no_gate_passes() -> None:
    pooled = {
        "h1": {
            "ic_boot_median": 0.02,
            "ic_ci95_low": -0.01,
            "ic_ci95_high": 0.05,
            "n": 500,
            "passes_gate": False,
        }
    }
    verdict, reason, best = build_verdict(pooled)
    assert verdict == "HEADROOM_ONLY"
    assert "FAIL" in reason
    assert best["best_horizon"] == "h1"


def test_build_verdict_abort_when_no_valid_horizon() -> None:
    verdict, reason, _ = build_verdict({"h1": {"ic_boot_median": float("nan")}})
    assert verdict == "ABORT"


def test_run_writes_payload(tmp_path: Path) -> None:
    panel = pd.DataFrame({"SYN_OU": _ou(SEED, 3072)})
    panel_path = tmp_path / "panel.parquet"
    panel.to_parquet(panel_path)
    out_path = tmp_path / "ic.json"

    payload = run(
        panel_path=panel_path,
        symbols=("SYN_OU",),
        horizons=(1, 4, 24),
        window=512,
        step=64,
        max_bars=None,
        out_path=out_path,
    )
    assert out_path.exists()
    on_disk = json.loads(out_path.read_text())
    assert on_disk["spike_name"] == "dro_ara_ic_fx"
    assert on_disk["ic_gate"] == IC_GATE
    assert "replay_hash" in on_disk
    assert payload["replay_hash"] == on_disk["replay_hash"]
