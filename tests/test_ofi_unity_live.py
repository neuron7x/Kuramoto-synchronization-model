from __future__ import annotations

import numpy as np
import pandas as pd

from research.kernels.ofi_unity_live import ofi_unity_kernel, validate_unity


def _synthetic_l2(n: int = 300) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=n, freq="h", tz="UTC")
    base = np.cumsum(np.random.default_rng(42).normal(0, 0.1, n)) + 100
    df = pd.DataFrame(
        {
            "x_bid": base - 0.01,
            "x_ask": base + 0.01,
            "mid_returns": np.r_[0.0, np.diff(np.log(base))],
        },
        index=idx,
    )
    return df


def test_ofi_unity_kernel_runs() -> None:
    df = _synthetic_l2()
    s = ofi_unity_kernel(df, window=60)
    assert len(s) == len(df) - 60
    assert s.notna().all()


def test_validate_unity_schema() -> None:
    df = _synthetic_l2()
    s = ofi_unity_kernel(df, window=60)
    v = validate_unity(s, df["mid_returns"].shift(-1))
    for key in ["IC", "p_value", "DETECT", "DISCRIMINATE", "DELIVER", "FINAL"]:
        assert key in v
