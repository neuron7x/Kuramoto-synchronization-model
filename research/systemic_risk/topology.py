# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Interbank network topology — directed empirical adapter + null baselines.

Real interbank exposures are *directed*: bank *i* lending to bank *j* is
not the same as *j* lending to *i*. Symmetrising the graph, as v1 of this
module did, throws away the credit-direction signal that determines
which institution propagates stress to which neighbour. v2 builds a
directed (asymmetric) adjacency by default and supports an explicit
symmetric override only for null-model baselines.

Two construction paths:

1. **Empirical** (:func:`from_exposure_matrix`): a possibly directed
   exposure matrix :math:`E` where :math:`E_{ij}` = lending from bank
   *i* to bank *j* is binarised at a documented threshold.
   ``directed=True`` (default) keeps the asymmetric structure;
   ``directed=False`` averages :math:`E` with :math:`E^T` first
   (legacy/null-only).

2. **Barabási–Albert null** (:func:`barabasi_albert_null`,
   :func:`fit_barabasi_albert`): the BA generator produces a symmetric
   graph by construction; :func:`fit_barabasi_albert` fits the
   power-law exponent of an *empirical* degree sequence by MLE
   (Clauset, Shalizi, Newman 2009, *SIAM Rev.* 51: 661) so the null
   baseline is calibrated to the data, not hard-coded at *m=2*.

Pure-function API. No I/O. Determinism via explicit seeds.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
from numpy.typing import NDArray

from .errors import InvalidExposureMatrixError, InvalidNodeLabelsError

__all__ = [
    "InterbankTopology",
    "from_exposure_matrix",
    "barabasi_albert_null",
]


@dataclass(frozen=True, slots=True)
class InterbankTopology:
    """Frozen interbank topology.

    Attributes
    ----------
    adjacency
        Binary adjacency, ``int8`` shape ``(N, N)``, zero diagonal.
        ``adjacency[i, j] == 1`` iff there is a directed edge *i → j*
        in the support graph (lending from *i* to *j*). May be
        symmetric (BA null) or asymmetric (empirical exposures).
    weights
        Real, non-negative magnitudes shape ``(N, N)``, zero diagonal.
        Symmetric iff ``adjacency`` is symmetric. ``None`` when the
        topology was generated synthetically.
    node_labels
        Tuple of node identifiers; length ``N``.
    source_label
        Free-form provenance tag, e.g. ``"e-MID_2011-Q3"`` or
        ``"BA_null_m=3_seed=42"``.
    snapshot_date
        Calendar date the snapshot pertains to. ``None`` when the
        topology represents a static null model.

    Invariants
    ----------
    INV-TOP1: ``adjacency`` is binary, square 2-D, zero-diagonal.
    INV-TOP2: ``weights`` (when present) is non-negative, finite,
              zero-diagonal, with the same shape as ``adjacency``.
    INV-TOP3: ``len(node_labels) == adjacency.shape[0]``.
    INV-TOP4 (asymmetry): for empirical directed inputs, the bound
              ``mean(adjacency != adjacency.T) > 0`` is reported but
              not enforced — symmetric empirical graphs are valid
              edge cases (e.g. fully reciprocated lending).
    """

    adjacency: NDArray[np.int8]
    node_labels: tuple[str, ...]
    source_label: str
    weights: NDArray[np.float64] | None = None
    snapshot_date: date | None = None

    def __post_init__(self) -> None:
        a = self.adjacency
        if a.ndim != 2 or a.shape[0] != a.shape[1]:
            raise ValueError(f"INV-TOP1: adjacency must be square 2-D, got shape={a.shape}")
        n = a.shape[0]
        if not np.all((a == 0) | (a == 1)):
            raise ValueError("INV-TOP1: adjacency must be binary {0,1}")
        if np.any(np.diag(a) != 0):
            raise ValueError("INV-TOP1: adjacency must have zero diagonal")
        if len(self.node_labels) != n:
            raise ValueError(f"INV-TOP3: len(node_labels)={len(self.node_labels)} != N={n}")
        w = self.weights
        if w is not None:
            if w.shape != a.shape:
                raise ValueError(f"INV-TOP2: weights shape={w.shape} != adjacency {a.shape}")
            if np.any(w < 0):
                raise ValueError("INV-TOP2: weights must be non-negative")
            if not np.isfinite(w).all():
                raise ValueError("INV-TOP2: weights must be finite (no NaN/Inf)")
            if np.any(np.diag(w) != 0):
                raise ValueError("INV-TOP2: weights must have zero diagonal")
        # Freeze arrays to prevent silent mutation downstream.
        a_frozen = np.array(a, dtype=np.int8, copy=True)
        a_frozen.flags.writeable = False
        object.__setattr__(self, "adjacency", a_frozen)
        if w is not None:
            w_frozen = np.array(w, dtype=np.float64, copy=True)
            w_frozen.flags.writeable = False
            object.__setattr__(self, "weights", w_frozen)

    @property
    def n_nodes(self) -> int:
        return int(self.adjacency.shape[0])

    @property
    def is_symmetric(self) -> bool:
        return bool(np.array_equal(self.adjacency, self.adjacency.T))

    @property
    def asymmetry_fraction(self) -> float:
        """Fraction of off-diagonal entries that differ between A and A.T.

        ``0.0`` for fully symmetric graphs; bounded above by 1.0. Used
        by the asymmetry-invariant test on real-data adapters.
        """
        a = self.adjacency
        if a.shape[0] <= 1:
            return 0.0
        diff = a != a.T
        # Off-diagonal entries only; diagonal is zero on both sides.
        np.fill_diagonal(diff, False)
        n = a.shape[0]
        denom = float(n * (n - 1))
        return float(diff.sum()) / denom if denom > 0 else 0.0

    @property
    def in_degree(self) -> NDArray[np.int64]:
        """Number of incoming edges per node (sum over rows)."""
        out: NDArray[np.int64] = self.adjacency.sum(axis=0, dtype=np.int64)
        return out

    @property
    def out_degree(self) -> NDArray[np.int64]:
        """Number of outgoing edges per node (sum over columns)."""
        out: NDArray[np.int64] = self.adjacency.sum(axis=1, dtype=np.int64)
        return out

    @property
    def degree(self) -> NDArray[np.int64]:
        """Total degree per node (in + out). For symmetric graphs equals 2*out_degree."""
        out: NDArray[np.int64] = self.in_degree + self.out_degree
        return out


