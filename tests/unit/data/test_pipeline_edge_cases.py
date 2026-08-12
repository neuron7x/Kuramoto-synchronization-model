# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from datetime import UTC
from pathlib import Path
from typing import Any, Iterable, List

import pandas as pd
import pytest

from core.data.backfill import (
    CacheEntry,
    CacheKey,
    GapFillPlanner,
    LayerCache,
    _resolve_cadence,
)
from core.data.catalog import normalize_symbol
from core.data.materialization import (
    InMemoryCheckpointStore,
    StreamMaterializer,
)
from core.data.path_guard import DataPathGuard
from core.data.resampling import (
    _ensure_datetime_index,
    align_timeframes,
    resample_order_book,
)


def test_data_path_guard_enforces_limits(tmp_path: Path) -> None:
    payload = tmp_path / "ticks.csv"
    payload.write_text("012345", encoding="utf-8")

    with pytest.raises(ValueError, match="Maximum allowed file size"):
        DataPathGuard(allowed_roots=[tmp_path], max_bytes=0)

    guard = DataPathGuard(allowed_roots=[tmp_path], max_bytes=4)
    with pytest.raises(ValueError, match="exceeds allowed size"):
        guard.resolve(payload, description="fixture")
    assert guard.max_bytes == 4


def test_cache_entry_slice_honours_start_and_end() -> None:
    index = pd.date_range("2024-01-01", periods=4, freq="1h", tz="UTC")
    frame = pd.DataFrame({"value": range(4)}, index=index)
    entry = CacheEntry(frame=frame, start=index[0], end=index[-1])
    sliced = entry.slice(start=index[1], end=index[2])
    assert sliced.index.min() == index[1]
    assert sliced.index.max() == index[2]


def test_resolve_cadence_rejects_ambiguous_index() -> None:
    index = pd.DatetimeIndex([pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-03")])
    with pytest.raises(
        ValueError, match="Unable to determine expected_index frequency"
    ):
        _resolve_cadence(index)


def test_resolve_cadence_accepts_explicit_frequency() -> None:
    index = pd.DatetimeIndex(
        [pd.Timestamp("2024-01-01", tz=UTC), pd.Timestamp("2024-01-03", tz=UTC)]
    )
    cadence = _resolve_cadence(index, frequency="1D")
    assert cadence.n == 1
    assert cadence.name == "D"


def test_gap_fill_planner_ignores_empty_frames() -> None:
    cache = LayerCache()
    planner = GapFillPlanner(cache)
    key = CacheKey(layer="raw", symbol="BTC", venue="BINANCE", timeframe="1m")
    empty = pd.DataFrame(columns=["price"], index=pd.DatetimeIndex([], tz="UTC"))
    planner.apply(key, empty)
    assert cache.get(key).empty


class _RecordingMaterializer(StreamMaterializer):
    def __init__(
        self,
        writer,
        checkpoint_store,
        *,
        microbatch_size: int,
        dedup_keys: Iterable[str],
    ) -> None:
        super().__init__(
            writer=writer,
            checkpoint_store=checkpoint_store,
            microbatch_size=microbatch_size,
            dedup_keys=dedup_keys,
            backfill_loader=None,
        )
        self.seen_batches: List[pd.DataFrame] = []
        self.empty_batches = 0

    def _iter_batches(self, payload: pd.DataFrame | Iterable[pd.DataFrame]):
        self.empty_batches += 1
        yield pd.DataFrame(columns=list(self._dedup_keys))
        yield from super()._iter_batches(payload)

    def _deduplicate(self, frame: pd.DataFrame) -> pd.DataFrame:  # type: ignore[override]
        if "force_empty" in frame.columns:
            return pd.DataFrame(columns=frame.columns)
        return super()._deduplicate(frame)

    def _process_batch(  # type: ignore[override]
        self,
        feature_view: str,
        batch: pd.DataFrame,
        history_keys: set[tuple[Any, ...]],
    ) -> None:
        self.seen_batches.append(batch)
        return super()._process_batch(feature_view, batch, history_keys)


def test_stream_materializer_skips_empty_batches() -> None:
    writes: list[pd.DataFrame] = []
    store = InMemoryCheckpointStore()
    materializer = _RecordingMaterializer(
        writer=lambda view, frame: writes.append(frame),
        checkpoint_store=store,
        microbatch_size=10,
        dedup_keys=["entity_id"],
    )

    payload = pd.DataFrame(
        [
            {"entity_id": 1, "value": 42, "force_empty": True},
        ]
    )
    materializer.materialize("features/main", payload)

    assert writes == []
    assert materializer.empty_batches == 1
    assert len(materializer.seen_batches) == 1
    assert list(materializer._chunk_frame(pd.DataFrame())) == []
    assert store.load("features/main") is None


def test_normalize_symbol_expands_known_quotes() -> None:
    assert normalize_symbol("btceur_perp") == "BTC-EUR-PERP"


def test_resample_order_book_handles_zero_totals() -> None:
    index = pd.date_range("2024-01-01", periods=2, freq="1min")
    levels = pd.DataFrame(
        {
            "bid0": [1.0, 0.0],
            "ask0": [1.0, 0.0],
        },
        index=index,
    )
    result = resample_order_book(
        levels, freq="1min", bid_cols=["bid0"], ask_cols=["ask0"]
    )
    assert not result["imbalance"].isna().any()
    assert not result["microprice"].isna().any()


def test_resample_order_book_all_zero_levels() -> None:
    index = pd.date_range("2024-01-01", periods=3, freq="1min")
    levels = pd.DataFrame(
        {
            "bid0": [0.0, 0.0, 0.0],
            "ask0": [0.0, 0.0, 0.0],
        },
        index=index,
    )

    result = resample_order_book(
        levels, freq="1min", bid_cols=["bid0"], ask_cols=["ask0"]
    )

    assert (result["microprice"] == 0.0).all()
    assert (result["imbalance"] == 0.0).all()


def test_ensure_datetime_index_localizes_naive_index() -> None:
    frame = pd.DataFrame({"value": [1]}, index=[pd.Timestamp("2024-01-01 00:00:00")])
    converted = _ensure_datetime_index(frame)
    assert isinstance(converted.index, pd.DatetimeIndex)
    assert converted.index.tz is not None


def test_ensure_datetime_index_rejects_non_datetime_index() -> None:
    frame = pd.DataFrame({"value": [1, 2]}, index=[0, 1])
    with pytest.raises(TypeError, match="Datetim"):
        _ensure_datetime_index(frame)


def test_align_timeframes_requires_reference_frame() -> None:
    index = pd.date_range("2024-01-01", periods=2, freq="1min", tz="UTC")
    frames = {"secondary": pd.DataFrame({"value": [1, 2]}, index=index)}
    with pytest.raises(ValueError, match="reference timeframe missing"):
        align_timeframes(frames, reference="primary")
