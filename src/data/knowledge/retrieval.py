"""Hybrid retrieval logic combining lexical and vector scores."""

from __future__ import annotations

import hashlib
from typing import Mapping, Sequence

from .cache import AnswerCache
from .graph import KnowledgeGraph
from .indexer import HybridIndex
from .models import CompletenessReport, SearchQuery, SearchResult
from .validators import CitationBuilder, CompletenessController, FreshnessPolicy


class SourcePrioritizer:
    """Apply per-source weighting during ranking."""

    def __init__(self, weights: Mapping[str, float] | None = None) -> None:
        self._weights = dict(weights or {})

    def weight(self, source: str) -> float:
        return self._weights.get(source, 1.0)


class HybridSearchEngine:
    """Coordinate ranking policies for hybrid retrieval."""

    def __init__(
        self,
        index: HybridIndex,
        freshness_policy: FreshnessPolicy,
        citation_builder: CitationBuilder,
        completeness_controller: CompletenessController,
        answer_cache: AnswerCache,
        knowledge_graph: KnowledgeGraph,
        source_prioritizer: SourcePrioritizer | None = None,
    ) -> None:
        self._index = index
        self._freshness = freshness_policy
        self._citation_builder = citation_builder
        self._completeness = completeness_controller
        self._cache = answer_cache
        self._graph = knowledge_graph
        self._prioritizer = source_prioritizer or SourcePrioritizer()

    def _fingerprint(self, query: SearchQuery) -> str:
        hasher = hashlib.blake2s(digest_size=16)
        hasher.update(query.text.encode("utf-8"))
        hasher.update(str(sorted(query.tags)).encode("utf-8"))
        hasher.update(str(query.limit).encode("utf-8"))
        hasher.update(str(query.freshness_horizon).encode("utf-8"))
        return hasher.hexdigest()

    def _score_tags(
        self, result_tags: Sequence[str], query_tags: Sequence[str]
    ) -> float:
        if not query_tags:
            return 1.0
        overlap = len(set(result_tags) & set(query_tags))
        if overlap == 0:
            return 0.8
        return 1.0 + 0.15 * overlap

    def _authority_bonus(self, document_id: str) -> float:
        backlinks = len(self._graph.backlinks(document_id))
        references = len(self._graph.references(document_id))
        return 1.0 + min(backlinks + references, 10) * 0.03

    def search(
        self, query: SearchQuery
    ) -> tuple[Sequence[SearchResult], CompletenessReport]:
        fingerprint = self._fingerprint(query)
        cached = self._cache.get(fingerprint)
        if cached:
            completeness = self._completeness.evaluate(query.text, cached)
            return cached, completeness

        raw_results = self._index.search(query.text, limit=query.limit * 2)
        ranked: list[SearchResult] = []

        for segment, score in raw_results:
            freshness_score = self._freshness.score(
                segment.metadata, query.freshness_horizon
            )
            if freshness_score <= 0:
                continue
            source_weight = (
                self._prioritizer.weight(segment.metadata.source)
                * segment.metadata.priority
            )
            tag_weight = self._score_tags(segment.metadata.tags, query.tags)
            authority = self._authority_bonus(segment.document_id)
            composite = score * freshness_score * source_weight * tag_weight * authority
            if composite <= 0:
                continue
            citations = []
            citation = self._citation_builder.build(segment.metadata)
            if citation:
                citations.append(citation)
            ranked.append(
                SearchResult(
                    document_id=segment.document_id,
                    segment_id=segment.segment_id,
                    text=segment.text,
                    score=composite,
                    citations=tuple(citations),
                    metadata=segment.metadata,
                )
            )

        ranked.sort(key=lambda item: item.score, reverse=True)
        limited = tuple(ranked[: query.limit])
        if limited:
            self._cache.set(fingerprint, limited)
        completeness = self._completeness.evaluate(query.text, limited)
        return limited, completeness
