# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""FIX-3 contract: honest DP3 (snapshot-staleness) recovery test.

Falsification gate: a synthetic series whose final bar is exactly the
prior-mean (zero novel signal) MUST yield REJECT — confirming the test
correctly identifies mechanical-only ΔSharpe as null.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from geosync.dp3_test import _sharpe_annualised, evaluate


def test_sharpe_is_nan_on_zero_volatility() -> None:
    """`sd <= 0.0 or not isfinite(sd)` — either condition alone forces NaN.

    A constant return series has zero std, so the annualised Sharpe is undefined
    and must be NaN, not mu/0 -> ±inf. Under `Or->And` the `sd <= 0` branch no
    longer fires on its own (a finite zero is finite), leaking an infinite Sharpe
    into the permutation null.
    """
    constant_positive = np.full(8, 0.01, dtype=np.float64)
    assert np.isnan(_sharpe_annualised(constant_positive)), "zero-vol Sharpe must be NaN, not ±inf"


def _equity_csv_from_returns(target: Path, log_rets: np.ndarray) -> Path:
    """Build a paper-state equity.csv from a log-return series.

    Equity[0] = 1.0; equity[i] = exp(cumsum(log_rets[:i])).
    """
    n_bars = len(log_rets) + 1
    equity = np.concatenate([[1.0], np.exp(np.cumsum(log_rets))])
    rows = []
    start = date(2026, 4, 11)
    for i in range(n_bars):
        rows.append(
            {
                "day_n": i + 1,
                "date": (start + timedelta(days=i)).isoformat(),
                "regime": "high_sync",
                "R": 0.4,
                "net_ret": float(log_rets[i - 1]) if i > 0 else 0.0,
                "equity": float(equity[i]),
                "btc_equity": 1.0,
            }
        )
    pd.DataFrame(rows).to_csv(target, index=False, lineterminator="\n")
    return target


def test_zero_novel_signal_yields_reject(tmp_path: Path) -> None:
    """Final bar = prior mean → ΔSharpe ≈ mechanical floor → REJECT."""
    rng = np.random.default_rng(123)
    prior = rng.normal(loc=-0.005, scale=0.01, size=14)
    final_bar_zero_novel = float(prior.mean())  # adds the prior mean — no novelty
    full = np.append(prior, final_bar_zero_novel)
    eq = _equity_csv_from_returns(tmp_path / "equity.csv", full)
    r = evaluate(15, equity_path=eq, n_perm=999, seed=42)
    assert r.label == "REJECT", (
        f"FIX-3 VIOLATED: synthetic 'no novel signal' (last bar = "
        f"prior mean) should yield REJECT, got {r.label}. "
        f"delta={r.delta_observed:+.4f}, band={r.band:.4f}, "
        f"p={r.p_value:.4f}."
    )
    assert r.p_value > 0.05, (
        f"FIX-3 VIOLATED: p={r.p_value} unexpectedly small for "
        f"synthetic null. delta={r.delta_observed}, band={r.band}."
    )


def test_strong_novel_signal_yields_confirmed(tmp_path: Path) -> None:
    """Large-n prior + extreme outlier → ΔSharpe outside mechanical null → CONFIRMED.

    Construction: prior is n=200 i.i.d. normal(0, 0.005). At this n the
    bootstrap mechanical null is tight (~O(1/√n) Sharpe units). Final bar
    is a 50σ negative spike (-0.25). |observed Δ| dwarfs mechanical SD.
    """
    rng = np.random.default_rng(7)
    prior = rng.normal(loc=0.0, scale=0.005, size=200)
    final_bar = -0.25  # 50× prior std
    full = np.append(prior, final_bar)
    eq = _equity_csv_from_returns(tmp_path / "equity.csv", full)
    r = evaluate(201, equity_path=eq, n_perm=999, seed=42)
    assert r.label == "CONFIRMED", (
        f"FIX-3 VIOLATED: large-n prior + 50σ outlier should yield "
        f"CONFIRMED, got {r.label}. delta={r.delta_observed:+.4f}, "
        f"band={r.band:.4f}, p={r.p_value:.4f}."
    )
    assert r.p_value < 0.05, (
        f"FIX-3 VIOLATED: p={r.p_value} unexpectedly large for outlier "
        f"signal. delta={r.delta_observed}, band={r.band}."
    )


def test_label_is_strictly_binary(tmp_path: Path) -> None:
    """Labels must be REJECT or CONFIRMED — never AMBIGUOUS / PENDING / etc."""
    rng = np.random.default_rng(11)
    full = rng.normal(loc=0.0, scale=0.01, size=20)
    eq = _equity_csv_from_returns(tmp_path / "equity.csv", full)
    r = evaluate(20, equity_path=eq, n_perm=499, seed=42)
    assert r.label in {
        "REJECT",
        "CONFIRMED",
    }, f"FIX-3 VIOLATED: label must be strictly binary (REJECT or CONFIRMED), got {r.label!r}."


def test_too_few_returns_raises(tmp_path: Path) -> None:
    """Bar=2 → n_returns=1 → cannot run mechanical null → ValueError."""
    eq = _equity_csv_from_returns(tmp_path / "equity.csv", np.array([0.001, 0.001]))
    with pytest.raises(ValueError, match=r"requires >= 3 returns"):
        evaluate(2, equity_path=eq, n_perm=99, seed=42)


def test_missing_paper_state_raises(tmp_path: Path) -> None:
    """Absent paper-state ledger → FileNotFoundError, no silent default."""
    with pytest.raises(FileNotFoundError):
        evaluate(15, equity_path=tmp_path / "nonexistent.csv")
