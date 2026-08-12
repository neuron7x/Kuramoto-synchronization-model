# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Compression utilities for storing document segments efficiently."""

from __future__ import annotations

import zlib
from typing import Iterable, List

from .models import CompressedSegment, DocumentSegment


class SegmentCompressor:
    """Compress and decompress segments using ``zlib``."""

    def compress(self, segment: DocumentSegment) -> CompressedSegment:
        payload = zlib.compress(segment.text.encode("utf-8"), level=9)
        return CompressedSegment(
            segment_id=segment.segment_id,
            document_id=segment.document_id,
            payload=payload,
            metadata=segment.metadata,
        )

    def decompress(self, compressed: CompressedSegment) -> DocumentSegment:
        text = zlib.decompress(compressed.payload).decode("utf-8")
        return DocumentSegment(
            segment_id=compressed.segment_id,
            document_id=compressed.document_id,
            order=int(compressed.segment_id.split("::")[-1]),
            text=text,
            metadata=compressed.metadata,
        )

    def bulk_compress(
        self, segments: Iterable[DocumentSegment]
    ) -> List[CompressedSegment]:
        return [self.compress(seg) for seg in segments]

    def bulk_decompress(
        self, segments: Iterable[CompressedSegment]
    ) -> List[DocumentSegment]:
        return [self.decompress(seg) for seg in segments]
