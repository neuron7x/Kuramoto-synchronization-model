from __future__ import annotations

import numpy as np
import pandas as pd

from research.kernels.neurophase_bridge import run


def test_neurophase_bridge_outputs_schema(tmp_path):
    n = 400
    ts = pd.date_range("2025-01-01", periods=n, freq="h", tz="UTC")
    mid = 100 + np.sin(np.linspace(0, 10, n))
    df = pd.DataFrame({"ts": ts, "bid_close": mid - 0.01, "ask_close": mid + 0.01, "mid": mid})
    df["spread"] = df["ask_close"] - df["bid_close"]
    df["mid_returns"] = np.r_[0.0, np.diff(np.log(mid))]

    inp = tmp_path / "x.csv"
    out = tmp_path / "o.csv"
    df.to_csv(inp, index=False)

    result = run(inp, out, window=64, threshold=0.5)
    assert out.exists()
    assert list(result.columns) == ["ts", "mid", "phase", "R", "gate_state", "execution_allowed"]
