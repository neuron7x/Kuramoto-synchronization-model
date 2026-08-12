# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Caching of previous answers to accelerate repeated lookups."""

from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Callable, MutableMapping, Sequence

from .models import AnswerCacheEntry, SearchResult


class AnswerCache:
    """Time-aware LRU cache for search responses."""

    def __init__(
        self,
        max_entries: int = 256,
        ttl: timedelta | None = timedelta(minutes=10),
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self._max_entries = max_entries
        self._ttl = ttl
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._entries: MutableMapping[str, AnswerCacheEntry] = OrderedDict()

    def _now(self) -> datetime:
        moment = self._clock()
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        else:
            moment = moment.astimezone(timezone.utc)
        return moment

    def _evict(self) -> None:
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def _is_expired(
        self, entry: AnswerCacheEntry, *, now: datetime | None = None
    ) -> bool:
        if self._ttl is None:
            return False
        reference = now or self._now()
        return reference - entry.created_at > self._ttl

    def _purge_expired(self, *, now: datetime | None = None) -> None:
        if self._ttl is None or not self._entries:
            return
        reference = now or self._now()
        expired_keys = [
            key
            for key, entry in list(self._entries.items())
            if self._is_expired(entry, now=reference)
        ]
        for key in expired_keys:
            self._entries.pop(key, None)

    def get(self, fingerprint: str) -> Sequence[SearchResult] | None:
        entry = self._entries.get(fingerprint)
        if entry is None:
            return None
        now = self._now()
        if self._is_expired(entry, now=now):
            self._entries.pop(fingerprint, None)
            return None
        self._entries.move_to_end(fingerprint)
        return entry.results

    def set(self, fingerprint: str, results: Sequence[SearchResult]) -> None:
        now = self._now()
        self._entries[fingerprint] = AnswerCacheEntry(
            query_fingerprint=fingerprint,
            created_at=now,
            results=tuple(results),
        )
        self._entries.move_to_end(fingerprint)
        self._purge_expired(now=now)
        self._evict()

    def clear(self) -> None:
        self._entries.clear()

    @property
    def max_entries(self) -> int:
        return self._max_entries

    @property
    def ttl(self) -> timedelta | None:
        return self._ttl

    def __len__(self) -> int:
        return len(self._entries)
