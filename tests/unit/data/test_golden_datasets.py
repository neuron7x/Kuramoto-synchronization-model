# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts import data_sanity

DATA_DIR = Path("data/golden")
BASELINE_FILE = DATA_DIR / "indicator_macd_baseline.csv"


def test_macd_baseline_is_minimal_and_clean() -> None:
    assert BASELINE_FILE.exists(), "Golden baseline is missing"

    df = pd.read_csv(BASELINE_FILE, parse_dates=["ts"])
    assert len(df) <= 10
    assert df["ts"].is_monotonic_increasing
    assert df.duplicated().sum() == 0
    assert df.isna().sum().sum() == 0

    analysis = data_sanity.analyze_csv(BASELINE_FILE)
    assert analysis.duplicate_rows == 0
    assert analysis.nan_ratio == 0
    assert analysis.spike_counts == {}