def from_exposure_matrix(
    exposures: NDArray[np.float64],
    node_labels: tuple[str, ...],
    *,
    threshold: float = 0.0,
    source_label: str = "empirical_exposure",
    directed: bool = True,
    snapshot_date: date | None = None,
) -> InterbankTopology:
    """Build an :class:`InterbankTopology` from a directed exposure matrix.

    Parameters
    ----------
    exposures
        Real, non-negative matrix shape ``(N, N)``. ``exposures[i, j]``
        is the magnitude of *i*'s exposure to *j* (e.g. lending volume).
    node_labels
        Length-``N`` tuple of node identifiers.
    threshold
        **Strict** lower cutoff: ``A[i, j] = 1`` iff
        ``weights[i, j] > threshold`` (an entry equal to ``threshold``
        is *not* an edge). Default ``0.0`` admits every strictly-
        positive entry — zero-exposure cells never become edges.
    source_label
        Provenance tag stored on the resulting topology.
    directed
        If ``True`` (default), preserve the asymmetric exposure
        structure: ``A[i,j] = 1`` iff ``exposures[i,j] > threshold``.
        If ``False``, symmetrise via :math:`(E + E^T)/2` before
        thresholding — used only by the null baseline.
    snapshot_date
        Optional calendar date the snapshot pertains to. Required for
        temporal-snapshot pipelines (e-MID quarterly, BIS LBS).

    HARD_FAIL conditions
    --------------------
    * ``exposures`` not 2-D / not square ⇒ :class:`InvalidExposureMatrixError`.
    * Length of ``node_labels`` ≠ N ⇒ :class:`InvalidNodeLabelsError`.
    * ``node_labels`` contain duplicates or empty strings ⇒
      :class:`InvalidNodeLabelsError`.
    * ``exposures`` contains negatives, NaN, or Inf ⇒
      :class:`InvalidExposureMatrixError`.
    * ``threshold`` < 0 ⇒ :class:`InvalidExposureMatrixError`.
    """
    e = np.asarray(exposures, dtype=np.float64)
    if e.ndim != 2 or e.shape[0] != e.shape[1]:
        raise InvalidExposureMatrixError(f"exposures must be square 2-D, got shape={e.shape}")
    if e.shape[0] != len(node_labels):
        raise InvalidNodeLabelsError(
            f"node_labels length {len(node_labels)} != exposures dim {e.shape[0]}"
        )
    if any(lbl is None for lbl in node_labels):
        raise InvalidNodeLabelsError("node_labels must not contain None")
    if any(not isinstance(lbl, str) for lbl in node_labels):
        raise InvalidNodeLabelsError("node_labels must contain only str values")
    if any(lbl.strip() == "" for lbl in node_labels):
        raise InvalidNodeLabelsError(
            "node_labels must not contain empty or whitespace-only strings"
        )
    if len(set(node_labels)) != len(node_labels):
        raise InvalidNodeLabelsError("node_labels must be unique")
    if not np.isfinite(e).all():
        raise InvalidExposureMatrixError("exposures must be finite (no NaN/Inf)")
    if np.any(e < 0):
        raise InvalidExposureMatrixError("exposures must be non-negative")
    if threshold < 0:
        raise InvalidExposureMatrixError(f"threshold must be >= 0, got {threshold}")
    if directed:
        weights = np.array(e, dtype=np.float64, copy=True)
    else:
        weights = 0.5 * (e + e.T)
    np.fill_diagonal(weights, 0.0)
    adj = (weights > threshold).astype(np.int8)
    np.fill_diagonal(adj, 0)
    return InterbankTopology(
        adjacency=adj,
        weights=weights,
        node_labels=tuple(node_labels),
        source_label=source_label,
        snapshot_date=snapshot_date,
    )


