# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from core.indicators.cache import (
    FileSystemIndicatorCache,
    cache_indicator,
    hash_input_data,
    make_fingerprint,
)
from core.indicators.multiscale_kuramoto import (
    MultiScaleKuramoto,
    MultiScaleKuramotoFeature,
    TimeFrame,
)


def test_make_fingerprint_varies_with_params() -> None:
    params_a = {"period": 14}
    params_b = {"period": 28}
    data_hash = "abc123"
    version = "1.0.0"

    fp_a = make_fingerprint("rsi", params_a, data_hash, version)
    fp_b = make_fingerprint("rsi", params_b, data_hash, version)

    assert fp_a != fp_b


def test_filesystem_cache_roundtrip(tmp_path: Path) -> None:
    cache = FileSystemIndicatorCache(tmp_path)
    payload = np.array([1.0, 2.0, 3.0])
    params = {"alpha": 0.5}
    data_hash = hash_input_data(payload)

    fingerprint = cache.store(
        indicator_name="test_indicator",
        params=params,
        data_hash=data_hash,
        value=payload,
        metadata={"unit": "test"},
    )

    record = cache.load(
        indicator_name="test_indicator",
        params=params,
        data_hash=data_hash,
    )

    assert record is not None
    assert record.fingerprint == fingerprint
    assert np.array_equal(record.value, payload)
    assert record.metadata == {"unit": "test"}


def test_cache_detects_tampering(tmp_path: Path) -> None:
    cache = FileSystemIndicatorCache(tmp_path)
    params = {"alpha": 0.1}
    data = [1, 2, 3]
    data_hash = hash_input_data(data)

    fingerprint = cache.store(
        indicator_name="malicious", params=params, data_hash=data_hash, value=data
    )

    entry_dir = tmp_path / "_global" / fingerprint
    payload_path = next(entry_dir.glob("payload.*"))
    payload_path.write_bytes(b"tampered")

    record = cache.load(
        indicator_name="malicious",
        params=params,
        data_hash=data_hash,
    )

    assert record is None


def test_backfill_state_roundtrip(tmp_path: Path) -> None:
    cache = FileSystemIndicatorCache(tmp_path)
    cache.update_backfill_state(
        TimeFrame.M1,
        last_timestamp="2024-01-01T00:01:00+00:00",
        fingerprint="finger",
        extras={"records": 120},
    )

    state = cache.get_backfill_state(TimeFrame.M1)
    assert state is not None
    assert state.timeframe == "M1"
    assert state.fingerprint == "finger"
    assert state.extras["records"] == 120


def test_cache_indicator_decorator(tmp_path: Path) -> None:
    cache = FileSystemIndicatorCache(tmp_path)
    calls: list[int] = []

    @cache_indicator(cache, indicator_name="square")
    def square(values: list[int]) -> list[int]:
        calls.append(1)
        return [v * v for v in values]

    data = [1, 2, 3]
    first = square(data)
    second = square(list(data))

    assert first == [1, 4, 9]
    assert second == first
    assert len(calls) == 1


class TrackingAnalyzer(MultiScaleKuramoto):
    def __init__(self) -> None:
        super().__init__(timeframes=(TimeFrame.M1,), use_adaptive_window=False, base_window=64)
        self.calls = 0

    def analyze(self, df: pd.DataFrame, *, price_col: str = "close"):
        self.calls += 1
        return super().analyze(df, price_col=price_col)


def _synthetic_prices(periods: int = 512) -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=periods, freq="1min", tz="UTC")
    prices = 100 + np.sin(np.linspace(0, 20, periods))
    return pd.DataFrame({"close": prices}, index=index)


def test_multiscale_feature_uses_cache(tmp_path: Path) -> None:
    cache = FileSystemIndicatorCache(tmp_path)
    analyzer = TrackingAnalyzer()
    feature = MultiScaleKuramotoFeature(analyzer=analyzer, cache=cache)
    df = _synthetic_prices()

    first = feature.transform(df)
    second = feature.transform(df.copy())

    assert first.value == pytest.approx(second.value, rel=1e-12)
    assert analyzer.calls == 1

    state = cache.get_backfill_state(TimeFrame.M1)
    assert state is not None
    assert state.last_timestamp is not None


def test_cache_preserves_dataframe_index(tmp_path: Path) -> None:
    cache = FileSystemIndicatorCache(tmp_path)
    index = pd.date_range("2024-01-01", periods=5, freq="1min", tz="UTC")
    frame = pd.DataFrame({"value": range(5)}, index=index)
    params = {"alpha": 0.9}
    data_hash = hash_input_data(frame.to_numpy())

    cache.store(
        indicator_name="df_indicator",
        params=params,
        data_hash=data_hash,
        value=frame,
    )

    record = cache.load(
        indicator_name="df_indicator",
        params=params,
        data_hash=data_hash,
    )

    assert record is not None
    assert isinstance(record.value, pd.DataFrame)
    pd.testing.assert_frame_equal(record.value, frame, check_freq=False)
