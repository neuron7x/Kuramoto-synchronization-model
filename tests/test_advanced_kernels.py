from __future__ import annotations

import json

import numpy as np
import pandas as pd

from research.askar.closing_report import run as run_report
from research.kernels.horizon_sweep import run as run_horizon
from research.kernels.ricci_regime_conditioned import run as run_regime
from research.kernels.signal_combiner import run as run_combiner


def _sample_csv(tmp_path):
    n = 700
    ts = pd.date_range("2023-01-01", periods=n, freq="h", tz="UTC")
    mid = 1800 + np.cumsum(np.random.default_rng(1).normal(0, 0.2, n))
    spread = np.maximum(0.03, 0.05 + np.random.default_rng(2).normal(0, 0.005, n))
    bid = mid - spread / 2
    ask = mid + spread / 2
    df = pd.DataFrame({"ts": ts, "bid_close": bid, "ask_close": ask, "mid": mid, "spread": spread})
    df["mid_returns"] = np.r_[0.0, np.diff(np.log(mid))]
    p = tmp_path / "sample.csv"
    df.to_csv(p, index=False)
    return p


def test_advanced_kernels_and_report(tmp_path):
    inp = _sample_csv(tmp_path)
    r1 = run_regime(inp, tmp_path / "regime.json")
    r2 = run_horizon(inp, tmp_path / "horizon.json")
    r3 = run_combiner(inp, tmp_path / "combiner.json")
    assert "FINAL" in r1 and "table" in r2 and "FINAL" in r3

    results_dir = tmp_path / "results"
    results_dir.mkdir()
    (results_dir / "ofi_unity_dukascopy_verdict.json").write_text(
        json.dumps({"FINAL": "REJECT", "IC": 0.0})
    )
    (results_dir / "ricci_on_spread_verdict.json").write_text(
        json.dumps({"FINAL": "REJECT", "IC": 0.01})
    )
    (results_dir / "plv_spread_market_verdict.json").write_text(json.dumps({"FINAL": "REJECT"}))
    (results_dir / "spread_stress_verdict.json").write_text(
        json.dumps({"FINAL": "REJECT", "IC": 0.02})
    )
    (results_dir / "ricci_regime_verdict.json").write_text(json.dumps(r1))
    (results_dir / "horizon_sweep_verdict.json").write_text(json.dumps(r2))
    (results_dir / "signal_combiner_verdict.json").write_text(json.dumps(r3))

    rep = run_report(results_dir, tmp_path / "final.json")
    assert "FINAL_VERDICT" in rep
