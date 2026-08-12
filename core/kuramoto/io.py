# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""IO helpers for Kuramoto CLI topology parsing and JSON export contracts.

This module is the single boundary for user-supplied topology files and
machine-readable payload generation used by ``tp-kuramoto``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

SCHEMA_VERSION = 1


def parse_float_list(raw: str, *, option_name: str) -> NDArray[np.float64]:
    """Parse a comma-separated vector and reject empty/non-finite values."""
    chunks = raw.split(",")
    if not chunks:
        raise ValueError(f"{option_name} must contain at least one numeric value.")
    if any(not chunk.strip() for chunk in chunks):
        raise ValueError(
            f"{option_name} contains an empty entry. "
            f"Use a strict comma-separated list such as '0.1,0.2,0.3'."
        )

    values = [chunk.strip() for chunk in chunks]

    try:
        vector = np.array([float(v) for v in values], dtype=np.float64)
    except ValueError as exc:
        raise ValueError(f"Failed to parse {option_name}: {exc}") from exc

    if not np.isfinite(vector).all():
        raise ValueError(f"{option_name} contains non-finite values.")

    return vector


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed JSON in {path}: {exc.msg}.") from exc
    except OSError as exc:
        raise ValueError(f"Failed to read JSON file {path}: {exc}.") from exc


def load_adjacency_matrix(path: Path) -> NDArray[np.float64]:
    """Load an adjacency matrix from ``.json``, ``.csv/.txt``, or ``.npy``."""
    suffix = path.suffix.lower()
    if suffix == ".json":
        matrix = np.asarray(_load_json(path), dtype=np.float64)
    elif suffix in {".csv", ".txt"}:
        try:
            matrix = np.loadtxt(path, delimiter=",", dtype=np.float64)
        except ValueError as exc:
            raise ValueError(f"Malformed delimited adjacency matrix in {path}: {exc}.") from exc
    elif suffix == ".npy":
        matrix = np.load(path, allow_pickle=False)
    else:
        raise ValueError(
            f"Unsupported adjacency file extension '{suffix}'. Supported: .json, .csv, .txt, .npy"
        )

    if matrix.ndim != 2:
        raise ValueError("Adjacency matrix must be 2-dimensional.")
    if matrix.shape[0] != matrix.shape[1]:
        raise ValueError("Adjacency matrix must be square (N x N).")
    if not np.isfinite(matrix).all():
        raise ValueError("Adjacency matrix contains non-finite values.")

    return np.asarray(matrix, dtype=np.float64)


def load_edge_list(path: Path, n_oscillators: int) -> NDArray[np.float64]:
    """Load weighted directed topology from edge-list JSON.

    Expected schema:
    ``{"edges": [{"source": int, "target": int, "weight": float=1.0}, ...]}``
    """
    payload = _load_json(path)
    edges = payload.get("edges") if isinstance(payload, dict) else None
    if not isinstance(edges, list):
        raise ValueError("Edge-list JSON must contain an 'edges' array.")

    adj = np.zeros((n_oscillators, n_oscillators), dtype=np.float64)
    seen_edges: set[tuple[int, int]] = set()

    for idx, edge in enumerate(edges):
        if not isinstance(edge, dict):
            raise ValueError(f"Edge entry at index {idx} must be an object.")

        try:
            source = int(edge["source"])
            target = int(edge["target"])
        except KeyError as exc:
            raise ValueError(f"Edge entry at index {idx} is missing {exc.args[0]!r}.") from exc

        weight = float(edge.get("weight", 1.0))

        if not (0 <= source < n_oscillators and 0 <= target < n_oscillators):
            raise ValueError(f"Edge ({source}, {target}) out of range for N={n_oscillators}.")
        if not np.isfinite(weight):
            raise ValueError(f"Edge ({source}, {target}) has non-finite weight.")
        if (source, target) in seen_edges:
            raise ValueError(f"Duplicate edge ({source}, {target}) is not allowed.")
        seen_edges.add((source, target))

        adj[source, target] = weight

    return adj


def export_payload(
    *,
    summary: dict[str, Any],
    config: dict[str, Any],
    include_trajectories: bool,
    order_parameter: NDArray[np.float64],
    time: NDArray[np.float64],
    phases: NDArray[np.float64],
) -> dict[str, Any]:
    """Build deterministic JSON-safe payload for stdout and file export."""
    if (
        not np.isfinite(order_parameter).all()
        or not np.isfinite(time).all()
        or not np.isfinite(phases).all()
    ):
        raise ValueError("Export payload requires finite trajectories.")
    expected_steps = len(time)
    if len(order_parameter) != expected_steps:
        raise ValueError(
            "Export payload shape mismatch: "
            f"order_parameter has length {len(order_parameter)}, expected {expected_steps}."
        )
    if phases.ndim != 2 or phases.shape[0] != expected_steps:
        raise ValueError(
            "Export payload shape mismatch: "
            f"phases has shape {phases.shape}, expected ({expected_steps}, N)."
        )

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "summary": summary,
        "config": config,
    }

    if include_trajectories:
        payload["order_parameter"] = order_parameter.tolist()
        payload["time"] = time.tolist()
        payload["phases"] = phases.tolist()

    return payload
