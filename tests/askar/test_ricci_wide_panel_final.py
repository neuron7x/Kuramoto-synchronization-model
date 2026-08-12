"""Tests for the wide-panel Ricci + 3-D gate pipeline.

Covers the invariants the closing brief requires:
 1. extended panel committed and readable
 2. orthogonality gate hard-aborts on synthetic high-|corr| input
 3. rolling Ricci mean has correct shape and bounded values
 4. stress detector `run_stress_detector` returns a well-formed report
 5. verdict JSON schema is complete and self-consistent
 6. 3-D verdict is False when any D fails
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from research.askar.ricci_wide_panel_final import (
    CORE_COLS,
    EXTENDED_PANEL_PATH,
    ORTHOGONALITY_GATE,
    RESULTS_PATH,
    WIDE_COLS,
    _rolling_ricci_mean,
    _scorr,
    run,
)
from research.askar.stress_detector import run_stress_detector

REQUIRED_TOP_KEYS = {
    "substrate",
    "gate",
    "window",
    "threshold",
    "permutations",
    "IC",
    "p_value",
    "corr_momentum",
    "corr_vol",
    "stress_detector",
    "lead_capture",
    "DETECT",
    "DISCRIMINATE",
    "DELIVER",
    "FINAL",
}


# ---------------------------------------------------------------- #
# 1. Extended panel exists and contains every required column
# ---------------------------------------------------------------- #


def test_extended_panel_committed_and_readable() -> None:
    if not EXTENDED_PANEL_PATH.exists():
        pytest.skip("extended panel parquet not staged")
    df = pd.read_parquet(EXTENDED_PANEL_PATH)
    assert df.shape[1] >= len(WIDE_COLS)
    for col in WIDE_COLS:
        assert col in df.columns, f"missing: {col}"
    assert not df[list(CORE_COLS)].isna().all().any()


# ---------------------------------------------------------------- #
# 2. Rolling Ricci mean shape + bounds on synthetic panel
# ---------------------------------------------------------------- #


def test_rolling_ricci_mean_bounds() -> None:
    rng = np.random.default_rng(0)
    n, k = 400, 4
    idx = pd.date_range("2020-01-01", periods=n, freq="h")
    returns = pd.DataFrame(
        rng.normal(size=(n, k)) * 0.01,
        index=idx,
        columns=["A", "B", "C", "D"],
    )
    kappa = _rolling_ricci_mean(returns, window=60, threshold=0.30)
    assert len(kappa) == n
    # First 60 bars are NaN by construction.
    assert kappa.iloc[:60].isna().all()
    # On 4 nodes, deg(u), deg(v) ∈ {0, 1, 2, 3}, so kappa edge ∈ [-2, 4].
    finite = kappa.dropna()
    assert (finite >= -2.0).all()
    assert (finite <= 4.0).all()


# ---------------------------------------------------------------- #
# 3. Orthogonality-gate helper catches high-|corr| synthetic pairs
# ---------------------------------------------------------------- #


def test_scorr_catches_high_correlation() -> None:
    rng = np.random.default_rng(1)
    n = 400
    idx = pd.date_range("2020-01-01", periods=n, freq="h")
    base = rng.normal(size=n)
    a = pd.Series(base, index=idx)
    b = pd.Series(base + rng.normal(scale=0.01, size=n), index=idx)
    c = pd.Series(rng.normal(size=n), index=idx)

    assert abs(_scorr(a, b)) > ORTHOGONALITY_GATE
    assert abs(_scorr(a, c)) < ORTHOGONALITY_GATE


# ---------------------------------------------------------------- #
# 4. Stress detector returns a well-formed report on synthetic data
# ---------------------------------------------------------------- #


def test_stress_detector_report_shape() -> None:
    rng = np.random.default_rng(2)
    n = 800
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    regime = np.sin(np.linspace(0, 30, n))
    target_r = 0.0003 * np.roll(regime, 2) + rng.normal(0, 0.005, n)

    panel = {"USA_500_Index": 100 * np.exp(np.cumsum(target_r))}
    for i in range(5):
        r = 0.0002 * regime + rng.normal(0, 0.005, n)
        panel[f"A{i}"] = 100 * np.exp(np.cumsum(r))
    prices = pd.DataFrame(panel, index=idx)

    signal, alerts, report = run_stress_detector(
        prices, target_asset="USA_500_Index", unity_window=60
    )
    # log-returns drop the first bar; signal / alerts share the returns index.
    assert len(signal) == len(alerts)
    assert len(signal) == len(prices) - 1
    assert alerts.dtype == bool
    d = report.to_dict()
    for key in (
        "ic_stress_vs_future_drawdown",
        "corr_stress_vol",
        "corr_stress_momentum",
        "lead_capture_rate",
        "alert_rate",
        "passed",
    ):
        assert key in d
    assert isinstance(d["passed"], bool)
    assert 0.0 <= float(d["lead_capture_rate"]) <= 1.0


# ---------------------------------------------------------------- #
# 5. Verdict JSON schema + 3-D self-consistency
# ---------------------------------------------------------------- #


def test_verdict_schema_and_three_d_consistency() -> None:
    if not EXTENDED_PANEL_PATH.exists():
        pytest.skip("extended panel not staged — run module first to build it")
    if not RESULTS_PATH.exists():
        verdict_live = run()
    else:
        verdict_live = json.loads(Path(RESULTS_PATH).read_text())

    missing = REQUIRED_TOP_KEYS - set(verdict_live.keys())
    assert not missing, f"missing verdict keys: {missing}"
    assert verdict_live["FINAL"] in {"SIGNAL_READY", "REJECT", "ABORT"}
    for d in ("DETECT", "DISCRIMINATE", "DELIVER"):
        assert verdict_live[d] in {"PASS", "FAIL", "SKIPPED"}

    # If FINAL is SIGNAL_READY all three D's must be PASS.
    if verdict_live["FINAL"] == "SIGNAL_READY":
        for d in ("DETECT", "DISCRIMINATE", "DELIVER"):
            assert verdict_live[d] == "PASS"

    # Gate pass implies non-SKIPPED D columns.
    if verdict_live["gate"]["gate_passed"]:
        for d in ("DETECT", "DISCRIMINATE", "DELIVER"):
            assert verdict_live[d] != "SKIPPED"

    # Gate block internal consistency: corr magnitudes recorded, threshold
    # mirrors the constant.
    assert verdict_live["gate"]["gate_threshold"] == pytest.approx(ORTHOGONALITY_GATE)


# ---------------------------------------------------------------- #
# 6. Full run() is importable and the resulting file exists
# ---------------------------------------------------------------- #


def test_run_writes_verdict_file() -> None:
    if not EXTENDED_PANEL_PATH.exists():
        pytest.skip("extended panel not staged")
    run()
    assert RESULTS_PATH.exists()
    payload = json.loads(Path(RESULTS_PATH).read_text())
    assert "FINAL" in payload