def barabasi_albert_null(
    n_nodes: int,
    m: int,
    *,
    seed: int,
    source_label: str | None = None,
) -> InterbankTopology:
    """Barabási–Albert preferential attachment, *m* edges per new node.

    Implementation is self-contained (no NetworkX dependency). Produces
    a *symmetric* graph by construction — used as the null baseline of
    the falsification battery, never as a model of the real economy.

    Empirical anchor: :math:`m \\in \\{2, 3, 4\\}` reproduces interbank
    degree distributions observed in Boss et al. 2004 and Soramäki et
    al. 2007. The mean degree of the resulting graph is ``2m`` for
    large ``n``. To pick *m* directly from data use
    :func:`research.systemic_risk.network_fitting.fit_barabasi_albert`.

    Parameters
    ----------
    n_nodes
        Final number of nodes (must be > ``m``).
    m
        Edges added per new node (must be >= 1).
    seed
        Seed for ``np.random.default_rng``. Required.
    source_label
        Optional override for the resulting ``source_label`` field.
    """
    if n_nodes <= m:
        raise ValueError(f"n_nodes={n_nodes} must be > m={m}")
    if m < 1:
        raise ValueError(f"m must be >= 1, got {m}")

    rng = np.random.default_rng(seed)
    adj = np.zeros((n_nodes, n_nodes), dtype=np.int8)
    # Seed graph: complete on m+1 nodes so every initial node has degree m.
    for i in range(m + 1):
        for j in range(i + 1, m + 1):
            adj[i, j] = 1
            adj[j, i] = 1
    # Repeated nodes list for the standard PA draw without replacement.
    repeated: list[int] = []
    for i in range(m + 1):
        repeated.extend([i] * m)
    for new_node in range(m + 1, n_nodes):
        targets: set[int] = set()
        while len(targets) < m:
            t = int(repeated[int(rng.integers(0, len(repeated)))])
            if t != new_node:
                targets.add(t)
        for t in targets:
            adj[new_node, t] = 1
            adj[t, new_node] = 1
            repeated.append(t)
        repeated.extend([new_node] * m)
    label = source_label if source_label is not None else f"BA_null_m={m}_seed={seed}"
    return InterbankTopology(
        adjacency=adj,
        weights=None,
        node_labels=tuple(f"n{i}" for i in range(n_nodes)),
        source_label=label,
    )
