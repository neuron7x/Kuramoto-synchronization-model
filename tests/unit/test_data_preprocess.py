# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradepulse.core.data.preprocess import normalize_df, scale_series


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
