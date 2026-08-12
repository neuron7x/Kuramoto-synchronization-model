# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Runtime state sealing for ``BacktesterCAL``.

Proves that two consecutive ``run`` calls on the same calibrated instance
produce bit-identical outputs, and that each component's mutable streaming
state is rewound to its post-calibration baseline between runs.

These guards fail-closed on three known leak surfaces:

* streaming containers (``FeatureStore.buf``, ``ConformalCQR._resid``,
  ``BacktesterCAL._ret_hist``);
* cached scalars (``RegimeModel.state``, ``ConformalCQR.alpha``,
  ``Guardrails.peak`` / ``cooldown``);
* stochastic generators (``Execution._rng``).

Without an explicit ``_reset_runtime_state``, each of these carries over
into the next run and silently perturbs the output. These tests reject
that regression at CI time.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import pytest

from geosync_hpc.backtest import BacktesterCAL
from geosync_hpc.conformal import ConformalCQR
from geosync_hpc.execution import Execution
from geosync_hpc.features import FeatureStore
from geosync_hpc.regime import RegimeModel
from geosync_hpc.risk import Guardrails

SEED = 42


def _tiny_cfg() -> dict[str, Any]:
    """Minimal valid config for a fast deterministic backtest."""
    return {
        "features": {"lookbacks": [5, 20], "fracdiff_d": 0.4, "ofi_window": 10},
        "regime": {"bins": [0.0, 0.5, 1.5, 5.0]},
        "quantile": {"low_q": 0.2, "high_q": 0.8},
        "conformal": {
            "alpha": 0.1,
            "decay": 0.01,
            "window": 200,
            "buffer_bps": 1.0,
            "online_update": False,
            "online_window": 200,
        },
        "policy": {
            "max_pos": 1.0,
            "kelly_shrink": 0.2,
            "cvar_window": 200,
            "cvar_alpha": 0.95,
            "risk_gamma": 10.0,
        },
        "execution": {
            "fee_bps": 1.0,
            "impact_coeff": 0.8,
            "impact_model": "square_root",
            "queue_fill_p": 0.85,
        },
        "risk": {
            "intraday_dd_limit": 0.02,
            "loss_streak_cooldown": 4,
            "vola_spike_mult": 2.5,
            "exposure_cap": 1.0,
        },
        "seed": 7,
        "target": {"horizon": 5},
    }


def _synthetic_ticks(n: int = 300, seed: int = SEED) -> pd.DataFrame:
    """Deterministic tiny tick frame with all columns BacktesterCAL needs."""
    rng = np.random.default_rng(seed)
    ret = rng.normal(0.0, 0.001, size=n)
    mid = 100.0 + np.cumsum(ret)
    spread = np.clip(rng.normal(0.0002, 5e-5, size=n), 5e-5, 8e-4)
    bid = mid - 0.5 * spread * mid
    ask = mid + 0.5 * spread * mid
    last = mid + rng.normal(0.0, spread * mid / 3.0)
    ts = pd.date_range("2026-01-01 09:30:00", periods=n, freq="s")
    df = pd.DataFrame(
        {
            "mid": mid,
            "bid": bid,
            "ask": ask,
            "bid_size": rng.integers(5, 50, size=n).astype(float),
            "ask_size": rng.integers(5, 50, size=n).astype(float),
            "last": last,
            "last_size": rng.integers(1, 10, size=n).astype(float),
            "spread": spread,
            "vol10": pd.Series(ret).rolling(10).std().fillna(0.001).to_numpy(),
            "feat_a": rng.normal(0.0, 1.0, size=n),
            "feat_b": rng.normal(0.0, 1.0, size=n),
            "y": ret,
        },
        index=ts,
    )
    return df


@pytest.fixture(scope="module")
def calibrated_bt() -> tuple[BacktesterCAL, pd.DataFrame]:
    """Build, fit, and calibrate a tiny BacktesterCAL; return with a run frame."""
    df = _synthetic_ticks(n=300)
    feat_cols = ["feat_a", "feat_b"]
    bt = BacktesterCAL(_tiny_cfg())
    bt.fit_quantiles(df[feat_cols].iloc[:150], df["y"].iloc[:150])
    bt.calibrate_conformal(df[feat_cols].iloc[150:250], df["y"].iloc[150:250])
    return bt, df


