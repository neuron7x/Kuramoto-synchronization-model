# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Naive baselines that the candidate Kuramoto signal must beat.

Per § 13 of the canonical R&D checklist, the candidate detector
must outperform every baseline below; otherwise the claimed signal
is empirically indistinguishable from a far simpler explanation.

* :func:`rolling_volatility_score` — pure volatility detector. If
  the candidate cannot beat this, the Kuramoto layer adds nothing
  over a "fire when the market is loud" rule.
* :func:`edge_density_score` — static topology density detector
  (one scalar per snapshot). If the candidate cannot beat this,
  the temporal phase structure adds nothing over a sparsifying /
  densifying graph indicator.

Both baselines share the same fail-closed contract as the rest of
the module: NaN / Inf rejected, zero-window rejected, no lookahead
leakage.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray

from .errors import InvalidExposureMatrixError, InvalidTemporalPanelError

__all__ = [
    "rolling_volatility_score",
    "edge_density_score",
]


def rolling_volatility_score(
    series: NDArray[np.float64],
    *,
    window: int,
    min_periods: int,
) -> NDArray[np.float64]:
    """Trailing-window sample standard deviation of a 1-D series.

    Pure volatility detector — no phase, no coupling, no graph.
    Runs as the candidate's "is the market just loud?" baseline.

    Contract
    --------
    * Output length equals input length.
    * ``score[t]`` uses only ``series[: t + 1]`` (no lookahead).
    * Indices where the trailing window is shorter than
      ``min_periods`` are NaN.
    * Constant segments give exactly ``0.0`` (not NaN) — the
      *standard deviation* of a constant series is well-defined.
    """
    v = np.asarray(series, dtype=np.float64)
    if v.ndim != 1:
        raise ValueError(f"series must be 1-D, got shape={v.shape}")
    if v.size == 0:
        raise ValueError("series must be non-empty")
    if not np.isfinite(v).all():
        raise ValueError("series must be finite (no NaN/Inf)")
    if window < 2:
        raise ValueError(f"window must be >= 2, got {window}")
    if min_periods < 2:
        raise ValueError(f"min_periods must be >= 2, got {min_periods}")
    if min_periods > window:
        raise ValueError(f"min_periods ({min_periods}) must be <= window ({window})")
    n = v.size
    out = np.full(n, np.nan, dtype=np.float64)
    for t in range(n):
        start = max(0, t - window + 1)
        seg = v[start : t + 1]
        if seg.size < min_periods:
            continue
        out[t] = float(seg.std(ddof=1))
    return out


def edge_density_score(
    adjacency_panel: Sequence[NDArray[np.generic]],
    *,
    directed: bool = True,
    include_self_edges: bool = False,
) -> NDArray[np.float64]:
    """Per-snapshot edge density of a panel of adjacency matrices.

    Canonical formula (density ∈ [0, 1] for binary adjacency):

    ::

        directed,   no self-edges:  sum(A_off)        / (N * (N - 1))
        directed,   self-edges:     sum(A)            /  N**2
        undirected, no self-edges:  sum(triu(A, k=1)) / (N * (N - 1) / 2)
        undirected, self-edges:     sum(triu(A, k=0)) / (N * (N + 1) / 2)

    The undirected case reads only the strict upper triangle so
    each edge is counted exactly once — an unguarded ``A.sum()`` on
    a symmetric matrix would double-count and exceed 1.0 for the
    complete graph. Symmetry is enforced fail-closed when
    ``directed=False``: a transpose bug raises rather than
    silently scaling the density wrong.

    Returns a length-``len(adjacency_panel)`` ``float64`` array.

    Fail-closed
    -----------
    * empty panel → :class:`InvalidTemporalPanelError`
    * non-square snapshot → :class:`InvalidExposureMatrixError`
    * inconsistent ``N`` across snapshots → :class:`InvalidTemporalPanelError`
    * NaN / Inf snapshot → :class:`InvalidExposureMatrixError`
    * negative entry → :class:`InvalidExposureMatrixError`
      (caller passes binary 0/1 or non-negative weights only)
    * ``directed=False`` with non-symmetric snapshot →
      :class:`InvalidExposureMatrixError`
    """
    if len(adjacency_panel) == 0:
        raise InvalidTemporalPanelError("adjacency_panel must be non-empty")
    n_snapshots = len(adjacency_panel)
    out = np.empty(n_snapshots, dtype=np.float64)
    n_nodes: int | None = None
    for idx, raw in enumerate(adjacency_panel):
        a = np.asarray(raw, dtype=np.float64)
        if a.ndim != 2 or a.shape[0] != a.shape[1]:
            raise InvalidExposureMatrixError(
                f"snapshot {idx} must be square 2-D, got shape={a.shape}"
            )
        if not np.isfinite(a).all():
            raise InvalidExposureMatrixError(f"snapshot {idx} contains NaN/Inf")
        if np.any(a < 0):
            raise InvalidExposureMatrixError(f"snapshot {idx} contains negative entries")
        n = a.shape[0]
        if n_nodes is None:
            n_nodes = n
        elif n != n_nodes:
            raise InvalidTemporalPanelError(
                f"snapshot {idx} has N={n}; expected N={n_nodes} from "
                f"snapshot 0 (panel must share a stable node universe)"
            )
        if not directed and not np.array_equal(a, a.T):
            # bounds: undirected density is only well-defined on
            # symmetric adjacency. A transpose / orientation bug
            # would silently distort the scale; fail-closed.
            raise InvalidExposureMatrixError(
                f"snapshot {idx} must be symmetric when directed=False"
            )
        if n <= 1:
            out[idx] = 0.0
            continue
        if include_self_edges:
            if directed:
                edges = float(a.sum())
                denom = float(n * n)
            else:
                edges = float(np.triu(a, k=0).sum())
                denom = float(n * (n + 1) / 2)
        else:
            if directed:
                edges = float(a.sum() - np.trace(a))
                denom = float(n * (n - 1))
            else:
                edges = float(np.triu(a, k=1).sum())
                denom = float(n * (n - 1) / 2)
        out[idx] = edges / denom
    return out
