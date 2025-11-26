"""Tests for the NeuroPRO synthetic data helpers."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from neuropro import data as data_module
from neuropro import synthetic as synthetic_module


def test_generate_demo_ticks_is_deterministic(tmp_path: Path) -> None:
    out_path = tmp_path / "sim_ticks.csv"

    first = pd.read_csv(
        synthetic_module.generate_demo_ticks(out_path, n=256, seed=1234)
    )

    out_path.unlink()

    second = pd.read_csv(
        synthetic_module.generate_demo_ticks(out_path, n=256, seed=1234)
    )

    pd.testing.assert_frame_equal(first, second)


def test_read_ticks_csv_materialises_missing_demo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dataset_path = tmp_path / "sim_ticks.csv"

    monkeypatch.setattr(
        synthetic_module, "DEFAULT_DEMO_TICKS_PATH", dataset_path, raising=False
    )
    monkeypatch.setattr(
        data_module, "DEFAULT_DEMO_TICKS_PATH", dataset_path, raising=False
    )
    monkeypatch.setattr(
        data_module,
        "generate_demo_ticks",
        synthetic_module.generate_demo_ticks,
        raising=False,
    )

    df = data_module.read_ticks_csv(dataset_path)

    assert dataset_path.exists()
    assert df.index.name == "timestamp"
    assert df.index.is_monotonic_increasing
    assert df.shape[0] == 15000
    assert df.columns.tolist() == [
        "mid",
        "bid",
        "ask",
        "bid_size",
        "ask_size",
        "last",
        "last_size",
        "ret1",
        "ret5",
        "ret20",
        "vol10",
        "vol50",
        "spread",
        "regime",
        "y",
    ]
    assert df.index[0].isoformat() == "2024-01-01T09:30:00"
    assert df.index[-1].isoformat() == "2024-01-01T13:39:59"
    assert df["mid"].iloc[0] == pytest.approx(100.00000073809201)
    assert df["regime"].value_counts().to_dict() == {0: 4000, 1: 7000, 2: 4000}
    assert df["y"].iloc[-1] == pytest.approx(0.0)
