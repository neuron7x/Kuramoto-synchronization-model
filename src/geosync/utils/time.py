# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Time-series utilities for OHLCV data resampling.

This module provides proper OHLCV aggregation that respects the semantics of
each field: Open=first, High=max, Low=min, Close=last, Volume=sum.
"""

from typing import Dict, Literal

import pandas as pd

__all__ = ["resample_ohlcv"]


def resample_ohlcv(
    df: pd.DataFrame,
    rule: str,
    *,
    price_cols: tuple[str, str, str, str] = ("open", "high", "low", "close"),
    volume_col: str = "volume",
    label: Literal["left", "right"] = "left",
    closed: Literal["left", "right"] = "left",
) -> pd.DataFrame:
    """Resample OHLCV data to a different frequency.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with DatetimeIndex containing OHLCV data
    rule : str
        Resampling frequency rule (e.g., '5min', '1h', '1D')
    price_cols : tuple[str, str, str, str], optional
        Column names for (open, high, low, close), by default ("open", "high", "low", "close")
    volume_col : str, optional
        Column name for volume, by default "volume"
    label : {"left", "right"}, optional
        Which bin edge label to use, by default "left"
    closed : {"left", "right"}, optional
        Which side of bin interval is closed, by default "left"

    Returns
    -------
    pd.DataFrame
        Resampled OHLCV data with proper aggregation

    Examples
    --------
    >>> import pandas as pd
    >>> import numpy as np
    >>> dates = pd.date_range('2024-01-01', periods=10, freq='1min')
    >>> df = pd.DataFrame({
    ...     'open': np.arange(10, 20),
    ...     'high': np.arange(11, 21),
    ...     'low': np.arange(9, 19),
    ...     'close': np.arange(10.5, 20.5),
    ...     'volume': np.ones(10) * 100
    ... }, index=dates)
    >>> resampled = resample_ohlcv(df, '5min')
    >>> len(resampled)
    2
    """
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("DataFrame must have a DatetimeIndex")

    # ``resample`` requires a monotonic DatetimeIndex. Sorting ensures that
    # consumers do not need to pre-order their data before calling the helper,
    # which previously surfaced as a cryptic pandas ``ValueError``.
    if not df.index.is_monotonic_increasing:
        df = df.sort_index()

    open_col, high_col, low_col, close_col = price_cols

    # Build aggregation dictionary
    agg_dict: Dict[str, str] = {}

    if open_col in df.columns:
        agg_dict[open_col] = "first"
    if high_col in df.columns:
        agg_dict[high_col] = "max"
    if low_col in df.columns:
        agg_dict[low_col] = "min"
    if close_col in df.columns:
        agg_dict[close_col] = "last"
    if volume_col in df.columns:
        agg_dict[volume_col] = "sum"

    if not agg_dict:
        raise ValueError(
            "No OHLCV columns found in DataFrame; expected at least one of "
            f"{price_cols + (volume_col,)}"
        )

    # Resample with proper aggregation
    resampled = df.resample(rule, label=label, closed=closed).agg(agg_dict)

    # Drop rows where all values are NaN
    resampled = resampled.dropna(how="all")

    return resampled
