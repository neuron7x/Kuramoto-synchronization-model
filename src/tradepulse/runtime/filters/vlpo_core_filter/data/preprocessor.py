"""Utility helpers for preparing telemetry dataframes."""

from __future__ import annotations

import pandas as pd
from sklearn.preprocessing import MinMaxScaler


def prepare_timeseries(data: pd.DataFrame, *, target_col: str) -> pd.DataFrame:
    """Scale non-target columns to ``[0, 1]`` while keeping the target intact."""

    if target_col not in data.columns:
        raise ValueError(f"Target column '{target_col}' missing from dataframe")

    scaler = MinMaxScaler()
    feature_columns = [col for col in data.columns if col != target_col]
    features = data[feature_columns]
    scaled = pd.DataFrame(
        scaler.fit_transform(features),
        columns=feature_columns,
        index=data.index,
    )
    scaled[target_col] = data[target_col].to_numpy()
    return scaled


__all__ = ["prepare_timeseries"]
