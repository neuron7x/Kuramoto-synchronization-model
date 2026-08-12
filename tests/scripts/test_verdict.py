# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""FIX-4 contract: CI-aware verdict on the live Sharpe trajectory.

Falsification gate (FIX-4): given known true_sharpe and n bars, the CI must
(i) be wider than the threshold gap when n is small, AND (ii) contract
monotonically as n grows. Verdict labels AMBIGUOUS when CI crosses any
nominal threshold.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from geosync.verdict import THRESHOLDS, _crosses_threshold, _sharpe_annualised, evaluate


def test_sharpe_is_nan_on_zero_volatility() -> None:
    """`sd <= 0.0 or not isfinite(sd)` — either condition alone forces NaN.

    A constant return series has zero std, so the Sharpe is undefined and must be
    NaN, not a division by zero. Under `Or->And` the `sd <= 0` branch no longer
    fires on its own (a finite zero is finite), so mu/0.0 returns +inf instead.
    """
    constant_positive = np.full(8, 0.01, dtype=np.float64)
    assert np.isnan(_sharpe_annualised(constant_positive)), "zero-vol Sharpe must be NaN, not ±inf"


def test_crosses_threshold_false_when_an_endpoint_is_not_finite() -> None:
    """`isfinite(low) and isfinite(high)` — BOTH endpoints must be finite.

    A non-finite band endpoint means the crossing test is undefined and must
    return False (no crossing claimed). Under `And->Or` a single finite endpoint
    would satisfy the guard, then `low < b < inf` could spuriously report a cross.
    """
    lowest_boundary = min(t for _, t in THRESHOLDS)
    assert _crosses_threshold(lowest_boundary - 1.0, float("inf")) is False
    assert _crosses_threshold(float("-inf"), lowest_boundary + 1.0) is False


def _synthetic_equity_csv(
    target: Path,
    *,
    n_bars: int,
    daily_drift: float,
    daily_vol: float,
    seed: int,
) -> Path:
    """Build a synthetic paper-state equity.csv with the canonical columns."""
    rng = np.random.default_rng(seed)
    log_rets = rng.normal(loc=daily_drift, scale=daily_vol, size=n_bars - 1)
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


def test_ci_brackets_point_estimate(tmp_path: Path) -> None:
    """CI must envelope the point Sharpe estimate (sanity)."""
    eq = _synthetic_equity_csv(
        tmp_path / "equity.csv",
        n_bars=120,
        daily_drift=0.0,
        daily_vol=0.01,
        seed=1,
    )
    v = evaluate(120, equity_path=eq, n_paths=499, seed=42)
    assert np.isfinite(v.sharpe_point), f"point Sharpe NaN: {v}"
    assert v.ci_low <= v.sharpe_point <= v.ci_high or abs(v.ci_high - v.ci_low) > 0.01, (
        f"FIX-4 VIOLATED: CI [{v.ci_low}, {v.ci_high}] does not bracket "
        f"point Sharpe {v.sharpe_point}. Verdict: {v}."
    )


def test_ci_contracts_with_more_bars(tmp_path: Path) -> None:
    """CI width should be (much) wider at n=20 than at n=200 for same DGP."""
    eq = _synthetic_equity_csv(
        tmp_path / "equity.csv",
        n_bars=210,
        daily_drift=0.0,
        daily_vol=0.01,
        seed=7,
    )
    v_short = evaluate(20, equity_path=eq, n_paths=499, seed=42)
    v_long = evaluate(200, equity_path=eq, n_paths=499, seed=42)
    width_short = v_short.ci_high - v_short.ci_low
    width_long = v_long.ci_high - v_long.ci_low
    assert width_short > width_long, (
        f"FIX-4 VIOLATED: CI width did not contract with sample size. "
        f"short(n=20)={width_short:.3f}, long(n=200)={width_long:.3f}."
    )
    assert width_short > 1.0, (
        f"FIX-4 VIOLATED: CI on n=20 is suspiciously narrow ({width_short:.3f}); "
        f"sub-1.0 width at small-n means underdispersion / bootstrap collapse."
    )


def test_ambiguous_when_ci_spans_threshold(tmp_path: Path) -> None:
    """At very small n the CI must span thresholds → AMBIGUOUS, not point label."""
    eq = _synthetic_equity_csv(
        tmp_path / "equity.csv",
        n_bars=18,
        daily_drift=-0.005,
        daily_vol=0.02,
        seed=3,
    )
    v = evaluate(15, equity_path=eq, n_paths=499, seed=42)
    boundaries = [t for _, t in THRESHOLDS]
    crosses = any(v.ci_low < b < v.ci_high for b in boundaries)
    assert v.crosses_threshold == crosses, (
        f"FIX-4 VIOLATED: crosses_threshold flag inconsistent with CI vs boundaries. "
        f"flag={v.crosses_threshold}, derived={crosses}, "
        f"CI=[{v.ci_low}, {v.ci_high}], boundaries={boundaries}."
    )
    if v.crosses_threshold:
        assert v.label == "AMBIGUOUS", (
            f"FIX-4 VIOLATED: CI crosses a threshold but label is "
            f"{v.label!r}, expected 'AMBIGUOUS'. Verdict: {v}."
        )


def test_unambiguous_when_ci_narrow(tmp_path: Path) -> None:
    """With many bars and a clear positive Sharpe, CI should NOT cross 0 → RECOVERING."""
    eq = _synthetic_equity_csv(
        tmp_path / "equity.csv",
        n_bars=400,
        daily_drift=0.005,
        daily_vol=0.005,
        seed=11,
    )
    v = evaluate(400, equity_path=eq, n_paths=499, seed=42)
    assert v.label != "AMBIGUOUS", (
        f"FIX-4 VIOLATED: with strong positive drift over 400 bars the CI "
        f"should not cross zero, but verdict is AMBIGUOUS. {v}."
    )
    assert (
        v.label == "RECOVERING"
    ), f"FIX-4 VIOLATED: expected RECOVERING for sharpe>0, got {v.label}. {v}."


def test_missing_paper_state_raises(tmp_path: Path) -> None:
    """Absent paper-state ledger → FileNotFoundError, no silent default."""
    with pytest.raises(FileNotFoundError):
        evaluate(15, equity_path=tmp_path / "nonexistent.csv")
