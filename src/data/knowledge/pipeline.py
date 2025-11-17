"""Update pipeline for the knowledge search subsystem."""

from __future__ import annotations

from typing import Iterable, Mapping, Sequence

from .compression import SegmentCompressor
from .embeddings import EmbeddingProvider
from .graph import KnowledgeGraph
from .indexer import HybridIndex
from .models import (
    Document,
    DocumentSegment,
    IndexedSegment,
    PipelineContext,
    PipelineResult,
)
from .segmenter import DocumentSegmenter
from .sharding import ShardManager
from .validators import CitationBuilder, LinkValidator


class KnowledgeUpdatePipeline:
    """Coordinate document ingestion into the hybrid index."""

    def __init__(
        self,
        segmenter: DocumentSegmenter,
        compressor: SegmentCompressor,
        shard_manager: ShardManager,
        embedding_provider: EmbeddingProvider,
        index: HybridIndex,
        knowledge_graph: KnowledgeGraph,
        citation_builder: CitationBuilder | None = None,
    ) -> None:
        self._segmenter = segmenter
        self._compressor = compressor
        self._shard_manager = shard_manager
        self._embedding_provider = embedding_provider
        self._index = index
        self._graph = knowledge_graph
        self._citation_builder = citation_builder or CitationBuilder(LinkValidator())

    def _compress_segments(
        self, context: PipelineContext, segments: Sequence[DocumentSegment]
    ) -> None:
        for compressed in self._compressor.bulk_compress(segments):
            context.compressed_segments[compressed.segment_id] = compressed

    def _index_segments(
        self, context: PipelineContext, segments: Sequence[DocumentSegment]
    ) -> None:
        for segment in segments:
            shard_key = self._shard_manager.shard_key(segment)
            vector = self._embedding_provider.embed_segment(segment)
            indexed = IndexedSegment(
                segment_id=segment.segment_id,
                document_id=segment.document_id,
                shard_key=shard_key,
                metadata=segment.metadata,
                vector=tuple(vector.tolist()),
                text=segment.text,
            )
            context.indexed_segments[indexed.segment_id] = indexed

    def run(
        self,
        documents: Iterable[Document],
        references: Mapping[str, Sequence[str]] | None = None,
    ) -> PipelineResult:
        context = PipelineContext()
        all_segments: list[DocumentSegment] = []
        invalid_links: list[str] = []
        references = references or {}
        processed_documents: set[str] = set()

        for document in documents:
            self._graph.upsert_document(document.metadata)
            segments = self._segmenter.segment(document)
            processed_documents.add(document.metadata.document_id)
            for segment in segments:
                context.segments[segment.segment_id] = segment
            all_segments.extend(segments)
            citation = self._citation_builder.build(document.metadata)
            if citation is None:
                invalid_links.append(document.metadata.document_id)

        if all_segments:
            self._compress_segments(context, all_segments)
            self._index_segments(context, all_segments)

        for source_id, targets in references.items():
            for target_id in targets:
                self._graph.add_reference(source_id, target_id)
        self._graph.prune_orphans()

        report = self._index.maintenance(
            context.indexed_segments.values(), processed_documents
        )
        return PipelineResult(
            context=context, index_report=report, invalid_links=tuple(invalid_links)
        )
