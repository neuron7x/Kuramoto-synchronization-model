# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the :mod:`strategies.quantum_neural` dataset utilities."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

# The strategy module depends on PyTorch for tensors and Dataset base classes.
# Skip these tests automatically when PyTorch is not installed.
pytest.importorskip("torch")

from strategies.quantum_neural import AdvancedTradingDataset


def _make_frame(rows: int) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=rows, freq="D")
    base = 10.0 + np.arange(rows, dtype=np.float32)
    volume = 1_000.0 + np.arange(rows, dtype=np.float32)
    return pd.DataFrame(
        {
            "date": dates,
            "open": base - 0.5,
            "high": base + 0.5,
            "low": base - 1.0,
            "close": base,
            "volume": volume,
        }
    )


def test_dataset_targets_align_with_next_close() -> None:
    df = _make_frame(12)
    seq_len = 4
    dataset = AdvancedTradingDataset(df, sequence_length=seq_len, augment=False)

    assert len(dataset) == len(df) - seq_len

    window, target_price, target_action = dataset[0]
    assert target_price.item() == pytest.approx(df["close"].iloc[seq_len])
    assert target_action.item() == 1

    last_window, last_price, last_action = dataset[-1]
    expected_index = len(df) - 1
    assert last_price.item() == pytest.approx(df["close"].iloc[expected_index])
    assert last_action.item() == 1

    assert window.shape == last_window.shape


def test_dataset_rejects_out_of_range_indices() -> None:
    df = _make_frame(8)
    dataset = AdvancedTradingDataset(df, sequence_length=3, augment=False)

    with pytest.raises(IndexError):
        _ = dataset[len(dataset)]

    with pytest.raises(IndexError):
        _ = dataset[-len(dataset) - 1]


def test_dataset_requires_enough_observations() -> None:
    df = _make_frame(3)
    with pytest.raises(ValueError):
        AdvancedTradingDataset(df, sequence_length=3, augment=False)

    with pytest.raises(ValueError):
        AdvancedTradingDataset(df.iloc[:1], sequence_length=1, augment=False)
