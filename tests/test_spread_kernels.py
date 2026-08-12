from __future__ import annotations

import numpy as np
import pandas as pd

from research.kernels.neurophase_bridge import run as run_bridge
from research.kernels.plv_market_spread import run as run_plv
from research.kernels.ricci_on_spread import run as run_ricci
from research.kernels.spread_stress_detector import run as run_stress


def _sample_csv(tmp_path):
    n = 600
    ts = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    mid = 1800 + np.cumsum(np.random.default_rng(42).normal(0, 0.2, n))
    spread = np.maximum(0.03, 0.05 + np.random.default_rng(7).normal(0, 0.005, n))
    bid = mid - spread / 2
    ask = mid + spread / 2
    df = pd.DataFrame({"ts": ts, "bid_close": bid, "ask_close": ask, "mid": mid, "spread": spread})
    df["mid_returns"] = np.r_[0.0, np.diff(np.log(mid))]
    p = tmp_path / "x.csv"
    df.to_csv(p, index=False)
    return p


def test_spread_kernels_end_to_end(tmp_path):
    inp = _sample_csv(tmp_path)
    assert "FINAL" in run_ricci(inp, tmp_path / "r.json")
    assert "FINAL" in run_plv(inp, tmp_path / "p.json", n=50)
    assert "FINAL" in run_stress(inp, tmp_path / "s.json")
    out = run_bridge(inp, tmp_path / "b.csv", window=64)
    assert "gate_state" in out.columns
