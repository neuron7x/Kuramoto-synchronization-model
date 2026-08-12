# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Segmentation strategy for knowledge base documents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

from .models import Document, DocumentSegment


@dataclass(slots=True)
class SegmentationConfig:
    """Configuration for segmenting documents."""

    max_segment_tokens: int = 200
    overlap_tokens: int = 40

    def validate(self) -> None:
        if self.max_segment_tokens <= 0:
            raise ValueError("max_segment_tokens must be positive")
        if not 0 <= self.overlap_tokens < self.max_segment_tokens:
            raise ValueError("overlap_tokens must be in [0, max_segment_tokens)")


class DocumentSegmenter:
    """Token-count aware segmenter with optional overlap."""

    def __init__(self, config: SegmentationConfig | None = None) -> None:
        self._config = config or SegmentationConfig()
        self._config.validate()

    def segment(self, document: Document) -> List[DocumentSegment]:
        """Split ``document`` into ordered segments."""

        tokens = document.content.split()
        segments: List[DocumentSegment] = []
        offset = 0
        index = 0
        while offset < len(tokens):
            window = tokens[offset : offset + self._config.max_segment_tokens]
            text = " ".join(window)
            segment_id = f"{document.metadata.document_id}::{index}"
            segments.append(
                DocumentSegment(
                    segment_id=segment_id,
                    document_id=document.metadata.document_id,
                    order=index,
                    text=text,
                    metadata=document.metadata,
                )
            )
            offset += self._config.max_segment_tokens - self._config.overlap_tokens
            index += 1
        return segments

    def bulk_segment(self, documents: Iterable[Document]) -> List[DocumentSegment]:
        """Segment a collection of documents."""

        all_segments: List[DocumentSegment] = []
        for doc in documents:
            all_segments.extend(self.segment(doc))
        return all_segments
