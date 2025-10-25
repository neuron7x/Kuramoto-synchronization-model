from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from src.data.knowledge.cache import AnswerCache
from src.data.knowledge.models import DocumentMetadata, SearchResult


@dataclass
class _ControlledClock:
    """Deterministic clock used to exercise cache expiry semantics."""

    current: datetime

    def advance(self, delta: timedelta) -> datetime:
        self.current += delta
        return self.current

    def __call__(self) -> datetime:
        return self.current


def _make_result(document_id: str) -> SearchResult:
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    metadata = DocumentMetadata(
        document_id=document_id,
        source="unit-test",
        created_at=base,
        updated_at=base,
    )
    return SearchResult(
        document_id=document_id,
        segment_id=f"{document_id}-seg",
        text=f"payload for {document_id}",
        score=1.0,
        citations=(),
        metadata=metadata,
    )


def test_answer_cache_purges_expired_entries_on_set() -> None:
    clock = _ControlledClock(datetime(2024, 1, 1, tzinfo=timezone.utc))
    cache = AnswerCache(max_entries=5, ttl=timedelta(seconds=30), clock=clock)

    cache.set("alpha", (_make_result("doc-alpha"),))
    assert len(cache) == 1

    clock.advance(timedelta(seconds=45))
    cache.set("beta", (_make_result("doc-beta"),))

    assert len(cache) == 1, "stale entries should be purged eagerly"
    assert cache.get("alpha") is None

    beta_results = cache.get("beta")
    assert beta_results is not None
    assert beta_results[0].document_id == "doc-beta"


def test_answer_cache_respects_max_entries_after_purge() -> None:
    clock = _ControlledClock(datetime(2024, 1, 1, tzinfo=timezone.utc))
    cache = AnswerCache(max_entries=2, ttl=timedelta(seconds=15), clock=clock)

    cache.set("first", (_make_result("doc-first"),))
    cache.set("second", (_make_result("doc-second"),))
    assert len(cache) == 2

    clock.advance(timedelta(seconds=12))
    cache.set("third", (_make_result("doc-third"),))

    assert len(cache) == 2
    assert cache.get("first") is None
    assert cache.get("second") is not None
    assert cache.get("third") is not None
