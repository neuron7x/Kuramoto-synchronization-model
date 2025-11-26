"""Facade for the redesigned knowledge search subsystem."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Iterable, Mapping, Sequence

from .cache import AnswerCache
from .compression import SegmentCompressor
from .embeddings import EmbeddingProvider
from .graph import KnowledgeGraph
from .indexer import HybridIndex, HybridIndexConfig
from .models import (
    CompletenessReport,
    Document,
    PipelineResult,
    SearchQuery,
    SearchResult,
)
from .pipeline import KnowledgeUpdatePipeline
from .retrieval import HybridSearchEngine, SourcePrioritizer
from .segmenter import DocumentSegmenter, SegmentationConfig
from .sharding import ShardManager
from .validators import (
    CitationBuilder,
    CompletenessController,
    FreshnessPolicy,
    LinkValidator,
)


@dataclass(slots=True)
class KnowledgeSearchConfig:
    """Configuration bundle for the knowledge search subsystem."""

    segmentation: SegmentationConfig = field(default_factory=SegmentationConfig)
    shard_weights: Mapping[str, int] = field(default_factory=lambda: {"default": 1})
    embedding_dimension: int = 384
    hybrid_index: HybridIndexConfig = field(default_factory=HybridIndexConfig)
    freshness_half_life_days: float = 30.0
    cache_max_entries: int = 512
    cache_ttl_minutes: int | None = 30
    source_weights: Mapping[str, float] = field(default_factory=dict)
    required_tags_by_query: Mapping[str, Sequence[str]] = field(default_factory=dict)


class KnowledgeSearchSubsystem:
    """High-level orchestrator for document ingestion and retrieval."""

    def __init__(self, config: KnowledgeSearchConfig | None = None) -> None:
        self._config = config or KnowledgeSearchConfig()
        self._segmenter = DocumentSegmenter(self._config.segmentation)
        self._compressor = SegmentCompressor()
        self._shards = ShardManager(self._config.shard_weights)
        self._embedding = EmbeddingProvider(self._config.embedding_dimension)
        self._index = HybridIndex(self._embedding, self._config.hybrid_index)
        self._graph = KnowledgeGraph()
        self._freshness = FreshnessPolicy(self._config.freshness_half_life_days)
        cache_ttl = (
            timedelta(minutes=self._config.cache_ttl_minutes)
            if self._config.cache_ttl_minutes is not None
            else None
        )
        self._cache = AnswerCache(
            max_entries=self._config.cache_max_entries, ttl=cache_ttl
        )
        self._citation_builder = CitationBuilder(LinkValidator())
        self._completeness = CompletenessController(self._config.required_tags_by_query)
        self._prioritizer = SourcePrioritizer(self._config.source_weights)
        self._pipeline = KnowledgeUpdatePipeline(
            segmenter=self._segmenter,
            compressor=self._compressor,
            shard_manager=self._shards,
            embedding_provider=self._embedding,
            index=self._index,
            knowledge_graph=self._graph,
            citation_builder=self._citation_builder,
        )
        self._search = HybridSearchEngine(
            index=self._index,
            freshness_policy=self._freshness,
            citation_builder=self._citation_builder,
            completeness_controller=self._completeness,
            answer_cache=self._cache,
            knowledge_graph=self._graph,
            source_prioritizer=self._prioritizer,
        )

    def update_documents(
        self,
        documents: Iterable[Document],
        references: Mapping[str, Sequence[str]] | None = None,
    ) -> PipelineResult:
        """Run the update pipeline for the provided documents."""

        result = self._pipeline.run(documents=documents, references=references)
        report = result.index_report
        if report.updated_segments or report.removed_segments:
            self._cache.clear()
        return result

    def search(
        self, query: SearchQuery
    ) -> tuple[Sequence[SearchResult], CompletenessReport]:
        """Execute a hybrid search with cache, citations, and completeness control."""

        return self._search.search(query)

    @property
    def graph(self) -> KnowledgeGraph:
        return self._graph

    @property
    def cache(self) -> AnswerCache:
        return self._cache
