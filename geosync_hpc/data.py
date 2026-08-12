# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Data loading utilities for GeoSync HPC demos."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from geosync_hpc.synthetic import DEFAULT_DEMO_TICKS_PATH, generate_demo_ticks


def _ensure_demo_dataset(path: Path) -> None:
    """Materialise the demo tick dataset on demand if it is missing."""

    resolved = path.resolve()
    if not path.exists() and resolved == DEFAULT_DEMO_TICKS_PATH:
        generate_demo_ticks(DEFAULT_DEMO_TICKS_PATH)


def read_ticks_csv(path: str | Path, time_col: str = "timestamp") -> pd.DataFrame:
    """Read tick-level CSV data with a parsed datetime index."""

    csv_path = Path(path)
    _ensure_demo_dataset(csv_path)

    if not csv_path.exists():
        raise FileNotFoundError(f"Tick dataset not found at {csv_path}")

    df = pd.read_csv(csv_path, parse_dates=[time_col])
    df = df.set_index(time_col).sort_index()
    return df
