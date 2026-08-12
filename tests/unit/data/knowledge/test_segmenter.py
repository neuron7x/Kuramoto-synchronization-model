# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.data.knowledge.models import Document, DocumentMetadata
from src.data.knowledge.segmenter import (
    DocumentSegmenter,
    SegmentationConfig,
)


def _make_document(*, document_id: str, content: str) -> Document:
    timestamp = datetime(2024, 1, 1, tzinfo=timezone.utc)
    metadata = DocumentMetadata(
        document_id=document_id,
        source="unit-test",
        created_at=timestamp,
        updated_at=timestamp,
        priority=1.0,
        tags=("alpha", "beta"),
        attributes={"owner": "qa"},
    )
    return Document(metadata=metadata, content=content)


def test_segmenter_respects_token_window_and_overlap() -> None:
    segmenter = DocumentSegmenter(
        SegmentationConfig(max_segment_tokens=5, overlap_tokens=2)
    )
    doc = _make_document(
        document_id="doc-1",
        content=" ".join(f"token-{i}" for i in range(12)),
    )

    segments = segmenter.segment(doc)

    assert [segment.order for segment in segments] == list(range(4))
    assert all(segment.metadata is doc.metadata for segment in segments)
    assert [segment.segment_id for segment in segments] == [
        "doc-1::0",
        "doc-1::1",
        "doc-1::2",
        "doc-1::3",
    ]
    segment_texts = [segment.text.split() for segment in segments]
    assert segment_texts[0] == [f"token-{i}" for i in range(5)]
    assert segment_texts[1][0] == "token-3"
    assert segment_texts[1][-1] == "token-7"
    assert segment_texts[2][0] == "token-6"
    assert segment_texts[3][0] == "token-9"
    assert segment_texts[3][-1] == "token-11"


def test_bulk_segment_concatenates_results_in_document_order() -> None:
    segmenter = DocumentSegmenter(
        SegmentationConfig(max_segment_tokens=3, overlap_tokens=0)
    )
    doc_a = _make_document(document_id="doc-A", content="one two three four")
    doc_b = _make_document(document_id="doc-B", content="five six seven eight")

    segments = segmenter.bulk_segment([doc_a, doc_b])

    assert [segment.document_id for segment in segments] == [
        "doc-A",
        "doc-A",
        "doc-B",
        "doc-B",
    ]
    assert [segment.order for segment in segments] == [0, 1, 0, 1]
    assert segments[0].text == "one two three"
    assert segments[1].text == "four"
    assert segments[2].text == "five six seven"
    assert segments[3].text == "eight"


def test_segmentation_config_validation_guards_invalid_values() -> None:
    with pytest.raises(ValueError, match="max_segment_tokens"):
        SegmentationConfig(max_segment_tokens=0).validate()

    with pytest.raises(ValueError, match="overlap_tokens"):
        SegmentationConfig(max_segment_tokens=5, overlap_tokens=5).validate()

    # Acceptable configuration should not raise
    cfg = SegmentationConfig(max_segment_tokens=5, overlap_tokens=4)
    cfg.validate()
