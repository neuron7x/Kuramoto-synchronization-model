# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import pandas as pd

from src.data.macro.integration import integrate_macro_features


def test_integrate_macro_features_prevents_leakage():
    market = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2023-02-10", "2023-02-20"], utc=True),
            "price": [100.0, 101.5],
        }
    )

    macro = pd.DataFrame(
        {
            "indicator": ["GDP"],
            "period_end": pd.to_datetime(["2023-01-31"], utc=True),
            "release_date": pd.to_datetime(["2023-02-15"], utc=True),
            "available_at": pd.to_datetime(["2023-02-18"], utc=True),
            "value": [1.5],
            "z_score": [0.1],
            "yoy_change": [0.02],
            "release_gap_days": [15],
        }
    )

    merged = integrate_macro_features(
        market,
        macro,
        on="timestamp",
        macro_time_column="available_at",
    )

    assert pd.isna(merged.loc[0, "value"])
    assert merged.loc[1, "value"] == 1.5


def test_integrate_macro_features_allows_forward_lookup():
    market = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2023-02-10"], utc=True),
            "price": [100.0],
        }
    )
    macro = pd.DataFrame(
        {
            "period_end": pd.to_datetime(["2023-01-31"], utc=True),
            "release_date": pd.to_datetime(["2023-02-15"], utc=True),
            "available_at": pd.to_datetime(["2023-02-15"], utc=True),
            "value": [1.5],
        }
    )

    merged = integrate_macro_features(
        market,
        macro,
        on="timestamp",
        macro_time_column="available_at",
        allow_future_leakage=True,
        direction="forward",
    )

    assert merged.loc[0, "value"] == 1.5


def test_integrate_macro_features_masks_using_alternative_availability_column():
    market = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2023-02-20"], utc=True),
            "price": [101.0],
        }
    )

    macro = pd.DataFrame(
        {
            "indicator": ["GDP"],
            "period_end": pd.to_datetime(["2023-01-31"], utc=True),
            "release_date": pd.to_datetime(["2023-02-15"], utc=True),
            "available_at": pd.to_datetime(["2023-02-25"], utc=True),
            "value": [2.0],
        }
    )

    merged = integrate_macro_features(
        market,
        macro,
        on="timestamp",
        macro_time_column="period_end",
        allow_future_leakage=False,
    )

    assert pd.isna(merged.loc[0, "value"])