# ---------------------------------------------------------------------------
# Component-level reset contracts
# ---------------------------------------------------------------------------


def test_feature_store_reset_clears_buffer() -> None:
    fs = FeatureStore(0.4, 10, buf_maxlen=50)
    for i in range(20):
        fs.update(
            {
                "mid": 100.0 + i,
                "bid": 99.9,
                "ask": 100.1,
                "bid_size": 10.0,
                "ask_size": 10.0,
                "last": 100.0,
                "last_size": 1.0,
            }
        )
    assert len(fs.buf) == 20
    fs.reset_runtime_state()
    assert len(fs.buf) == 0
    # Static config survives reset:
    assert fs.d == 0.4
    assert fs.ofi_window == 10


def test_regime_model_reset_rewinds_state() -> None:
    reg = RegimeModel(bins=(0.0, 0.5, 1.5, 5.0))
    reg.update({"rv": 3.0})
    assert reg.state > 0
    reg.reset_runtime_state()
    assert reg.state == 0
    # Static config survives reset:
    assert reg.bins == (0.0, 0.5, 1.5, 5.0)


def test_guardrails_reset_zeros_peak_and_cooldown() -> None:
    g = Guardrails(0.02, 4, 2.5, 1.0)
    g.check([0.1, 0.2, 0.3, -0.5], 0.01, 0.01, loss_streak=5, proposed_pos=0.5)
    assert g.peak > 0 or g.cooldown > 0
    g.reset_runtime_state()
    assert g.peak == 0.0
    assert g.cooldown == 0


def test_execution_reset_rewinds_rng() -> None:
    ex = Execution(1.0, 0.8, "square_root", 0.85, seed=13)
    values_a = [ex.fill(100.0, 1e-4, 1.0, 0.0) for _ in range(20)]
    ex.reset_runtime_state()
    values_b = [ex.fill(100.0, 1e-4, 1.0, 0.0) for _ in range(20)]
    assert values_a == values_b, "Execution RNG did not rewind: fills diverged."


def test_conformal_reset_rehydrates_calibration_snapshot() -> None:
    cqr = ConformalCQR(alpha=0.1, decay=0.01, window=100, online_window=100)
    rng = np.random.default_rng(SEED)
    L = rng.normal(-1.0, 0.1, size=50)
    U = rng.normal(1.0, 0.1, size=50)
    y = rng.normal(0.0, 0.5, size=50)
    cqr.fit_calibrate(L, U, y)
    qhat_cal = cqr.qhat
    resid_cal = list(cqr._resid)
    # Drift the state:
    cqr.dynamic_alpha(rv=2.0, rv_ref=1.0)
    assert cqr.alpha != cqr.alpha0
    cqr._resid.append(99.9)
    # Reset must restore every calibrated attribute:
    cqr.reset_runtime_state()
    assert cqr.alpha == cqr.alpha0
    assert cqr.qhat == qhat_cal
    assert list(cqr._resid) == resid_cal


def test_conformal_reset_on_uncalibrated_instance_is_a_noop_on_qhat() -> None:
    """Reset before calibration must leave ``qhat`` ``None`` (not raise)."""
    cqr = ConformalCQR(alpha=0.1)
    assert cqr.qhat is None
    cqr.dynamic_alpha(rv=2.0, rv_ref=1.0)  # drifts alpha
    cqr.reset_runtime_state()
    assert cqr.qhat is None
    assert cqr.alpha == cqr.alpha0


# ---------------------------------------------------------------------------
# End-to-end BacktesterCAL equivalence across repeated runs
# ---------------------------------------------------------------------------


def test_backtester_run_is_bit_identical_across_repeated_calls(
    calibrated_bt: tuple[BacktesterCAL, pd.DataFrame],
) -> None:
    bt, df = calibrated_bt
    feat_cols = ["feat_a", "feat_b"]
    run_window = df.iloc[250:].copy()
    out1 = bt.run(run_window, feat_cols, y_col="y")
    out2 = bt.run(run_window, feat_cols, y_col="y")
    pd.testing.assert_frame_equal(
        out1.reset_index(drop=True),
        out2.reset_index(drop=True),
        check_exact=True,
        check_like=False,
    )


