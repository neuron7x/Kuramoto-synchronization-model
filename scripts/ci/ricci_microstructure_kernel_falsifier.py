#!/usr/bin/env python3
"""Diff-bound falsifier for the ricci-microstructure-v1-kernel acceptor.

Inverts the anti-vacuity contract of the Ollivier-Ricci microstructure kernel:
with graph topology held fixed, scaling the per-level order-book *sizes* MUST
change the mean curvature. The pre-repair v1 kernel used a uniform/topology-only
transport measure and produced constant curvature; that regression drives the
difference to ~0 and makes this script exit non-zero.

Exit 0  -> kernel is microstructure-sensitive (asserted-healthy state).
Exit 1  -> kernel went vacuous (size change did not move curvature).
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from geosync_research.lines.ricci_microstructure_v1.graph_builder import build_l2_graph
from geosync_research.lines.ricci_microstructure_v1.ricci_kernel import (
    RicciKernelConfig,
    compute_ricci_curvature,
    edge_curvature_records,
)


def _mean_curvature(row: pd.Series) -> float:
    graph = build_l2_graph(row, depth=5)
    curved = compute_ricci_curvature(graph, config=RicciKernelConfig(alpha=0.5, n_min_edges=2))
    return float(np.mean([rec["ricciCurvature"] for rec in edge_curvature_records(curved)]))


def main() -> int:
    base_row = {
        "timestamp": "2026-01-01T00:00:00Z",
        "price": 100.0,
        "bid_px_1": 99.9,
        "ask_px_1": 100.1,
        "bid_sz_1": 10.0,
        "ask_sz_1": 9.0,
        "bid_px_2": 99.8,
        "ask_px_2": 100.2,
        "bid_sz_2": 11.0,
        "ask_sz_2": 8.0,
        "bid_px_3": 99.7,
        "ask_px_3": 100.3,
        "bid_sz_3": 12.0,
        "ask_sz_3": 7.0,
        "bid_px_4": 99.6,
        "ask_px_4": 100.4,
        "bid_sz_4": 13.0,
        "ask_sz_4": 6.0,
        "bid_px_5": 99.5,
        "ask_px_5": 100.5,
        "bid_sz_5": 14.0,
        "ask_sz_5": 5.0,
    }
    base = pd.DataFrame([base_row]).iloc[0]
    perturbed = base.copy()
    for i in range(1, 6):
        perturbed[f"bid_sz_{i}"] = base[f"bid_sz_{i}"] * (1.0 + 0.5 * i)
    if abs(_mean_curvature(base) - _mean_curvature(perturbed)) <= 1e-6:
        print("FALSIFIED: kernel vacuous — size change did not move curvature", file=sys.stderr)
        return 1
    print("OK: kernel is microstructure-sensitive (size change moved curvature)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
