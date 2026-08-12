"""Build deterministic L2 order-book graphs for Ricci inference."""

from __future__ import annotations

from typing import Any

import networkx as nx
import pandas as pd

from .nobi import nobi


def build_l2_graph(
    row: pd.Series | dict[str, Any], *, depth: int, weight_mode: str = "nobi"
) -> nx.DiGraph:
    if depth < 1:
        raise ValueError("depth must be >= 1")
    record = row.to_dict() if hasattr(row, "to_dict") else dict(row)
    imbalance = nobi(record, depth)
    if weight_mode != "nobi":
        raise ValueError(f"unsupported edge weight mode: {weight_mode}")

    graph = nx.DiGraph()
    for idx in range(1, depth + 1):
        bid_node = f"bid_{idx}"
        ask_node = f"ask_{idx}"
        graph.add_node(
            bid_node,
            side="bid",
            level=idx,
            price=float(record[f"bid_px_{idx}"]),
            size=float(record[f"bid_sz_{idx}"]),
        )
        graph.add_node(
            ask_node,
            side="ask",
            level=idx,
            price=float(record[f"ask_px_{idx}"]),
            size=float(record[f"ask_sz_{idx}"]),
        )

    # Per-edge metric = absolute price gap between the two levels — a real,
    # snapshot-varying geometric distance. The previous constant
    # abs(imbalance)+eps made every edge identical AND was never read (the kernel
    # used unweighted hop-count), so curvature collapsed to a fixed topological
    # constant independent of the book. The price gap makes the Ollivier metric
    # microstructure-sensitive; `edge_weight` still carries the NOBI feature.
    def _gap(a: str, b: str) -> float:
        return abs(float(graph.nodes[a]["price"]) - float(graph.nodes[b]["price"])) + 1.0e-12

    for idx in range(1, depth):
        for src, dst in ((f"bid_{idx}", f"bid_{idx + 1}"), (f"ask_{idx}", f"ask_{idx + 1}")):
            graph.add_edge(src, dst, edge_weight=imbalance, weight=_gap(src, dst))
            graph.add_edge(dst, src, edge_weight=imbalance, weight=_gap(src, dst))
    for idx in range(1, depth + 1):
        bid_node, ask_node = f"bid_{idx}", f"ask_{idx}"
        graph.add_edge(bid_node, ask_node, edge_weight=imbalance, weight=_gap(bid_node, ask_node))
        graph.add_edge(ask_node, bid_node, edge_weight=imbalance, weight=_gap(ask_node, bid_node))

    for _, _, data in graph.edges(data=True):
        if data["edge_weight"] != data["edge_weight"]:
            raise ValueError("NaN edge weight")
    return graph
