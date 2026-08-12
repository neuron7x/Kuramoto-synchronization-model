# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import time
from datetime import UTC

import pandas as pd
import pytest

from core.data.materialization import (
    Checkpoint,
    InMemoryCheckpointStore,
    StreamMaterializer,
)


@pytest.fixture
def stream_payload() -> pd.DataFrame:
    ts = pd.Timestamp("2024-01-01 00:00:00", tz=UTC)
    return pd.DataFrame(
        {
            "entity_id": ["a", "a", "b", "b"],
            "ts": [
                ts,
                ts,
                ts - pd.Timedelta(minutes=1),
                ts + pd.Timedelta(minutes=1),
            ],
            "value": [1.0, 1.0, 2.0, 3.0],
        }
    )


def test_microbatch_checkpointing(stream_payload: pd.DataFrame) -> None:
    checkpoint_store = InMemoryCheckpointStore()
    written: list[pd.DataFrame] = []

    def writer(_name: str, frame: pd.DataFrame) -> None:
        written.append(frame.copy())

    materializer = StreamMaterializer(
        writer,
        checkpoint_store,
        microbatch_size=2,
        dedup_keys=("entity_id", "ts"),
        backfill_loader=lambda _: pd.DataFrame(
            {
                "entity_id": ["c"],
                "ts": [pd.Timestamp("2023-12-31 23:59:00", tz=UTC)],
                "value": [9.0],
            }
        ),
    )

    materializer.materialize("features.demo", stream_payload)

    assert len(written) == 2
    # Backfill row is merged with each batch; ensure dedup keeps latest.
    assert all("c" not in batch["entity_id"].values for batch in written)
    assert all(batch["entity_id"].isin(["a", "b"]).all() for batch in written)

    # Replaying the same payload must be idempotent.
    materializer.materialize("features.demo", stream_payload)
    assert len(written) == 2
    checkpoint = checkpoint_store.load("features.demo")
    assert isinstance(checkpoint, Checkpoint)
    assert len(checkpoint.checkpoint_ids) == 2


def test_refresh_history_keys_between_batches() -> None:
    checkpoint_store = InMemoryCheckpointStore()
    writes: list[pd.DataFrame] = []

    materializer = StreamMaterializer(
        lambda _name, frame: writes.append(frame.copy()),
        checkpoint_store,
        microbatch_size=10,
    )

    first = pd.DataFrame(
        {
            "entity_id": ["dup"],
            "ts": [pd.Timestamp("2024-01-01 00:00:00", tz=UTC)],
            "value": [1.0],
        }
    )
    second = pd.DataFrame(
        {
            "entity_id": ["dup"],
            "ts": [pd.Timestamp("2024-01-01 00:00:00", tz=UTC)],
            "value": [1.0],
        }
    )

    materializer.materialize("features.demo", [first, second])

    assert len(writes) == 1
    assert writes[0].equals(first.reset_index(drop=True))


def test_deduplicate_requires_keys(stream_payload: pd.DataFrame) -> None:
    checkpoint_store = InMemoryCheckpointStore()

    materializer = StreamMaterializer(
        lambda *_: None,
        checkpoint_store,
        microbatch_size=2,
        dedup_keys=("entity_id", "ts"),
    )

    with pytest.raises(KeyError):
        bad_payload = stream_payload.drop(columns=["ts"])
        materializer.materialize("features.demo", bad_payload)


def test_materializer_configuration_guards() -> None:
    checkpoint_store = InMemoryCheckpointStore()

    with pytest.raises(ValueError):
        StreamMaterializer(lambda *_: None, checkpoint_store, microbatch_size=0)

    with pytest.raises(ValueError):
        StreamMaterializer(lambda *_: None, checkpoint_store, dedup_keys=())


def test_materialize_accepts_iterable_batches(stream_payload: pd.DataFrame) -> None:
    checkpoint_store = InMemoryCheckpointStore()
    writes: list[pd.DataFrame] = []

    materializer = StreamMaterializer(
        lambda _name, frame: writes.append(frame.copy()),
        checkpoint_store,
        microbatch_size=3,
    )

    materializer.materialize("features.demo", [stream_payload])
    assert writes


