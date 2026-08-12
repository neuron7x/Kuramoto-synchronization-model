"""Tests for the Betti-1 topology signal."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from research.askar.betti_topology import (
    EXTENDED_PANEL_PATH,
    VERDICT_PATH,
    _lead_capture,
    _permutation_pvalue,
    _scorr,
    compute_betti1,
    run,
)

# ---------------------------------------------------------------- #
# 1. B₁ = 0 on a fully disconnected graph (no edges, k = V)
# ---------------------------------------------------------------- #


def test_b1_zero_for_disconnected_graph() -> None:
    # Uncorrelated white noise with a high threshold → no edges at all
    # → E = 0, k = V → B₁ = 0 − V + V = 0.
    rng = np.random.default_rng(0)
    n, k = 200, 6
    returns = pd.DataFrame(
        rng.normal(size=(n, k)) * 0.01,
        index=pd.date_range("2020-01-01", periods=n, freq="h"),
        columns=[f"A{i}" for i in range(k)],
    )
    # Threshold 0.99 → virtually no edges on white noise
    b1 = compute_betti1(returns, window=60, threshold=0.99)
    tail = b1.dropna()
    assert len(tail) > 100
    assert float(tail.max()) == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------- #
# 2. B₁ = (V−1)·(V−2)/2 on the complete graph K_V (all edges active, k=1)
# ---------------------------------------------------------------- #


def test_b1_positive_for_complete_graph() -> None:
    # Force a complete graph by making every asset identical up to sign.
    # For perfectly correlated returns (|corr|=1 > 0.30), adj is K_V.
    # On K_V: E = V(V−1)/2, k = 1, V = n → B₁ = V(V−1)/2 − V + 1
    #                                       = (V−1)(V−2)/2
    n, k = 120, 5
    rng = np.random.default_rng(1)
    base = rng.normal(size=n)
    returns = pd.DataFrame(
        {f"A{i}": base * (1.0 + 0.001 * i) for i in range(k)},
        index=pd.date_range("2020-01-01", periods=n, freq="h"),
    )
    b1 = compute_betti1(returns, window=60, threshold=0.30)
    expected = (k - 1) * (k - 2) / 2.0  # = 6 on 5 nodes
    tail = b1.dropna()
    assert len(tail) > 50
    assert float(tail.iloc[-1]) == pytest.approx(expected, abs=1e-9)


# ---------------------------------------------------------------- #
# 3. Series has the expected shape and every finite value is ≥ 0
# ---------------------------------------------------------------- #


def test_b1_series_shape_and_finite() -> None:
    rng = np.random.default_rng(3)
    n, k = 300, 8
    returns = pd.DataFrame(
        rng.normal(size=(n, k)) * 0.005,
        index=pd.date_range("2020-01-01", periods=n, freq="h"),
        columns=[f"A{i}" for i in range(k)],
    )
    b1 = compute_betti1(returns, window=60, threshold=0.30)
    assert len(b1) == n
    # First (window - 1) = 59 bars are warmup NaN; first emitted value at t=59.
    assert b1.iloc[:59].isna().all()
    assert np.isfinite(b1.iloc[59])
    finite = b1.dropna()
    assert np.isfinite(finite.to_numpy()).all()
    # B₁ ≥ 0 by topological definition on the 1-skeleton.
    assert (finite >= 0.0).all()


# ---------------------------------------------------------------- #
# 4. Small primitive tests (permutation p, scorr, lead_capture)
# ---------------------------------------------------------------- #


def test_scorr_returns_finite_or_zero() -> None:
    rng = np.random.default_rng(4)
    idx = pd.date_range("2020-01-01", periods=200, freq="h")
    a = pd.Series(rng.normal(size=200), index=idx)
    b = pd.Series(rng.normal(size=200), index=idx)
    val = _scorr(a, b)
    assert abs(val) < 0.5


def test_permutation_p_under_random_null() -> None:
    rng = np.random.default_rng(5)
    n = 400
    idx = pd.date_range("2020-01-01", periods=n, freq="h")
    x = pd.Series(rng.normal(size=n), index=idx)
    y = pd.Series(rng.normal(size=n), index=idx)
    p = _permutation_pvalue(x, y, permutations=200, seed=5)
    assert 0.0 <= p <= 1.0
    assert p > 0.10


def test_lead_capture_handles_zero_events() -> None:
    idx = pd.date_range("2020-01-01", periods=100, freq="h")
    b1 = pd.Series(np.arange(100, dtype=float), index=idx)
    fwd = pd.Series(np.zeros(100, dtype=float), index=idx)  # no drawdowns
    capture, captured, events = _lead_capture(b1, fwd, threshold=-0.05)
    assert capture == 0.0
    assert captured == 0
    assert events == 0


# ---------------------------------------------------------------- #
# 5. End-to-end: the run() builds a well-formed verdict file
# ---------------------------------------------------------------- #


def test_run_produces_verdict_when_panel_present() -> None:
    if not EXTENDED_PANEL_PATH.exists():
        pytest.skip("extended panel not staged")
    run()
    assert VERDICT_PATH.exists()
    verdict = json.loads(Path(VERDICT_PATH).read_text())
    required = {
        "substrate",
        "IC",
        "p_value",
        "corr_momentum",
        "corr_vol",
        "corr_vix",
        "corr_hyg",
        "lead_capture",
        "DETECT",
        "DISCRIMINATE",
        "DELIVER",
        "FINAL",
    }
    missing = required - set(verdict.keys())
    assert not missing, f"missing keys: {missing}"
    assert verdict["FINAL"] in {"SIGNAL_READY", "REJECT"}
    for d in ("DETECT", "DISCRIMINATE", "DELIVER"):
        assert verdict[d] in {"PASS", "FAIL"}
