"""Fractal graph contrastive learning helpers for FHMC novelty signals."""

from __future__ import annotations

from typing import Sequence

import networkx as nx
import numpy as np

try:
    import torch
    import torch.nn.functional as F

    _TORCH_AVAILABLE = True
except (ImportError, OSError):  # pragma: no cover - optional dependency
    _TORCH_AVAILABLE = False
    torch = None  # type: ignore[assignment]
    F = None  # type: ignore[assignment]


def fractal_boxcover(graph: nx.Graph, max_box: int = 4) -> list[list[int]]:
    """Greedy renormalisation box-covering with bounded diameter."""

    if max_box <= 0:
        raise ValueError("max_box must be positive")

    boxes: list[list[int]] = []
    nodes: Sequence[int] = list(graph.nodes())
    used: set[int] = set()
    for root in nodes:
        if root in used:
            continue
        box = [root]
        used.add(root)
        for candidate in nodes:
            if candidate in used or candidate == root:
                continue
            try:
                if nx.shortest_path_length(graph, root, candidate) <= max_box:
                    box.append(candidate)
                    used.add(candidate)
            except nx.NetworkXNoPath:
                continue
        boxes.append(box)
    return boxes


def fd_one_shot(graph: nx.Graph, boxes: Sequence[Sequence[int]]) -> float:
    """Approximate fractal dimension via a single log–log fit."""

    if not boxes:
        return 0.0

    lengths = np.maximum(np.array([len(box) for box in boxes], dtype=float), 1.0)
    counts = float(len(boxes))
    x = np.log(lengths + 1e-8)
    if np.allclose(x, x[0]):
        return 0.0

    y = np.log(np.full_like(lengths, fill_value=counts))
    design = np.column_stack([x, np.ones_like(x)])
    slope, _intercept = np.linalg.lstsq(design, y, rcond=None)[0]
    return float(abs(slope))


def contrastive_loss_fractal(
    z_i: "torch.Tensor",
    z_j: "torch.Tensor",
    fd_i: "torch.Tensor",
    fd_j: "torch.Tensor",
    *,
    tau: float = 0.2,
) -> "torch.Tensor":
    """Fractal-aware contrastive objective for representation alignment."""

    if not _TORCH_AVAILABLE:
        raise ImportError("torch is required for contrastive_loss_fractal")

    if tau <= 0:
        raise ValueError("tau must be positive")

    align = (z_i * z_j).sum(dim=-1)
    weight = 1.0 + (fd_i - fd_j).abs()
    return -(weight * F.log_softmax(align / tau, dim=0)).mean()


def fractal_gcl_novelty(
    graph: nx.Graph,
    embeddings_i: np.ndarray,
    embeddings_j: np.ndarray,
) -> tuple[float, float]:
    """Return novelty and fractal dimension given two embedding snapshots."""

    if embeddings_i.ndim != 2 or embeddings_j.ndim != 2:
        raise ValueError("embeddings must be 2-D arrays")
    if embeddings_i.shape[1] != embeddings_j.shape[1]:
        raise ValueError("embeddings must share the same feature dimension")

    boxes = fractal_boxcover(graph)
    fd = fd_one_shot(graph, boxes)

    zi = embeddings_i.mean(axis=0)
    zj = embeddings_j.mean(axis=0)
    zi = zi / (np.linalg.norm(zi) + 1e-8)
    zj = zj / (np.linalg.norm(zj) + 1e-8)
    cos = float(np.clip(np.dot(zi, zj), -1.0, 1.0))
    novelty = (1.0 - cos) * (1.0 + abs(fd))
    return novelty, fd
