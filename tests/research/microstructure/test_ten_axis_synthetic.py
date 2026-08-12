# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Ten-axis falsification battery on a SYNTHETIC ground-truth substrate (path B).

Each axis must DETECT a planted edge/persistence and REJECT its absence — that
two-sided behaviour is what makes the axis a falsifier rather than a replay.
Thresholds are set strictly between the empirically-measured edge and null
statistics (calibration run, deterministic seeds).

Scope boundary (honest): this validates that the seven array-level axis METHODS
have power and control false positives on a known substrate. It does NOT anchor
the frozen Session-1 result (that is path A, gated on the external L2 substrate),
and the kill-test (parquet loader), walk-forward (path artifact) and
transfer-entropy axes are the next rung (I/O adapters). It makes no scientific
claim about real markets.
"""

from __future__ import annotations

import numpy as np
import pytest

from research.microstructure.attribution import lag_ic_sweep
from research.microstructure.cv import purged_kfold_ic
from research.microstructure.hurst import dfa_hurst
from research.microstructure.robustness import (
    block_bootstrap_ic,
    deflated_sharpe,
    mutual_information,
)
from research.microstructure.spectral import spectral_report
from research.microstructure.synthetic_substrate import (
    make_persistent_signal,
    make_white_signal,
    permute_target,
    plant_edge,
)

N, M = 4000, 6


@pytest.fixture(scope="module")
def substrate() -> dict[str, np.ndarray]:
    sig = make_persistent_signal(N, M, seed=7)
    tgt = plant_edge(sig, edge=0.3, lag=1, noise=1.0, seed=8)
    return {
        "signal": sig,
        "target": tgt,
        "null": permute_target(tgt, seed=9),
        "white": make_white_signal(N, M, seed=10),
    }


def test_axis2_block_bootstrap_ci(substrate: dict[str, np.ndarray]) -> None:
    s = substrate["signal"].ravel()
    edge = block_bootstrap_ic(s, substrate["target"].ravel(), n_bootstraps=200)
    null = block_bootstrap_ic(s, substrate["null"].ravel(), n_bootstraps=200)
    assert edge.ci_lo_95 > 0.0, "edge CI must exclude 0"  # detect
    assert null.ci_lo_95 < 0.0 < null.ci_hi_95, "null CI must straddle 0"  # reject


def test_axis3_deflated_sharpe(substrate: dict[str, np.ndarray]) -> None:
    def dsr(target: np.ndarray) -> float:
        pos = np.sign(substrate["signal"][:-1])
        pnl = (pos * np.diff(target, axis=0)).mean(axis=1)
        sr = float(pnl.mean() / (pnl.std() + 1e-12) * np.sqrt(252))
        return deflated_sharpe(sr, n_trials=10, n_observations=len(pnl)).deflated_sharpe

    assert dsr(substrate["target"]) > 5.0  # detect
    assert dsr(substrate["null"]) < 2.0  # reject


def test_axis4_purged_kfold(substrate: dict[str, np.ndarray]) -> None:
    edge = purged_kfold_ic(substrate["signal"], substrate["target"], horizon_rows=1)
    null = purged_kfold_ic(substrate["signal"], substrate["null"], horizon_rows=1)
    assert edge.ic_mean > 0.3 and all(f > 0 for f in edge.ic_per_fold)  # detect, 5/5
    assert abs(null.ic_mean) < 0.05  # reject


def test_axis5_mutual_information(substrate: dict[str, np.ndarray]) -> None:
    s = substrate["signal"].ravel()
    edge = mutual_information(s, substrate["target"].ravel())
    null = mutual_information(s, substrate["null"].ravel())
    assert edge.mutual_information_nats > 0.1  # detect
    assert null.mutual_information_nats < 0.05  # reject


def test_axis6_lag_attribution(substrate: dict[str, np.ndarray]) -> None:
    edge = lag_ic_sweep(substrate["signal"][:, 0], substrate["target"])
    null = lag_ic_sweep(substrate["signal"][:, 0], substrate["null"])
    assert edge.ic_peak_value > 0.05  # detect a lead
    assert abs(null.ic_peak_value) <= edge.ic_peak_value  # reject: null no stronger


def test_axis7_spectral_redness(substrate: dict[str, np.ndarray]) -> None:
    persistent = spectral_report(substrate["signal"][:, 0])
    white = spectral_report(substrate["white"][:, 0])
    assert persistent.redness_slope_beta > 1.0  # detect red spectrum
    assert white.redness_slope_beta < 0.5  # reject: white is flat


def test_axis8_dfa_hurst(substrate: dict[str, np.ndarray]) -> None:
    persistent = dfa_hurst(substrate["signal"][:, 0])
    white = dfa_hurst(substrate["white"][:, 0])
    assert persistent.hurst_exponent > 0.7 and persistent.r_squared > 0.9  # detect
    assert white.hurst_exponent < 0.6  # reject: white ≈ 0.5


@pytest.mark.parametrize("seed", [11, 23, 37])
def test_falsification_is_robust_across_seeds(seed: int) -> None:
    """The detect/reject separation holds under reseeding (not a lucky draw)."""
    sig = make_persistent_signal(N, M, seed=seed)
    tgt = plant_edge(sig, edge=0.3, lag=1, noise=1.0, seed=seed + 1)
    null = permute_target(tgt, seed=seed + 2)
    edge_ic = block_bootstrap_ic(sig.ravel(), tgt.ravel(), n_bootstraps=100)
    null_ic = block_bootstrap_ic(sig.ravel(), null.ravel(), n_bootstraps=100)
    assert edge_ic.ci_lo_95 > 0.0 and (null_ic.ci_lo_95 < 0.0 < null_ic.ci_hi_95)