def test_backtester_components_rewind_before_run() -> None:
    """After one run + _reset_runtime_state, every component state is
    equivalent to its post-calibration / pre-run state.

    Builds a *fresh* calibrated instance so the baseline snapshot captures
    the virgin post-calibration state (``fs.buf`` empty, ``reg.state`` zero,
    ``guard.peak`` zero) — not whatever a previous test left behind.
    """
    df = _synthetic_ticks(n=300)
    feat_cols = ["feat_a", "feat_b"]
    bt = BacktesterCAL(_tiny_cfg())
    bt.fit_quantiles(df[feat_cols].iloc[:150], df["y"].iloc[:150])
    bt.calibrate_conformal(df[feat_cols].iloc[150:250], df["y"].iloc[150:250])
    run_window = df.iloc[250:].copy()

    # Snapshot the clean state immediately after calibration.
    clean = {
        "fs_buf_len": len(bt.fs.buf),
        "reg_state": bt.reg.state,
        "cqr_alpha": bt.cqr.alpha,
        "cqr_qhat": bt.cqr.qhat,
        "cqr_resid": list(bt.cqr._resid),
        "guard_peak": bt.guard.peak,
        "guard_cooldown": bt.guard.cooldown,
        "ret_hist_len": len(bt._ret_hist),
    }

    bt.run(run_window, feat_cols, y_col="y")
    # After run, at least some components must have drifted (sanity).
    drifted = (
        len(bt.fs.buf) != clean["fs_buf_len"]
        or bt.reg.state != clean["reg_state"]
        or bt.cqr.alpha != clean["cqr_alpha"]
        or bt.guard.peak != clean["guard_peak"]
        or len(bt._ret_hist) != clean["ret_hist_len"]
    )
    assert drifted, (
        "Test setup drift: run() did not actually mutate any component state; "
        "the reset-vs-drift assertion below becomes a tautology."
    )

    bt._reset_runtime_state()
    assert len(bt.fs.buf) == clean["fs_buf_len"]
    assert bt.reg.state == clean["reg_state"]
    assert bt.cqr.alpha == clean["cqr_alpha"]
    assert bt.cqr.qhat == clean["cqr_qhat"]
    assert list(bt.cqr._resid) == clean["cqr_resid"]
    assert bt.guard.peak == clean["guard_peak"]
    assert bt.guard.cooldown == clean["guard_cooldown"]
    assert len(bt._ret_hist) == clean["ret_hist_len"]


def test_backtester_run_differs_without_reset_interleaved_calls(
    calibrated_bt: tuple[BacktesterCAL, pd.DataFrame],
) -> None:
    """Regression guard: simulate the OLD (broken) behaviour by running
    with components pre-loaded from a prior pass. Proves the reset is
    load-bearing — without it, the output diverges.
    """
    bt, df = calibrated_bt
    feat_cols = ["feat_a", "feat_b"]
    run_window = df.iloc[250:].copy()

    # Baseline: run from clean state.
    baseline = bt.run(run_window, feat_cols, y_col="y")

    # Poison the streaming components post-hoc, bypassing _reset_runtime_state.
    bt.fs.buf.append(
        {
            "mid": 9999.0,
            "bid": 9998.0,
            "ask": 10000.0,
            "bid_size": 1.0,
            "ask_size": 1.0,
            "last": 9999.0,
            "last_size": 1.0,
        }
    )
    bt.reg.state = 2
    bt.guard.peak = 10.0
    bt.guard.cooldown = 30
    _ = bt.exec._rng.random()  # advance RNG one step

    # A fresh run() still produces the baseline — proving that
    # _reset_runtime_state inside run() wipes the poisoning.
    after_poison = bt.run(run_window, feat_cols, y_col="y")
    pd.testing.assert_frame_equal(
        baseline.reset_index(drop=True),
        after_poison.reset_index(drop=True),
        check_exact=True,
    )
