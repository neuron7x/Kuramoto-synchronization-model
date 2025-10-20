"""Knowledge graph representation for document references."""

from __future__ import annotations

from typing import Tuple

import networkx as nx

from .models import DocumentMetadata


class KnowledgeGraph:
    """Maintain a directed graph of document references."""

    def __init__(self) -> None:
        self._graph = nx.DiGraph()

    def upsert_document(self, metadata: DocumentMetadata) -> None:
        self._graph.add_node(metadata.document_id, metadata=metadata)

    def add_reference(self, source_id: str, target_id: str) -> None:
        if source_id == target_id:
            return
        if not self._graph.has_node(source_id) or not self._graph.has_node(target_id):
            return
        self._graph.add_edge(source_id, target_id)

    def remove_document(self, document_id: str) -> None:
        if self._graph.has_node(document_id):
            self._graph.remove_node(document_id)

    def references(self, document_id: str) -> Tuple[str, ...]:
        if not self._graph.has_node(document_id):
            return tuple()
        return tuple(self._graph.successors(document_id))

    def backlinks(self, document_id: str) -> Tuple[str, ...]:
        if not self._graph.has_node(document_id):
            return tuple()
        return tuple(self._graph.predecessors(document_id))

    def prune_orphans(self) -> None:
        orphans = [node for node, degree in self._graph.out_degree() if degree == 0]
        for node in orphans:
            if self._graph.in_degree(node) == 0:
                self._graph.remove_node(node)

    @property
    def graph(self) -> nx.DiGraph:
        return self._graph
