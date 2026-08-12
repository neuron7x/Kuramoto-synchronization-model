from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.kernels.ofi_unity_live import ofi_unity_kernel


def synthetic_df(rows: int = 120) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=rows, freq="h")
    x = np.linspace(100, 101, rows)
    return pd.DataFrame({"bid_1": x - 0.01, "ask_1": x + 0.01}, index=idx)


def test_attack_empty_dataframe() -> None:
    with pytest.raises(ValueError):
        ofi_unity_kernel(pd.DataFrame())


def test_attack_single_row_returns_empty_series() -> None:
    s = ofi_unity_kernel(synthetic_df(rows=1), window=1)
    assert len(s) == 0


def test_attack_all_nan_raises() -> None:
    df = pd.DataFrame({"bid_1": [np.nan] * 100, "ask_1": [np.nan] * 100})
    with pytest.raises(ValueError):
        ofi_unity_kernel(df)


def test_attack_subnormal_floats_survive() -> None:
    tiny = np.float64(2.2250738585072014e-308)
    df = pd.DataFrame({"bid_1": [tiny] * 100, "ask_1": [tiny * 1.0001] * 100})
    s = ofi_unity_kernel(df)
    assert s.notna().all()
