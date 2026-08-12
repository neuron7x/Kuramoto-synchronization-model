# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import pandas as pd
import pytest

from core.data.feature_store import FeatureStoreIntegrityError, OnlineFeatureStore
from core.utils import dataframe_io


def _frame(values: list[int]) -> pd.DataFrame:
    return pd.DataFrame(
        {"timestamp": values, "alpha": [float(v) * 0.1 for v in values]}
    )


def test_overwrite_mode_purges_existing_store(tmp_path):
    store = OnlineFeatureStore(tmp_path)
    initial = _frame([1, 2, 3])
    store.sync("live.features", initial, mode="overwrite")

    new_payload = _frame([10, 11])
    store.sync("live.features", new_payload, mode="overwrite")

    stored = store.load("live.features")
    pd.testing.assert_frame_equal(
        stored.reset_index(drop=True), new_payload.reset_index(drop=True)
    )


def test_integrity_report_detects_row_and_hash_mismatches(tmp_path):
    store = OnlineFeatureStore(tmp_path)
    payload = _frame([1, 2, 3])
    store.sync("risk.alpha", payload, mode="overwrite")

    report = store.compute_integrity("risk.alpha", payload)
    assert report.row_count_diff == 0
    assert report.hash_differs is False
    report.ensure_valid()

    corrupted = payload.iloc[:-1]
    bad_report = store.compute_integrity("risk.alpha", corrupted)
    assert bad_report.row_count_diff != 0
    assert bad_report.hash_differs is True
    with pytest.raises(FeatureStoreIntegrityError):
        bad_report.ensure_valid()


def test_overwrite_calls_purge(tmp_path, monkeypatch):
    store = OnlineFeatureStore(tmp_path)
    store.sync("signals", _frame([1]), mode="overwrite")

    calls: list[str] = []

    original = store.purge

    def tracked(name: str) -> None:
        calls.append(name)
        original(name)

    monkeypatch.setattr(store, "purge", tracked)
    store.sync("signals", _frame([2, 3]), mode="overwrite")

    assert calls == ["signals"]


def test_polars_fallback_without_pyarrow(monkeypatch, tmp_path):
    pytest.importorskip("polars")
    dataframe_io.reset_dataframe_io_backends()
    monkeypatch.setattr(dataframe_io, "_pyarrow_available", lambda: False)

    store = OnlineFeatureStore(tmp_path)
    payload = _frame([5, 6, 7])
    store.sync("alt.features", payload, mode="overwrite")

    stored = store.load("alt.features")
    pd.testing.assert_frame_equal(
        stored.reset_index(drop=True), payload.reset_index(drop=True)
    )

    parquet_path = (tmp_path / "alt.features").with_suffix(".parquet")
    assert parquet_path.exists()


def test_json_fallback_when_no_parquet_backend(monkeypatch, tmp_path):
    dataframe_io.reset_dataframe_io_backends()
    monkeypatch.setattr(dataframe_io, "_pyarrow_available", lambda: False)

    def _only_json() -> list:
        return [dataframe_io._json_backend()]

    monkeypatch.setattr(dataframe_io, "_available_backends", _only_json)

    store = OnlineFeatureStore(tmp_path)
    payload = _frame([9, 10])
    store.sync("json.features", payload, mode="overwrite")

    stored = store.load("json.features")
    pd.testing.assert_frame_equal(
        stored.reset_index(drop=True), payload.reset_index(drop=True)
    )

    json_path = store._resolve_path("json.features").with_suffix(".json")
    assert json_path.exists()
