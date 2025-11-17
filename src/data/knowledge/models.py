"""Data models for the knowledge search subsystem."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Mapping, MutableMapping, Sequence


@dataclass(slots=True)
class DocumentMetadata:
    """Metadata describing a knowledge document."""

    document_id: str
    source: str
    created_at: datetime
    updated_at: datetime
    priority: float = 1.0
    tags: Sequence[str] = field(default_factory=tuple)
    attributes: Mapping[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class Document:
    """A knowledge base document with textual content and metadata."""

    metadata: DocumentMetadata
    content: str


@dataclass(slots=True)
class DocumentSegment:
    """A content segment derived from a :class:`Document`."""

    segment_id: str
    document_id: str
    order: int
    text: str
    metadata: DocumentMetadata


@dataclass(slots=True)
class CompressedSegment:
    """Compressed payload for a document segment."""

    segment_id: str
    document_id: str
    payload: bytes
    metadata: DocumentMetadata


@dataclass(slots=True)
class IndexedSegment:
    """Representation of a segment stored inside an index."""

    segment_id: str
    document_id: str
    shard_key: str
    metadata: DocumentMetadata
    vector: Sequence[float]
    text: str


@dataclass(slots=True)
class SearchQuery:
    """Incoming search request."""

    text: str
    tags: Sequence[str] = field(default_factory=tuple)
    limit: int = 10
    freshness_horizon: int | None = None


@dataclass(slots=True)
class Citation:
    """Citation material for a search result."""

    document_id: str
    url: str
    title: str
    accessed_at: datetime


@dataclass(slots=True)
class SearchResult:
    """A ranked search result returned to the caller."""

    document_id: str
    segment_id: str
    text: str
    score: float
    citations: Sequence[Citation]
    metadata: DocumentMetadata


@dataclass(slots=True)
class AnswerCacheEntry:
    """Cached answer material."""

    query_fingerprint: str
    created_at: datetime
    results: Sequence[SearchResult]


@dataclass(slots=True)
class CompletenessReport:
    """Information about coverage of returned results."""

    total_results: int
    missing_tags: Sequence[str]
    stale_results: Sequence[str]


@dataclass(slots=True)
class IndexMaintenanceReport:
    """Summary of an index maintenance run."""

    updated_segments: int
    removed_segments: int
    shards_touched: Sequence[str]
    issues: Sequence[str] = field(default_factory=tuple)


@dataclass(slots=True)
class PipelineResult:
    """Outcome of a pipeline execution."""

    context: PipelineContext
    index_report: IndexMaintenanceReport
    invalid_links: Sequence[str]


@dataclass(slots=True)
class PipelineContext:
    """Mutable state shared within a pipeline execution."""

    segments: MutableMapping[str, DocumentSegment] = field(default_factory=dict)
    compressed_segments: MutableMapping[str, CompressedSegment] = field(
        default_factory=dict
    )
    indexed_segments: MutableMapping[str, IndexedSegment] = field(default_factory=dict)
