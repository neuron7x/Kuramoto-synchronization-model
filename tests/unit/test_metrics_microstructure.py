from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.metrics.microstructure import (
    MicrostructureReport,
    build_symbol_microstructure_report,
    hasbrouck_information_impulse,
    kyles_lambda,
    queue_imbalance,
)


def test_queue_imbalance_clips_and_normalizes() -> None:
    bid_sizes = [-1.0, 2.0, 3.0]
    ask_sizes = [1.0, -5.0, 1.0]
    # clipped -> bid_total=5, ask_total=2 => imbalance=(5-2)/(5+2)
    assert queue_imbalance(bid_sizes, ask_sizes) == pytest.approx(3 / 7)


def test_queue_imbalance_returns_zero_for_empty_book() -> None:
    assert queue_imbalance([], []) == 0.0


def test_kyles_lambda_filters_invalid_and_centers_inputs() -> None:
    returns = [0.01, np.nan, 0.03, -0.02]
    signed_volume = [10.0, 5.0, np.nan, -10.0]
    # After filtering -> returns [0.01, -0.02], volume [10.0, -10.0]
    # centered volume: [10, -10] - mean(0) => unchanged
    # centered returns: [0.015, -0.015]
    expected = (10 * 0.015 + (-10) * -0.015) / (10**2 + (-10) ** 2)
    assert kyles_lambda(returns, signed_volume) == pytest.approx(expected)


def test_kyles_lambda_returns_zero_for_degenerate_volume() -> None:
    assert kyles_lambda([0.1, 0.2], [0.0, 0.0]) == 0.0


def test_hasbrouck_information_impulse_handles_signed_root() -> None:
    returns = [0.05, -0.02, 0.03]
    signed_volume = [9.0, 0.0, -16.0]
    signed_volume = np.asarray(signed_volume)
    transformed = signed_volume - np.mean(signed_volume)
    transformed = np.sign(transformed) * np.sqrt(np.abs(transformed))
    transformed = transformed - np.mean(transformed)
    centered_returns = np.asarray(returns) - np.mean(returns)
    expected = float(
        np.dot(transformed, centered_returns)
        / (np.linalg.norm(transformed) * np.linalg.norm(centered_returns))
    )
    assert hasbrouck_information_impulse(returns, signed_volume) == pytest.approx(expected)


def test_hasbrouck_information_impulse_zero_when_no_information() -> None:
    assert hasbrouck_information_impulse([], []) == 0.0


def test_build_symbol_microstructure_report_produces_dataframe() -> None:
    frame = pd.DataFrame(
        {
            "symbol": ["AAA", "AAA", "BBB"],
            "bid_volume": [1.0, 2.0, 3.0],
            "ask_volume": [1.0, 1.5, 3.0],
            "returns": [0.01, 0.02, -0.03],
            "signed_volume": [5.0, -2.0, 4.0],
        }
    )
    report = build_symbol_microstructure_report(frame)
    assert list(report.columns) == [
        "symbol",
        "samples",
        "avg_queue_imbalance",
        "kyles_lambda",
        "hasbrouck_impulse",
    ]
    assert report.loc[report["symbol"] == "AAA", "samples"].item() == 2
    assert isinstance(report.iloc[0]["avg_queue_imbalance"], float)


def test_build_symbol_microstructure_report_missing_column() -> None:
    frame = pd.DataFrame({"symbol": ["AAA"], "bid_volume": [1.0]})
    with pytest.raises(KeyError, match="Missing columns"):
        build_symbol_microstructure_report(frame)


def test_microstructure_report_dataclass_fields() -> None:
    report = MicrostructureReport(
        symbol="TEST",
        samples=3,
        avg_queue_imbalance=0.25,
        kyles_lambda=0.1,
        hasbrouck_impulse=-0.2,
    )
    assert report.symbol == "TEST"
    assert report.samples == 3
