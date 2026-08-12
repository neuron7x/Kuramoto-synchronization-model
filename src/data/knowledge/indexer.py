# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Index management for the knowledge search subsystem."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

import numpy as np

from .embeddings import EmbeddingProvider
from .models import IndexedSegment, IndexMaintenanceReport


class BM25Index:
    """Simple in-memory BM25 index."""

    def __init__(self, k1: float = 1.6, b: float = 0.75) -> None:
        self._k1 = k1
        self._b = b
        self._segments: Dict[str, Tuple[Counter[str], int, IndexedSegment]] = {}
        self._doc_freq: Dict[str, int] = defaultdict(int)
        self._total_length = 0

    def _tokenize(self, text: str) -> List[str]:
        return [token for token in text.lower().split() if token]

    @property
    def document_count(self) -> int:
        return len(self._segments)

    @property
    def avg_document_length(self) -> float:
        if not self._segments:
            return 0.0
        return self._total_length / len(self._segments)

    def upsert(self, segment: IndexedSegment) -> None:
        if segment.segment_id in self._segments:
            self.remove(segment.segment_id)
        tokens = self._tokenize(segment.text)
        counts = Counter(tokens)
        self._segments[segment.segment_id] = (counts, len(tokens), segment)
        self._total_length += len(tokens)
        for token in counts:
            self._doc_freq[token] += 1

    def remove(self, segment_id: str) -> None:
        record = self._segments.pop(segment_id, None)
        if not record:
            return
        counts, length, _segment = record
        self._total_length -= length
        for token in counts:
            self._doc_freq[token] -= 1
            if self._doc_freq[token] <= 0:
                del self._doc_freq[token]

    def search(self, query: str, limit: int = 10) -> List[Tuple[str, float]]:
        tokens = self._tokenize(query)
        if not tokens:
            return []
        scores: Dict[str, float] = defaultdict(float)
        avgdl = self.avg_document_length or 1.0
        for token in tokens:
            df = self._doc_freq.get(token)
            if not df:
                continue
            idf = math.log((self.document_count - df + 0.5) / (df + 0.5) + 1.0)
            for segment_id, (counts, length, _segment) in self._segments.items():
                freq = counts.get(token)
                if not freq:
                    continue
                numerator = freq * (self._k1 + 1)
                denominator = freq + self._k1 * (1 - self._b + self._b * length / avgdl)
                scores[segment_id] += idf * numerator / denominator
        return sorted(scores.items(), key=lambda item: item[1], reverse=True)[:limit]


class VectorIndex:
    """Cosine-similarity vector index."""

    def __init__(self, dimension: int) -> None:
        self._dimension = dimension
        self._vectors: Dict[str, np.ndarray] = {}

    def upsert(self, segment_id: str, vector: Sequence[float]) -> None:
        arr = np.asarray(vector, dtype=float)
        if arr.shape != (self._dimension,):
            raise ValueError(
                f"vector dimensionality mismatch: expected {self._dimension}"
            )
        norm = np.linalg.norm(arr)
        if norm > 0:
            arr = arr / norm
        self._vectors[segment_id] = arr

    def remove(self, segment_id: str) -> None:
        self._vectors.pop(segment_id, None)

    def search(
        self, vector: Sequence[float], limit: int = 10
    ) -> List[Tuple[str, float]]:
        if not self._vectors:
            return []
        query = np.asarray(vector, dtype=float)
        if query.shape != (self._dimension,):
            raise ValueError(
                f"vector dimensionality mismatch: expected {self._dimension}"
            )
        norm = np.linalg.norm(query)
        if norm > 0:
            query = query / norm
        scores: List[Tuple[str, float]] = []
        for segment_id, stored in self._vectors.items():
            scores.append((segment_id, float(np.dot(stored, query))))
        scores.sort(key=lambda item: item[1], reverse=True)
        return scores[:limit]


@dataclass
class HybridIndexConfig:
    """Configuration for the :class:`HybridIndex`."""

    bm25_weight: float = 0.55
    vector_weight: float = 0.45
    candidate_multiplier: int = 3

    def validate(self) -> None:
        if self.bm25_weight <= 0 and self.vector_weight <= 0:
            raise ValueError("At least one weight must be positive")
        if self.candidate_multiplier < 1:
            raise ValueError("candidate_multiplier must be >= 1")


