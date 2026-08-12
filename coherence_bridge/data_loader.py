# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Data loader for Askar's formats: Exness CSV, Parquet, QuestDB.

Accepts:
  1. CSV from efinance (Exness tick data)
  2. Parquet from backfill
  3. QuestDB query result (via PGWire)
  4. Raw numpy array (for testing)

Returns: pd.DataFrame with DatetimeIndex + OHLCV columns.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def load_csv(path: str | Path, *, datetime_col: str = "timestamp") -> pd.DataFrame:
    """Load CSV tick/bar data. Auto-detects delimiter and datetime format."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Data file not found: {p}")

    df = pd.read_csv(p, parse_dates=[datetime_col])
    df = df.set_index(datetime_col).sort_index()

    # Normalize column names
    col_map = {
        "close": "close",
        "Close": "close",
        "price": "close",
        "Price": "close",
        "bid": "close",
        "ask": "close",
        "volume": "volume",
        "Volume": "volume",
        "vol": "volume",
        "tick_volume": "volume",
    }
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

    if "close" not in df.columns:
        # Try first numeric column
        numeric = df.select_dtypes(include=[np.number]).columns
        if len(numeric) > 0:
            df["close"] = df[numeric[0]]
        else:
            raise ValueError("No 'close' or numeric price column found")

    if "volume" not in df.columns:
        df["volume"] = 1.0

    return df[["close", "volume"]]


def load_parquet(path: str | Path) -> pd.DataFrame:
    """Load Parquet backfill data."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Parquet file not found: {p}")

    df = pd.read_parquet(p)

    if "timestamp_ns" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp_ns"], unit="ns")
        df = df.set_index("timestamp")
    elif "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp")

    if "close" not in df.columns and "gamma" in df.columns:
        # This is a signal file, not OHLCV
        return df

    return df


def from_numpy(
    prices: np.ndarray,
    *,
    freq: str = "1min",
    start: str = "2024-01-01",
    instrument: str = "EURUSD",
) -> pd.DataFrame:
    """Create DataFrame from numpy price array (for testing/synthetic)."""
    n = len(prices)
    idx = pd.date_range(start, periods=n, freq=freq)
    return pd.DataFrame(
        {"close": prices, "volume": np.ones(n) * 100},
        index=idx,
    )


def validate_ohlcv(df: pd.DataFrame) -> list[str]:
    """Check DataFrame is ready for GeoSyncAdapter. Returns list of issues."""
    issues: list[str] = []

    if not isinstance(df.index, pd.DatetimeIndex):
        issues.append("Index must be DatetimeIndex")

    if "close" not in df.columns:
        issues.append("Missing 'close' column")

    if "volume" not in df.columns:
        issues.append("Missing 'volume' column")

    if len(df) < 30:
        issues.append(f"Too few rows: {len(df)} (need >= 30)")

    if df["close"].isna().any():
        issues.append(f"NaN in close: {df['close'].isna().sum()} rows")

    if (df["close"] <= 0).any():
        issues.append("Non-positive prices found")

    if not df.index.is_monotonic_increasing:
        issues.append("Index not monotonically increasing")

    dups = df.index.duplicated().sum()
    if dups > 0:
        issues.append(f"Duplicate timestamps: {dups}")

    return issues
