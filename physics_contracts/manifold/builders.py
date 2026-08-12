# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Thin L2 / order-flow frame → ``MarketCausalGraphSnapshot`` adapter.

This module is a *builder*, not a graph theory. It maps an already-formed
order-flow frame (node labels, directed edges, transport weights, and the
provenance of the data substrate) onto the frozen
:class:`~physics_contracts.manifold.contracts.MarketCausalGraphSnapshot`
contract, and fails closed on every way an L2-derived causal graph can lie:

* a source event in the snapshot's future (look-ahead),
* a zero-hash / empty dataset fingerprint (no real data),
* a synthetic-tagged fingerprint reaching a real-data builder,
* a causal cutoff tighter than the substrate latency floor,
* a missing or mismatched edge weight.

It introduces **no new graph construction maths**: the edges and weights are
supplied by the caller (e.g. from
``core.kuramoto.capital_weighted.build_capital_weighted_adjacency`` applied to a
:class:`~core.kuramoto.capital_weighted.L2DepthSnapshot`). The builder only
validates, fingerprints, and content-addresses the result so the snapshot_id is
deterministic. There is **no synthetic fallback** — a missing licensed dataset
raises rather than substituting fabricated data.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from core.kuramoto.capital_weighted import L2DepthSnapshot
from physics_contracts.manifold.contracts import (
    MarketCausalGraphSnapshot,
    canonical_digest,
    require_licensed_l2,
)

__all__ = [
    "OrderFlowFrame",
    "build_causal_graph_snapshot",
    "l2_depth_to_order_flow_frame",
]

# Nanoseconds per second — the L2 substrate stamps events in integer ns
# (``L2DepthSnapshot.timestamp_ns``); the causal contract works in seconds.
_NS_PER_SECOND: float = 1.0e9


@dataclass(frozen=True, slots=True)
class OrderFlowFrame:
    """A structural order-flow frame ready to become a causal-graph snapshot.

    Every field maps one-to-one onto a ``MarketCausalGraphSnapshot`` field
    except ``source_event_times``, which carries the timestamps of the L2/order
    events the frame was built from so the builder can prove no look-ahead.

    The frame itself performs only cheap, local fail-closed checks; the heavy
    structural validation (edge-index bounds, weight finiteness, interval
    monotonicity, causal-cutoff ≥ latency-floor) is delegated to the snapshot
    contract so there is exactly one source of truth for it.
    """

    timestamp_start: float
    timestamp_end: float
    nodes: tuple[str, ...]
    edges: tuple[tuple[int, int], ...]
    edge_weights: tuple[float, ...]
    latency_floor_seconds: float
    causal_cutoff_seconds: float
    dataset_fingerprint: str
    source_event_times: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.edges) != len(self.edge_weights):
            raise ValueError(
                "OrderFlowFrame VIOLATED: missing edge weight — "
                f"{len(self.edges)} edges but {len(self.edge_weights)} weights"
            )


