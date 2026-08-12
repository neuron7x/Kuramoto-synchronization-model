# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Light-weight embedding provider for deterministic vector creation."""

from __future__ import annotations

import hashlib
from typing import Iterable, Sequence

import numpy as np

from .models import DocumentSegment


class EmbeddingProvider:
    """Generate deterministic embeddings without external dependencies."""

    def __init__(self, dimension: int = 384) -> None:
        if dimension <= 0:
            raise ValueError("dimension must be positive")
        self._dimension = dimension

    def embed(self, text: str) -> np.ndarray:
        tokens = text.lower().split()
        if not tokens:
            return np.zeros(self._dimension, dtype=float)
        vector = np.zeros(self._dimension, dtype=float)
        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=32).digest()
            for idx in range(0, len(digest), 2):
                position = digest[idx] % self._dimension
                value = digest[idx + 1] / 255.0
                vector[position] += value
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector /= norm
        return vector

    def embed_segment(self, segment: DocumentSegment) -> np.ndarray:
        return self.embed(segment.text)

    def bulk_embed(self, segments: Iterable[DocumentSegment]) -> Sequence[np.ndarray]:
        return [self.embed_segment(segment) for segment in segments]

    @property
    def dimension(self) -> int:
        return self._dimension
