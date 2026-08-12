# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from pathlib import Path

import pytest

from scripts import data_sanity

REFERENCE_DATASETS = [
    Path("data/sample.csv"),
    Path("data/sample_ohlc.csv"),
    Path("data/golden/indicator_macd_baseline.csv"),
]


@pytest.mark.parametrize("dataset", REFERENCE_DATASETS)
def test_reference_datasets_are_clean(dataset: Path) -> None:
    analysis = data_sanity.analyze_csv(dataset)
    assert analysis.duplicate_rows == 0
    assert analysis.nan_ratio == pytest.approx(0.0)
    assert analysis.column_nan_ratios == {}
    assert analysis.spike_counts == {}
