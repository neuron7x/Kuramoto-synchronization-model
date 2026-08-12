# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for :mod:`src.data.knowledge.sharding`."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.data.knowledge.models import DocumentMetadata, DocumentSegment
from src.data.knowledge.sharding import ShardManager


@pytest.fixture()
def metadata() -> DocumentMetadata:
    """Return consistent document metadata for constructing segments."""

    timestamp = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return DocumentMetadata(
        document_id="doc-1",
        source="unit-test",
        created_at=timestamp,
        updated_at=timestamp,
    )


def make_segment(
    segment_id: str, metadata: DocumentMetadata, *, order: int = 0
) -> DocumentSegment:
    return DocumentSegment(
        segment_id=segment_id,
        document_id=metadata.document_id,
        order=order,
        text="sample",
        metadata=metadata,
    )


def test_shard_manager_requires_positive_total_weight() -> None:
    with pytest.raises(ValueError):
        ShardManager({"alpha": 0})

    with pytest.raises(ValueError):
        ShardManager({"alpha": -2, "beta": 1})


def test_shard_key_is_deterministic(metadata: DocumentMetadata) -> None:
    manager = ShardManager({"alpha": 1, "beta": 2})
    segment = make_segment("segment-5", metadata)

    first = manager.shard_key(segment)
    second = manager.shard_key(segment)

    assert first == "alpha"
    assert first == second


def test_assign_groups_segments_by_computed_shard(metadata: DocumentMetadata) -> None:
    manager = ShardManager({"alpha": 1, "beta": 2})
    segments = [
        make_segment("segment-0", metadata, order=0),
        make_segment("segment-5", metadata, order=1),
        make_segment("segment-6", metadata, order=2),
    ]

    assignments = manager.assign(segments)

    assert set(assignments.keys()) == {"alpha", "beta"}
    assert {segment.segment_id for segment in assignments["alpha"]} == {"segment-5"}
    assert {segment.segment_id for segment in assignments["beta"]} == {
        "segment-0",
        "segment-6",
    }
