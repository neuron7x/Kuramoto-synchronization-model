# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Union

import numpy as np
import pandas as pd

from ..utils.logging import get_logger

_logger = get_logger(__name__)


ArrayLike = Union[np.ndarray, pd.Series, Sequence[float], Iterable[float]]


def normalize_df(
    df: pd.DataFrame, timestamp_col: str = "ts", *, use_float32: bool = False
) -> pd.DataFrame:
    """Return a cleaned and chronologically ordered copy of ``df``.

    The helper performs a defensive copy, standardises the timestamp column
    (if present) to UTC-aware ``datetime64`` values, sorts the frame by that
    column, removes duplicate rows and performs linear interpolation on the
    numeric columns to fill minor gaps.

    Parameters
    ----------
    df:
        Input dataframe to normalise. The original dataframe is never mutated.
    timestamp_col:
        Optional name of the column that stores timestamps (defaults to ``"ts"``).
    use_float32:
        Convert numeric columns to float32 to reduce memory usage (default: False).

    Returns
    -------
    pandas.DataFrame
        A normalised dataframe with a reset index for predictable downstream
        usage.
    """
    with _logger.operation(
        "normalize_df", rows=len(df), columns=len(df.columns), use_float32=use_float32
    ):
        normalized = df.copy()

        if timestamp_col in normalized.columns:
            timestamps = normalized[timestamp_col]
            if np.issubdtype(timestamps.dtype, np.number):
                normalized[timestamp_col] = pd.to_datetime(
                    timestamps, unit="s", errors="coerce", utc=True
                )
            else:
                normalized[timestamp_col] = pd.to_datetime(
                    timestamps, errors="coerce", utc=True
                )
            normalized = normalized.sort_values(timestamp_col)

        normalized = normalized.drop_duplicates()

        numeric_cols = normalized.select_dtypes(include=["number"]).columns
        if not numeric_cols.empty:
            normalized[numeric_cols] = normalized[numeric_cols].interpolate(
                method="linear", limit_direction="both"
            )

            # Convert to float32 if requested
            if use_float32:
                for col in numeric_cols:
                    if col != timestamp_col:
                        normalized[col] = normalized[col].astype(np.float32)

        return normalized.reset_index(drop=True)


def scale_series(
    x: ArrayLike, method: str = "zscore", *, use_float32: bool = False
) -> np.ndarray:
    """Scale a 1-D array according to the requested ``method``.

    Currently supported scaling methods are ``"zscore"`` (default) and
    ``"minmax"``. The function always returns a NumPy ``ndarray`` and leaves
    constant or empty inputs untouched.

    Parameters
    ----------
    x:
        Input array-like data to scale.
    method:
        Scaling method: "zscore" (standardization) or "minmax" (normalization).
    use_float32:
        Use float32 precision to reduce memory usage (default: False).

    Returns
    -------
    np.ndarray
        Scaled array with the same shape as input.
    """
    with _logger.operation("scale_series", method=method, use_float32=use_float32):
        dtype = np.float32 if use_float32 else float

        if isinstance(x, (np.ndarray, pd.Series)):
            values = np.asarray(x, dtype=dtype)
        else:
            if isinstance(x, (str, bytes)):
                raise TypeError("scale_series does not support string-like inputs")
            values = np.asarray(list(x), dtype=dtype)

        if values.ndim != 1:
            raise ValueError("scale_series expects a one-dimensional input")

        if values.size == 0:
            return values

        method = method.lower()

        if method == "zscore":
            std = values.std()
            if std == 0:
                return np.zeros_like(values)
            mean = values.mean()
            return (values - mean) / std

        if method == "minmax":
            data_min = values.min()
            data_range = values.max() - data_min
            if data_range == 0:
                return np.zeros_like(values)
            return (values - data_min) / data_range

        raise ValueError(f"Unsupported scaling method: {method!r}")
