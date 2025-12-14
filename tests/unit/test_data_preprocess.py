# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.data.preprocess import normalize_df, normalize_numeric_columns, scale_series


def test_normalize_df_orders_and_interpolates() -> None:
    raw = pd.DataFrame(
        {
            "ts": [3, 1, 2],
            "price": [104.0, 100.0, np.nan],
            "volume": [1.0, 3.0, np.nan],
        }
    )
    normalized = normalize_df(raw)
    assert str(normalized["ts"].dt.tz) == "UTC"
    assert normalized["price"].iloc[0] == pytest.approx(100.0)
    assert normalized["price"].iloc[1] == pytest.approx(102.0)
    assert normalized["price"].iloc[2] == pytest.approx(104.0)
    assert normalized["volume"].iloc[1] == pytest.approx(2.0)
    assert normalized.index.tolist() == [0, 1, 2]


def test_normalize_df_infers_millisecond_timestamps() -> None:
    base_ms = 1_700_000_000_000
    raw = pd.DataFrame(
        {
            "ts": [base_ms, base_ms + 1_000, base_ms + 2_000],
            "price": [1.0, 2.0, 3.0],
        }
    )

    normalized = normalize_df(raw)

    assert str(normalized["ts"].dt.tz) == "UTC"
    deltas = normalized["ts"].diff().dt.total_seconds().dropna()
    assert deltas.tolist() == [1.0, 1.0]


def test_scale_series_zscore_and_minmax() -> None:
    data = np.array([1.0, 2.0, 3.0])
    z = scale_series(data, method="zscore")
    assert pytest.approx(z.mean(), abs=1e-12) == 0.0
    assert pytest.approx(z.std(ddof=0), abs=1e-12) == 1.0

    mm = scale_series(data, method="minmax")
    assert mm.min() == 0.0
    assert mm.max() == 1.0


def test_scale_series_handles_edge_cases() -> None:
    zeros = np.zeros(5)
    assert np.all(scale_series(zeros, method="zscore") == 0.0)
    assert np.all(scale_series([5, 5, 5], method="minmax") == 0.0)
    assert scale_series([], method="zscore").size == 0
    with pytest.raises(ValueError):
        scale_series(np.ones((2, 2)), method="zscore")
    with pytest.raises(TypeError):
        scale_series("abc", method="zscore")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        scale_series([1, 2, 3], method="unknown")


def test_normalize_numeric_columns_scales_dataframe() -> None:
    frame = pd.DataFrame(
        {
            "ts": [1, 2, 3],
            "price": [100.0, 101.0, 102.0],
            "volume": [1.0, 2.0, 3.0],
            "symbol": ["BTC", "BTC", "BTC"],
        }
    )

    normalized = normalize_numeric_columns(frame, exclude=["ts"])

    assert normalized["symbol"].tolist() == ["BTC", "BTC", "BTC"]
    assert pytest.approx(normalized["price"].mean(), abs=1e-12) == 0.0
    assert pytest.approx(normalized["price"].std(ddof=0), abs=1e-12) == 1.0
    expected_volume = scale_series(frame["volume"], method="zscore")
    assert np.allclose(normalized["volume"].values, expected_volume)
    assert normalized.dtypes["price"] == np.float64


def test_normalize_numeric_columns_preserves_nans_and_dtype() -> None:
    frame = pd.DataFrame(
        {
            "feature": [1.0, np.nan, 3.0, 5.0],
            "constant": [2, 2, 2, 2],
        }
    )

    normalized = normalize_numeric_columns(frame, method="minmax", use_float32=True)

    assert np.isnan(normalized.loc[1, "feature"])
    assert normalized["feature"].min(skipna=True) == pytest.approx(0.0)
    assert normalized["feature"].max(skipna=True) == pytest.approx(1.0)
    assert np.allclose(normalized["constant"].values, 0.0)
    assert normalized["feature"].dtype == np.float32


def test_normalize_numeric_columns_rejects_invalid_columns() -> None:
    frame = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})

    with pytest.raises(KeyError):
        normalize_numeric_columns(frame, columns=["missing"])  # type: ignore[list-item]

    with pytest.raises(TypeError):
        normalize_numeric_columns(frame, columns=["b"])  # type: ignore[list-item]


def test_normalize_numeric_columns_skips_boolean_columns_by_default() -> None:
    frame = pd.DataFrame(
        {
            "feature": [1.0, 2.0, 3.0],
            "flag": [True, False, True],
        }
    )

    normalized = normalize_numeric_columns(frame)

    assert normalized["flag"].dtype == bool
    assert normalized["flag"].tolist() == [True, False, True]
    assert normalized["feature"].mean() == pytest.approx(0.0)


def test_normalize_numeric_columns_rejects_explicit_boolean_columns() -> None:
    frame = pd.DataFrame(
        {
            "value": [1.0, 2.0, 3.0],
            "flag": [True, False, True],
        }
    )

    with pytest.raises(TypeError, match="boolean dtype"):
        normalize_numeric_columns(frame, columns=["value", "flag"])
