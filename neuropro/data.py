"""Data loading utilities for NeuroTrade PRO demos."""

from __future__ import annotations

import pandas as pd


def read_ticks_csv(path: str, time_col: str = "timestamp") -> pd.DataFrame:
    """Read tick-level CSV data with a parsed datetime index."""
    df = pd.read_csv(path, parse_dates=[time_col])
    df = df.set_index(time_col).sort_index()
    return df
