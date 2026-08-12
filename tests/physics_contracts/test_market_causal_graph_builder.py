# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the L2/order-flow → MarketCausalGraphSnapshot builder (Task 2).

Every falsifier in the builder contract gets a fail-closed witness: future
timestamp edge, zero-hash dataset, synthetic fingerprint, causal cutoff below
the latency floor, and missing edge weight. The happy path proves the
snapshot_id is deterministic and that there is no synthetic fallback.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from core.kuramoto.capital_weighted import L2DepthSnapshot
from physics_contracts.manifold.builders import (
    OrderFlowFrame,
    build_causal_graph_snapshot,
    l2_depth_to_order_flow_frame,
)
from physics_contracts.manifold.contracts import LicensedDataUnavailable

_REAL_FP = "a" * 64


def _frame(**overrides: object) -> OrderFlowFrame:
    base: dict[str, Any] = {
        "timestamp_start": 0.0,
        "timestamp_end": 1.0,
        "nodes": ("A", "B", "C"),
        "edges": ((0, 1), (1, 2)),
        "edge_weights": (0.5, 0.7),
        "latency_floor_seconds": 0.1,
        "causal_cutoff_seconds": 0.25,
        "dataset_fingerprint": _REAL_FP,
        "source_event_times": (0.5,),
    }
    base.update(overrides)
    return OrderFlowFrame(**base)


def test_happy_path_builds_snapshot_with_deterministic_id() -> None:
    frame = _frame()
    snap_a = build_causal_graph_snapshot(frame)
    snap_b = build_causal_graph_snapshot(frame)
    assert snap_a.snapshot_id == snap_b.snapshot_id
    assert snap_a.nodes == ("A", "B", "C")
    assert snap_a.edges == ((0, 1), (1, 2))
    assert snap_a.dataset_fingerprint == _REAL_FP


def test_future_timestamp_edge_is_rejected() -> None:
    frame = _frame(source_event_times=(2.0,))  # event after timestamp_end=1.0
    with pytest.raises(ValueError, match="look-ahead"):
        build_causal_graph_snapshot(frame)


def test_zero_hash_dataset_fails_closed() -> None:
    frame = _frame(dataset_fingerprint="0" * 64)
    with pytest.raises(LicensedDataUnavailable):
        build_causal_graph_snapshot(frame)


def test_synthetic_fingerprint_has_no_fallback() -> None:
    frame = _frame(dataset_fingerprint="synthetic:00000001")
    with pytest.raises(LicensedDataUnavailable):
        build_causal_graph_snapshot(frame)


def test_causal_cutoff_below_latency_floor_is_rejected() -> None:
    frame = _frame(latency_floor_seconds=0.5, causal_cutoff_seconds=0.1)
    with pytest.raises(ValueError, match="causal_cutoff"):
        build_causal_graph_snapshot(frame)


def test_missing_edge_weight_is_rejected() -> None:
    with pytest.raises(ValueError, match="missing edge weight"):
        _frame(edges=((0, 1), (1, 2)), edge_weights=(0.5,))


def test_l2_depth_adapter_reads_upper_triangle_edges() -> None:
    snapshot = L2DepthSnapshot(
        timestamp_ns=500_000_000,
        bid_sizes=np.ones((3, 5)),
        ask_sizes=np.ones((3, 5)),
        mid_prices=np.array([1.0, 2.0, 3.0]),
    )
    adjacency = np.array([[0.0, 0.4, 0.0], [0.4, 0.0, 0.6], [0.0, 0.6, 0.0]])
    frame = l2_depth_to_order_flow_frame(
        snapshot,
        adjacency=adjacency,
        symbols=("A", "B", "C"),
        timestamp_start=0.0,
        timestamp_end=1.0,
        latency_floor_seconds=0.1,
        causal_cutoff_seconds=0.25,
        dataset_fingerprint=_REAL_FP,
    )
    snap = build_causal_graph_snapshot(frame)
    assert snap.edges == ((0, 1), (1, 2))
    assert snap.edge_weights == (0.4, 0.6)


def test_l2_adapter_event_after_interval_is_lookahead() -> None:
    # Book event at 2.0 s but the snapshot interval ends at 1.0 s.
    snapshot = L2DepthSnapshot(
        timestamp_ns=2_000_000_000,
        bid_sizes=np.ones((2, 5)),
        ask_sizes=np.ones((2, 5)),
        mid_prices=np.array([1.0, 2.0]),
    )
    adjacency = np.array([[0.0, 0.5], [0.5, 0.0]])
    frame = l2_depth_to_order_flow_frame(
        snapshot,
        adjacency=adjacency,
        symbols=("A", "B"),
        timestamp_start=0.0,
        timestamp_end=1.0,
        latency_floor_seconds=0.1,
        causal_cutoff_seconds=0.25,
        dataset_fingerprint=_REAL_FP,
    )
    with pytest.raises(ValueError, match="look-ahead"):
        build_causal_graph_snapshot(frame)


def test_l2_adapter_rejects_negative_adjacency() -> None:
    snapshot = L2DepthSnapshot(
        timestamp_ns=1,
        bid_sizes=np.ones((2, 5)),
        ask_sizes=np.ones((2, 5)),
        mid_prices=np.array([1.0, 2.0]),
    )
    with pytest.raises(ValueError, match="negative weights"):
        l2_depth_to_order_flow_frame(
            snapshot,
            adjacency=np.array([[0.0, -0.5], [-0.5, 0.0]]),
            symbols=("A", "B"),
            timestamp_start=0.0,
            timestamp_end=1.0,
            latency_floor_seconds=0.1,
            causal_cutoff_seconds=0.25,
            dataset_fingerprint=_REAL_FP,
        )
