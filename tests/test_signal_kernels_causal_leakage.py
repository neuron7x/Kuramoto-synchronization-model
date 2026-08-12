"""Regression tests: causal look-ahead leakage in two research signal kernels.

Two confirmed defects are pinned here so they cannot silently return:

1. ``neurophase_bridge`` exported an execution gate whose per-bar phase was
   computed from a global mean and a whole-array Hilbert transform. That made
   ``phase[i]`` (and the gate at bar ``i``) depend on FUTURE samples ``j > i``
   — look-ahead that inflates any downstream backtest of the gate history. The
   causal version's phase/gate at bar ``i`` must be invariant to any change
   after bar ``i``.

2. ``plv_market_spread`` built its significance null by i.i.d.-permuting the
   Hilbert phases, destroying the spread's autocorrelation. The null PLV then
   collapsed to ~1/sqrt(N) and the test turned anti-conservative: two
   independent-but-autocorrelated series were flagged ``SIGNAL_READY``. The
   autocorrelation-preserving (FFT phase-randomised) null must NOT flag an
   uncoupled pair.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.kernels.neurophase_bridge import run as run_bridge
from research.kernels.plv_market_spread import _phase, _plv
from research.kernels.plv_market_spread import run as run_plv


def _ar1(n: int, phi: float, sd: float, seed: int) -> np.ndarray:
    """A stationary AR(1) series: autocorrelated but with no cross-structure."""
    rng = np.random.default_rng(seed)
    x = np.zeros(n, dtype=float)
    noise = rng.normal(0.0, sd, n)
    for t in range(1, n):
        x[t] = phi * x[t - 1] + noise[t]
    return x


def _write_bridge_csv(path: Path, mid: np.ndarray) -> None:
    n = len(mid)
    ts = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    df = pd.DataFrame({"ts": ts, "mid": mid})
    df["mid_returns"] = np.r_[0.0, np.diff(np.log(mid))]
    df.to_csv(path, index=False)


def test_neurophase_gate_is_invariant_to_future_bars(tmp_path: Path) -> None:
    """phase[i] and the gate at bar i must not depend on samples after i.

    Two inputs are identical up to bar ``i`` and diverge sharply afterwards.
    A causal gate produces bit-identical phase and execution decisions at every
    bar ``k <= i``; the buggy whole-array Hilbert did not (it leaked the future
    back into the present through the FFT).
    """
    n = 300
    window = 64
    i = 150

    base = np.cumsum(np.random.default_rng(0).normal(0.0, 0.2, n))
    shared = 1800.0 + base

    diverged = shared.copy()
    diverged[i + 1 :] += np.random.default_rng(999).normal(0.0, 5.0, n - (i + 1))

    csv_a = tmp_path / "a.csv"
    csv_b = tmp_path / "b.csv"
    _write_bridge_csv(csv_a, shared)
    _write_bridge_csv(csv_b, diverged)

    out_a = run_bridge(csv_a, tmp_path / "oa.csv", window=window, threshold=0.5)
    out_b = run_bridge(csv_b, tmp_path / "ob.csv", window=window, threshold=0.5)

    # Schema is preserved.
    assert list(out_a.columns) == ["ts", "mid", "phase", "R", "gate_state", "execution_allowed"]

    phase_a = out_a["phase"].to_numpy(dtype=float)
    phase_b = out_b["phase"].to_numpy(dtype=float)
    gate_a = out_a["execution_allowed"].to_numpy()
    gate_b = out_b["execution_allowed"].to_numpy()
    state_a = out_a["gate_state"].to_numpy()
    state_b = out_b["gate_state"].to_numpy()

    # Every bar up to and including the divergence point must be untouched by
    # the future. This is the core causal-invariance contract.
    np.testing.assert_allclose(
        phase_a[: i + 1],
        phase_b[: i + 1],
        rtol=0.0,
        atol=1e-9,
        err_msg="CAUSAL LEAK: phase[<=i] changed when a later bar changed",
    )
    assert np.array_equal(gate_a[: i + 1], gate_b[: i + 1]), (
        "CAUSAL LEAK: execution_allowed[<=i] changed when a later bar changed"
    )
    assert np.array_equal(state_a[: i + 1], state_b[: i + 1]), (
        "CAUSAL LEAK: gate_state[<=i] changed when a later bar changed"
    )

    # And the change after bar i is real (guards against a degenerate no-op input
    # that would pass the invariance check vacuously).
    assert not np.allclose(phase_a[i + 1 :], phase_b[i + 1 :])


def _write_plv_csv(path: Path, mid_returns: np.ndarray, spread: np.ndarray) -> None:
    n = len(mid_returns)
    ts = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    mid = 1800.0 + np.cumsum(mid_returns)
    df = pd.DataFrame({"ts": ts, "mid": mid, "spread": spread, "mid_returns": mid_returns})
    df.to_csv(path, index=False)


def test_plv_null_does_not_flag_independent_autocorrelated_series(tmp_path: Path) -> None:
    """Two independent AR(1) drivers must NOT be flagged SIGNAL_READY.

    The market-return and spread series share no cross-structure, only their own
    autocorrelation. The i.i.d.-permutation null (the bug) reported p < 0.05 for
    exactly this case; the autocorrelation-preserving null must reject it.
    """
    n = 800
    midr = _ar1(n, 0.9, 0.01, seed=1)
    spread = 0.05 + 0.01 * _ar1(n, 0.9, 1.0, seed=2)

    csv = tmp_path / "indep.csv"
    _write_plv_csv(csv, midr, spread)
    out_json = tmp_path / "plv.json"

    verdict = run_plv(csv, out_json, n=500, seed=42)

    # Schema is preserved.
    assert set(verdict) == {"plv", "p_value", "FINAL"}
    assert json.loads(out_json.read_text(encoding="utf-8")) == verdict

    assert verdict["FINAL"] != "SIGNAL_READY", (
        f"ANTI-CONSERVATIVE NULL: independent AR(1) pair flagged {verdict['FINAL']} "
        f"at p={verdict['p_value']}"
    )
    assert verdict["p_value"] >= 0.05


def test_permutation_null_would_have_flagged_the_uncoupled_pair(tmp_path: Path) -> None:
    """Contrast: the OLD i.i.d.-permutation null is anti-conservative here.

    Computed on the SAME phases, the permutation p-value is far smaller than the
    autocorrelation-preserving one — the mechanism behind the false SIGNAL_READY.
    This locks in *why* the fix was needed, not just that the new verdict
    differs. It reuses the same realisation the calibration test rejects
    (seeds 1/2), whose observed PLV sits inside the bulk of the
    autocorrelation-preserving null.
    """
    n = 800
    midr = _ar1(n, 0.9, 0.01, seed=1)
    spread = 0.05 + 0.01 * _ar1(n, 0.9, 1.0, seed=2)

    m = min(len(midr), len(spread))
    split = int(0.7 * m)
    phi_m = _phase(midr[split:m])
    phi_s = _phase(spread[split:m])
    obs = _plv(phi_m, phi_s)

    # Reconstruct the buggy i.i.d.-permutation null in-line.
    rng = np.random.default_rng(42)
    n_surr = 500
    hits = sum(1 for _ in range(n_surr) if _plv(phi_m, rng.permutation(phi_s)) >= obs)
    perm_p = (hits + 1) / (n_surr + 1)

    csv = tmp_path / "indep.csv"
    _write_plv_csv(csv, midr, spread)
    verdict = run_plv(csv, tmp_path / "plv.json", n=n_surr, seed=42)
    new_p = float(verdict["p_value"])

    assert perm_p < 0.05, f"expected the permutation null to be anti-conservative, got {perm_p}"
    assert new_p > perm_p, (
        f"autocorrelation-preserving null must be more conservative than permutation: "
        f"new_p={new_p} perm_p={perm_p}"
    )