def test_backfill_only_updates_checkpoint(stream_payload: pd.DataFrame) -> None:
    checkpoint_store = InMemoryCheckpointStore()
    writes: list[pd.DataFrame] = []

    deduped = stream_payload.sort_values(
        by=["entity_id", "ts"], kind="mergesort"
    ).drop_duplicates(["entity_id", "ts"], keep="last")

    materializer = StreamMaterializer(
        lambda _name, frame: writes.append(frame.copy()),
        checkpoint_store,
        backfill_loader=lambda _name: deduped,
    )

    materializer.materialize("features.demo", stream_payload)
    assert writes == []
    checkpoint = checkpoint_store.load("features.demo")
    assert checkpoint is not None
    assert len(checkpoint.checkpoint_ids) == 1


def test_backfill_loader_called_once(stream_payload: pd.DataFrame) -> None:
    checkpoint_store = InMemoryCheckpointStore()
    writes: list[pd.DataFrame] = []
    loader_calls: list[int] = []

    def loader(_name: str) -> pd.DataFrame:
        loader_calls.append(1)
        return stream_payload.iloc[0:0]

    materializer = StreamMaterializer(
        lambda _name, frame: writes.append(frame.copy()),
        checkpoint_store,
        microbatch_size=1,
        backfill_loader=loader,
    )

    materializer.materialize("features.demo", stream_payload)

    assert len(loader_calls) == 1
    expected_batches = len(stream_payload.drop_duplicates(["entity_id", "ts"]))
    assert len(writes) == expected_batches


def test_checkpoint_add_does_not_mutate_original() -> None:
    checkpoint = Checkpoint("demo", frozenset({"one"}))
    updated = checkpoint.add("two")

    assert checkpoint is not updated
    assert checkpoint.checkpoint_ids == frozenset({"one"})
    assert updated.checkpoint_ids == frozenset({"one", "two"})


def test_materializer_recovers_from_partial_write(stream_payload: pd.DataFrame) -> None:
    checkpoint_store = InMemoryCheckpointStore()
    persisted_batches: list[pd.DataFrame] = []
    failure_injected = {"active": True}

    def writer(_name: str, frame: pd.DataFrame) -> None:
        persisted_batches.append(frame.copy())
        if failure_injected["active"]:
            failure_injected["active"] = False
            raise ConnectionError("simulated database outage")

    def load_persisted(_name: str) -> pd.DataFrame:
        if not persisted_batches:
            return pd.DataFrame(columns=stream_payload.columns)
        return pd.concat(persisted_batches, ignore_index=True)

    materializer = StreamMaterializer(
        writer,
        checkpoint_store,
        microbatch_size=2,
        backfill_loader=load_persisted,
    )

    with pytest.raises(ConnectionError):
        materializer.materialize("features.demo", stream_payload)

    assert checkpoint_store.load("features.demo") is None

    materializer.materialize("features.demo", stream_payload)

    assert len(persisted_batches) == 2
    combined = pd.concat(persisted_batches, ignore_index=True)
    deduped = (
        combined.sort_values(by=["entity_id", "ts"], kind="mergesort")
        .drop_duplicates(["entity_id", "ts"], keep="last")
        .reset_index(drop=True)
    )
    expected = (
        stream_payload.sort_values(by=["entity_id", "ts"], kind="mergesort")
        .drop_duplicates(["entity_id", "ts"], keep="last")
        .reset_index(drop=True)
    )
    pd.testing.assert_frame_equal(deduped, expected)

    checkpoint = checkpoint_store.load("features.demo")
    assert checkpoint is not None
    assert len(checkpoint.checkpoint_ids) == 2


def test_materializer_handles_slow_writer(
    monkeypatch: pytest.MonkeyPatch, stream_payload: pd.DataFrame
) -> None:
    checkpoint_store = InMemoryCheckpointStore()
    writes: list[pd.DataFrame] = []
    sleep_calls: list[float] = []

    monkeypatch.setattr(time, "sleep", lambda seconds: sleep_calls.append(seconds))

    def writer(_name: str, frame: pd.DataFrame) -> None:
        time.sleep(0.01)
        writes.append(frame.copy())

    materializer = StreamMaterializer(writer, checkpoint_store, microbatch_size=2)
    materializer.materialize("features.demo", stream_payload)

    assert len(writes) == 2
    assert sleep_calls == [0.01, 0.01]
