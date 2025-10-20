"""Caching of previous answers to accelerate repeated lookups."""

from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import MutableMapping, Sequence

from .models import AnswerCacheEntry, SearchResult


class AnswerCache:
    """Time-aware LRU cache for search responses."""

    def __init__(self, max_entries: int = 256, ttl: timedelta | None = timedelta(minutes=10)) -> None:
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self._max_entries = max_entries
        self._ttl = ttl
        self._entries: MutableMapping[str, AnswerCacheEntry] = OrderedDict()

    def _evict(self) -> None:
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def _is_expired(self, entry: AnswerCacheEntry) -> bool:
        if self._ttl is None:
            return False
        return datetime.now(timezone.utc) - entry.created_at > self._ttl

    def get(self, fingerprint: str) -> Sequence[SearchResult] | None:
        entry = self._entries.get(fingerprint)
        if entry is None:
            return None
        if self._is_expired(entry):
            self._entries.pop(fingerprint, None)
            return None
        self._entries.move_to_end(fingerprint)
        return entry.results

    def set(self, fingerprint: str, results: Sequence[SearchResult]) -> None:
        self._entries[fingerprint] = AnswerCacheEntry(
            query_fingerprint=fingerprint,
            created_at=datetime.now(timezone.utc),
            results=tuple(results),
        )
        self._entries.move_to_end(fingerprint)
        self._evict()

    def clear(self) -> None:
        self._entries.clear()

    @property
    def max_entries(self) -> int:
        return self._max_entries

    @property
    def ttl(self) -> timedelta | None:
        return self._ttl
