"""Shard assignment utilities for knowledge segments."""

from __future__ import annotations

import hashlib
from typing import Iterable, Mapping

from .models import DocumentSegment


class ShardManager:
    """Assign segments to shards for scalable indexing."""

    def __init__(self, shard_weights: Mapping[str, int] | None = None) -> None:
        self._shard_weights = dict(shard_weights or {"default": 1})
        if not self._shard_weights:
            raise ValueError("At least one shard must be configured")
        self._total_weight = sum(self._shard_weights.values())
        if self._total_weight <= 0:
            raise ValueError("Shard weights must be positive")
        self._sorted_shards = sorted(self._shard_weights.items())

    def shard_key(self, segment: DocumentSegment) -> str:
        digest = hashlib.blake2b(
            segment.segment_id.encode("utf-8"), digest_size=8
        ).digest()
        value = int.from_bytes(digest, "big") % self._total_weight
        cumulative = 0
        for shard, weight in self._sorted_shards:
            cumulative += weight
            if value < cumulative:
                return shard
        return self._sorted_shards[-1][0]

    def assign(
        self, segments: Iterable[DocumentSegment]
    ) -> Mapping[str, list[DocumentSegment]]:
        buckets: dict[str, list[DocumentSegment]] = {
            shard: [] for shard in self._shard_weights
        }
        for segment in segments:
            shard = self.shard_key(segment)
            buckets.setdefault(shard, []).append(segment)
        return buckets
