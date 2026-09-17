"""Typed acyclic dependency graph with scoped invalidation."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import FrozenSet, Tuple

class DependencyKind(str, Enum):
    LOGICAL="LOGICAL"
    STATISTICAL="STATISTICAL"
    DATA="DATA"
    MODEL="MODEL"
    CALIBRATION="CALIBRATION"
    VERSION="VERSION"
    CONFIGURATION="CONFIGURATION"
    PROVENANCE="PROVENANCE"
    ORACLE="ORACLE"

@dataclass(frozen=True, slots=True)
class DependencyEdge:
    source: str
    target: str
    kind: DependencyKind

class DependencyGraph:
    def __init__(self) -> None:
        self._edges: set[DependencyEdge]=set()

    @property
    def edges(self) -> Tuple[DependencyEdge,...]:
        return tuple(sorted(self._edges,key=lambda e:(e.source,e.target,e.kind.value)))

    def add(self, source: str, target: str, kind: DependencyKind) -> None:
        if not source or not target: raise ValueError("dependency nodes must be non-empty")
        if source==target: raise ValueError("self-dependency forbidden")
        edge=DependencyEdge(source,target,kind); self._edges.add(edge)
        if self._reachable(target,source):
            self._edges.remove(edge); raise ValueError("dependency cycle forbidden")

    def _reachable(self, source: str, target: str) -> bool:
        stack=[source]; seen=set()
        while stack:
            node=stack.pop()
            if node==target: return True
            if node in seen: continue
            seen.add(node); stack.extend(e.target for e in self._edges if e.source==node)
        return False

    def impacted(self, source: str) -> FrozenSet[str]:
        out:set[str]=set(); stack=[source]
        while stack:
            node=stack.pop()
            for edge in self._edges:
                if edge.source==node and edge.target not in out:
                    out.add(edge.target); stack.append(edge.target)
        return frozenset(out)