def build_causal_graph_snapshot(
    frame: OrderFlowFrame,
    *,
    builder_method: str = "l2_order_flow_v1",
    construction_config: dict[str, object] | None = None,
) -> MarketCausalGraphSnapshot:
    """Adapt an :class:`OrderFlowFrame` to a fail-closed causal-graph snapshot.

    The licensed-data gate runs *first*: a zero-hash, empty, or synthetic
    fingerprint raises :class:`LicensedDataUnavailable` here, before any
    snapshot is constructed — there is no synthetic fallback path. The snapshot
    contract then enforces structural admissibility, and finally
    ``assert_no_lookahead`` rejects any source event after ``timestamp_end``.

    The returned snapshot's ``snapshot_id`` is a deterministic content address:
    identical frames yield identical ids.
    """

    # Fail-closed gate #1: real data must be present. Never substitute synthetic.
    fingerprint = require_licensed_l2(frame.dataset_fingerprint)

    config_payload: dict[str, object] = {
        "builder_method": builder_method,
        "n_nodes": len(frame.nodes),
        "n_edges": len(frame.edges),
        "latency_floor_seconds": frame.latency_floor_seconds,
        "causal_cutoff_seconds": frame.causal_cutoff_seconds,
    }
    if construction_config is not None:
        # Caller-supplied knobs participate in the replay identity.
        config_payload["construction_config"] = dict(sorted(construction_config.items()))
    construction_config_hash = canonical_digest(config_payload)

    # The contract validates interval monotonicity, edge indices, unique nodes,
    # finite non-negative weights, and causal_cutoff ≥ latency_floor — all the
    # remaining structural falsifiers — fail-closed in its __post_init__.
    snapshot = MarketCausalGraphSnapshot(
        timestamp_start=frame.timestamp_start,
        timestamp_end=frame.timestamp_end,
        nodes=frame.nodes,
        edges=frame.edges,
        edge_weights=frame.edge_weights,
        latency_floor_seconds=frame.latency_floor_seconds,
        causal_cutoff_seconds=frame.causal_cutoff_seconds,
        dataset_fingerprint=fingerprint,
        construction_config_hash=construction_config_hash,
        builder_method=builder_method,
    )

    # Fail-closed gate #2: no look-ahead. Any source event after the snapshot
    # end means the builder peeked into the future ("future timestamp edge").
    snapshot.assert_no_lookahead(frame.source_event_times)
    return snapshot


def l2_depth_to_order_flow_frame(
    snapshot: L2DepthSnapshot,
    *,
    adjacency: NDArray[np.float64],
    symbols: tuple[str, ...],
    timestamp_start: float,
    timestamp_end: float,
    latency_floor_seconds: float,
    causal_cutoff_seconds: float,
    dataset_fingerprint: str,
) -> OrderFlowFrame:
    """Convert an :class:`L2DepthSnapshot` + precomputed adjacency to a frame.

    ``adjacency`` is an ``(N, N)`` non-negative, symmetric coupling matrix the
    caller already built from the L2 book (e.g. via
    ``build_capital_weighted_adjacency``). This builder does **not** recompute
    any coupling — it only reads the upper triangle into a deterministic,
    canonically-ordered undirected edge list. ``symbols`` are the instrument
    node labels (length ``N``).

    The L2 event time (``snapshot.timestamp_ns`` → seconds) is recorded as the
    single source-event time, so a snapshot whose interval ends *before* the
    book event it consumed will be rejected as look-ahead by the snapshot
    builder.
    """

    n = len(symbols)
    if adjacency.shape != (n, n):
        raise ValueError(
            "l2_depth_to_order_flow_frame VIOLATED: adjacency shape "
            f"{adjacency.shape} does not match {n} symbols"
        )
    if not np.isfinite(adjacency).all():
        raise ValueError(
            "l2_depth_to_order_flow_frame VIOLATED: adjacency contains non-finite entries"
        )
    if (adjacency < 0.0).any():
        raise ValueError("l2_depth_to_order_flow_frame VIOLATED: adjacency has negative weights")

    edges: list[tuple[int, int]] = []
    weights: list[float] = []
    for i in range(n):
        for j in range(i + 1, n):
            w = float(adjacency[i, j])
            if w > 0.0:
                edges.append((i, j))
                weights.append(w)

    event_time_seconds = float(snapshot.timestamp_ns) / _NS_PER_SECOND
    return OrderFlowFrame(
        timestamp_start=timestamp_start,
        timestamp_end=timestamp_end,
        nodes=tuple(symbols),
        edges=tuple(edges),
        edge_weights=tuple(weights),
        latency_floor_seconds=latency_floor_seconds,
        causal_cutoff_seconds=causal_cutoff_seconds,
        dataset_fingerprint=dataset_fingerprint,
        source_event_times=(event_time_seconds,),
    )