class HybridIndex:
    """Coordinate BM25 and vector indexes across shards."""

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        config: HybridIndexConfig | None = None,
    ) -> None:
        self._embedding_provider = embedding_provider
        self._config = config or HybridIndexConfig()
        self._config.validate()
        self._bm25_by_shard: Dict[str, BM25Index] = defaultdict(BM25Index)
        self._vector_by_shard: Dict[str, VectorIndex] = {}
        self._segments: Dict[str, IndexedSegment] = {}

    def _ensure_vector_index(self, shard_key: str) -> VectorIndex:
        index = self._vector_by_shard.get(shard_key)
        if index is None:
            index = VectorIndex(self._embedding_provider.dimension)
            self._vector_by_shard[shard_key] = index
        return index

    def upsert(self, segment: IndexedSegment) -> None:
        self._segments[segment.segment_id] = segment
        bm25 = self._bm25_by_shard[segment.shard_key]
        bm25.upsert(segment)
        vector_index = self._ensure_vector_index(segment.shard_key)
        vector_index.upsert(segment.segment_id, segment.vector)

    def remove(self, segment_id: str) -> None:
        segment = self._segments.pop(segment_id, None)
        if not segment:
            return
        self._bm25_by_shard[segment.shard_key].remove(segment.segment_id)
        vector_index = self._vector_by_shard.get(segment.shard_key)
        if vector_index:
            vector_index.remove(segment.segment_id)

    def maintenance(
        self,
        segments: Iterable[IndexedSegment],
        documents_replaced: Iterable[str] | None = None,
    ) -> IndexMaintenanceReport:
        updated = 0
        shards_touched: set[str] = set()
        known_ids = set()
        replaced_documents = set(documents_replaced or [])
        for segment in segments:
            self.upsert(segment)
            updated += 1
            known_ids.add(segment.segment_id)
            shards_touched.add(segment.shard_key)
            replaced_documents.add(segment.document_id)
        removed = 0
        if replaced_documents:
            for segment_id, segment in list(self._segments.items()):
                if (
                    segment.document_id in replaced_documents
                    and segment_id not in known_ids
                ):
                    self.remove(segment_id)
                    removed += 1
        return IndexMaintenanceReport(
            updated_segments=updated,
            removed_segments=removed,
            shards_touched=sorted(shards_touched),
        )

    def search(self, query: str, limit: int = 10) -> List[Tuple[IndexedSegment, float]]:
        if not query.strip():
            return []
        candidate_limit = max(limit * self._config.candidate_multiplier, limit)
        bm25_scores: Dict[str, float] = defaultdict(float)
        vector_scores: Dict[str, float] = defaultdict(float)

        for shard, bm25 in self._bm25_by_shard.items():
            candidates = bm25.search(query, limit=candidate_limit)
            for segment_id, score in candidates:
                bm25_scores[segment_id] = max(bm25_scores.get(segment_id, 0.0), score)

        query_vector = self._embedding_provider.embed(query)
        for shard, vector_index in self._vector_by_shard.items():
            candidates = vector_index.search(query_vector, limit=candidate_limit)
            for segment_id, score in candidates:
                vector_scores[segment_id] = max(
                    vector_scores.get(segment_id, 0.0), score
                )

        combined: Dict[str, float] = defaultdict(float)
        for segment_id, score in bm25_scores.items():
            combined[segment_id] += score * self._config.bm25_weight
        for segment_id, score in vector_scores.items():
            combined[segment_id] += score * self._config.vector_weight

        ranked = sorted(combined.items(), key=lambda item: item[1], reverse=True)[
            :candidate_limit
        ]
        results: List[Tuple[IndexedSegment, float]] = []
        for segment_id, score in ranked[:limit]:
            segment = self._segments.get(segment_id)
            if segment is None:
                continue
            results.append((segment, score))
        return results

    @property
    def segments(self) -> Mapping[str, IndexedSegment]:
        return self._segments
