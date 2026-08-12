# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Redesigned knowledge search subsystem."""

from .cache import AnswerCache
from .compression import SegmentCompressor
from .embeddings import EmbeddingProvider
from .graph import KnowledgeGraph
from .indexer import BM25Index, HybridIndex, HybridIndexConfig, VectorIndex
from .models import (
    AnswerCacheEntry,
    Citation,
    CompletenessReport,
    Document,
    DocumentMetadata,
    DocumentSegment,
    IndexedSegment,
    IndexMaintenanceReport,
    PipelineContext,
    PipelineResult,
    SearchQuery,
    SearchResult,
)
from .pipeline import KnowledgeUpdatePipeline
from .retrieval import HybridSearchEngine, SourcePrioritizer
from .segmenter import DocumentSegmenter, SegmentationConfig
from .sharding import ShardManager
from .subsystem import KnowledgeSearchConfig, KnowledgeSearchSubsystem
from .validators import (
    CitationBuilder,
    CompletenessController,
    FreshnessPolicy,
    LinkValidator,
)

__all__ = [
    "AnswerCache",
    "AnswerCacheEntry",
    "BM25Index",
    "Citation",
    "CompletenessReport",
    "Document",
    "DocumentMetadata",
    "DocumentSegment",
    "EmbeddingProvider",
    "IndexedSegment",
    "IndexMaintenanceReport",
    "KnowledgeGraph",
    "KnowledgeSearchConfig",
    "KnowledgeSearchSubsystem",
    "KnowledgeUpdatePipeline",
    "LinkValidator",
    "SegmentCompressor",
    "HybridIndex",
    "HybridIndexConfig",
    "VectorIndex",
    "PipelineContext",
    "PipelineResult",
    "SearchQuery",
    "SearchResult",
    "DocumentSegmenter",
    "SegmentationConfig",
    "ShardManager",
    "HybridSearchEngine",
    "SourcePrioritizer",
    "CitationBuilder",
    "CompletenessController",
    "FreshnessPolicy",
]
