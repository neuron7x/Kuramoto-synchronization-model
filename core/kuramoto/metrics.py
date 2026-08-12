# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Emergent-dynamics metrics for a :class:`NetworkState` (protocol M2.4).

Given a phase trajectory and (optionally) the identified coupling
matrix we compute the observables that the methodology treats as the
public output of the NetworkKuramotoEngine:

- **Global order parameter** ``R(t) = |mean_i exp(iθ_i(t))|`` —
  classical Kuramoto coherence, in ``[0, 1]``.
- **Cluster order parameters** ``R_c(t)`` per signed community detected
  on the coupling graph. Communities are found by an efficient
  spectral-sign heuristic (see :func:`_signed_communities`); this
  avoids a hard dependency on :mod:`leidenalg` while still giving the
  right answer on planted-partition benchmarks.
- **Metastability** ``Var_t R(t)``.
- **Chimera index** — per-timestep variance of the per-node local
  order parameter computed on each node's coupling neighbourhood.
  Large values at a given time indicate coexistence of synchronised
  and desynchronised sub-populations.
- **Critical slowing down indicators** — rolling variance and lag-1
  autocorrelation of ``R(t)``. Both increase before bifurcations.
- **Edge entropy** — the mean permutation entropy (order 3) of the
  coupling series ``K_ij(t)`` for time-varying coupling inputs. For
  static ``K`` the edge entropy is 0 by convention.

All helpers use only ``numpy`` + ``scipy``; no ``leidenalg``,
``ewstools`` or ``antropy`` dependency. The outputs go into an
:class:`EmergentMetrics` contract, which enforces shape and range
invariants.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .contracts import CouplingMatrix, EmergentMetrics, PhaseMatrix

__all__ = [
    "MetricsConfig",
    "compute_metrics",
    "order_parameter",
    "chimera_index",
    "rolling_csd",
    "signed_communities",
    "permutation_entropy",
]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MetricsConfig:
    """Hyperparameters for :func:`compute_metrics`.

    Attributes
    ----------
    csd_window : int
        Rolling window length for critical-slowing-down indicators
        (variance and lag-1 autocorrelation of ``R(t)``). Must be
        positive and at most ``T``.
    n_clusters_max : int
        Upper bound on the number of communities the signed
        community detector is allowed to return. A fresh bipartition
        is attempted as long as ``n_clusters`` is below this cap and
        the most recent split reduces the signed-modularity objective.
    min_community_size : int
        Smallest acceptable community. Splits producing a community
        below this size are rejected — the methodology prefers a
        handful of large communities to many tiny ones.
    perm_entropy_order : int
        Permutation-entropy order used by the edge entropy metric.
        ``order = 3`` (six ordinal patterns) is the standard choice.
    """

    csd_window: int = 50
    n_clusters_max: int = 8
    min_community_size: int = 2
    perm_entropy_order: int = 3

    def __post_init__(self) -> None:
        if self.csd_window < 2:
            raise ValueError("csd_window must be ≥ 2")
        if self.n_clusters_max < 1:
            raise ValueError("n_clusters_max must be ≥ 1")
        if self.min_community_size < 1:
            raise ValueError("min_community_size must be ≥ 1")
        if self.perm_entropy_order < 2:
            raise ValueError("perm_entropy_order must be ≥ 2")


# ---------------------------------------------------------------------------
# Order parameter
# ---------------------------------------------------------------------------


def order_parameter(theta: np.ndarray, axis: int = 1) -> np.ndarray:
    """Kuramoto complex order parameter magnitude.

    ``|(1/N) Σ_k exp(i θ_k(t))|`` computed along ``axis`` (default:
    node axis). For a shape-``(T, N)`` phase matrix the output has
    shape ``(T,)``.

    Fail-closed on non-finite phases: ``np.exp(1j*nan)`` is NaN, which would
    leak past INV-K1 (R ∈ [0, 1]) — ``np.abs`` of a NaN mean is NaN, not a
    valid order parameter. A non-finite phase is a contract violation, so we
    raise rather than emit a silently out-of-bounds R.
    """
    theta = np.asarray(theta, dtype=np.float64)
    if not bool(np.all(np.isfinite(theta))):
        raise ValueError("order_parameter: theta must be finite (INV-K1 R∈[0,1])")
    z = np.mean(np.exp(1j * theta), axis=axis)
    return np.asarray(np.abs(z), dtype=np.float64)


def chimera_index(theta: np.ndarray, adjacency: np.ndarray) -> np.ndarray:
    """Variance across nodes of the neighbourhood-local order parameter.

    For every node ``i`` we compute ``r_i(t) = |mean_{j∈N(i)} exp(i θ_j(t))|``
    using the columns of the signed adjacency matrix as the local
    neighbourhood. The chimera index is the cross-node variance of
    ``r_i(t)`` at each timestep — it peaks when the network has
    regions of sync and de-sync coexisting at the same time.
    """
    T, N = theta.shape
    adj = np.abs(np.asarray(adjacency, dtype=np.float64))
    # Include the node itself in its neighbourhood so isolated nodes
    # get r_i = 1 rather than NaN
    adj = adj + np.eye(N)
    row_sum = adj.sum(axis=1, keepdims=True)
    row_sum = np.where(row_sum > 0, row_sum, 1.0)
    weights = adj / row_sum  # (N, N)
    exp_phase = np.exp(1j * theta)  # (T, N)
    # r_i(t) = |Σ_j weights[i,j] · exp(iθ_j(t))|
    local_complex = exp_phase @ weights.T  # (T, N)
    r_local = np.abs(local_complex)
    return np.asarray(np.var(r_local, axis=1, ddof=0), dtype=np.float64)


# ---------------------------------------------------------------------------
# Critical slowing down
# ---------------------------------------------------------------------------


def rolling_csd(R: np.ndarray, window: int) -> tuple[np.ndarray, np.ndarray]:
    """Return rolling variance and lag-1 autocorrelation of ``R``.

    The window is trailing (causal) so the metric is usable online
    without look-ahead bias. The first ``window - 1`` samples are
    padded with the full-window value at index ``window - 1`` to
    preserve the ``(T,)`` output shape.
    """
    T = R.shape[0]
    if window < 2 or window > T:
        raise ValueError(f"window must lie in [2, T]={T}; got {window}")
    var = np.empty(T, dtype=np.float64)
    ac1 = np.empty(T, dtype=np.float64)
    for t in range(T):
        # bounds: rolling-window lower index, clamped to 0 at the series start
        # (array indexing, not a physics quantity).
        lo = max(0, t - window + 1)
        seg = R[lo : t + 1]
        if seg.shape[0] < 2:
            var[t] = 0.0
            ac1[t] = 0.0
            continue
        var[t] = float(np.var(seg, ddof=0))
        if seg.shape[0] >= 3 and float(np.var(seg, ddof=0)) > 1e-12:
            a = seg[:-1] - seg[:-1].mean()
            b = seg[1:] - seg[1:].mean()
            denom = float(np.sqrt(np.dot(a, a) * np.dot(b, b)))
            ac1[t] = float(np.dot(a, b) / denom) if denom > 0 else 0.0
        else:
            ac1[t] = 0.0
    return var, ac1


# ---------------------------------------------------------------------------
# Signed community detection (lightweight, dependency-free)
# ---------------------------------------------------------------------------


def _canonical_eigvec_sign(v: np.ndarray) -> np.ndarray:
    """Return ``v`` with a deterministic sign convention.

    ``np.linalg.eigh`` returns eigenvectors with arbitrary sign: ``v``
    and ``-v`` are both valid principal eigenvectors. When the downstream
    split rule is ``v >= 0`` this ambiguity permutes the two halves of
    the bipartition. We fix the sign by requiring the coordinate of
    largest magnitude to be non-negative; tie-breaks on magnitude fall
    to the smallest index, so the convention is deterministic for every
    non-zero ``v``.

    The zero vector is returned unchanged — the caller must handle the
    degenerate split separately because both halves are empty by
    construction.
    """
    if v.size == 0:
        return v
    idx = int(np.argmax(np.abs(v)))
    pivot = float(v[idx])
    if pivot < 0.0:
        return -v
    return v


def _canonicalize_labels(labels: np.ndarray) -> np.ndarray:
    """Rewrite community ids so the ordering is permutation-invariant.

    The primary sort key is community *size*, descending: the biggest
    community always receives id ``0``. Ties break on the *smallest
    member index* ascending, so two communities of equal size fall
    into a stable order determined only by node identity. This removes
    two sources of label instability:

    1. **Eigenvector sign ambiguity** — when the recursive splitter
       flips which half receives ``new_id = max + 1`` the raw labels
       permute; after canonicalisation the partition is unchanged.
    2. **Split-order dependence** — recursive splits of different
       sub-communities can interleave in different orders on perturbed
       inputs; the size-then-min-index ordering is invariant under
       those interleavings.

    The partition (the equivalence classes on nodes) is preserved
    exactly — only the integer ids are rewritten. The returned labels
    are a dense ``0..C-1`` range where ``C`` is the number of
    communities.
    """
    labels = np.ascontiguousarray(labels, dtype=np.int64)
    unique, first_occurrence = np.unique(labels, return_index=True)
    sizes = np.array([int((labels == u).sum()) for u in unique], dtype=np.int64)
    # Sort by (-size, first_occurrence) so the biggest community wins;
    # ties break on the smallest node index.
    order = np.lexsort((first_occurrence, -sizes))
    remap = np.empty(unique.max() + 1, dtype=np.int64)
    for new_id, old_pos in enumerate(order):
        remap[unique[old_pos]] = new_id
    return np.asarray(remap[labels], dtype=np.int64)


def _signed_modularity(W: np.ndarray, labels: np.ndarray) -> float:
    """Signed modularity ``Q⁺ − Q⁻`` (Gómez, Jensen & Arenas, 2009).

    ``W`` is the signed coupling matrix; positive and negative edges
    contribute with opposite signs to the null model, so communities
    are rewarded for keeping excitatory edges inside and inhibitory
    edges between themselves.
    """
    W_pos = np.maximum(W, 0.0)
    W_neg = np.maximum(-W, 0.0)
    m_pos = float(W_pos.sum())
    m_neg = float(W_neg.sum())

    def _q(A: np.ndarray, m: float) -> float:
        if m <= 0:
            return 0.0
        k = A.sum(axis=1)
        q = 0.0
        for c in np.unique(labels):
            mask = labels == c
            A_in = A[np.ix_(mask, mask)].sum()
            k_in = k[mask].sum()
            q += A_in / m - (k_in / m) ** 2
        return float(q)

    w_total = m_pos + m_neg
    if w_total == 0:
        return 0.0
    return (m_pos * _q(W_pos, m_pos) - m_neg * _q(W_neg, m_neg)) / w_total


def signed_communities(
    K: np.ndarray,
    *,
    n_clusters_max: int = 8,
    min_community_size: int = 2,
    random_state: int = 0,
) -> np.ndarray:
    """Detect communities via recursive spectral sign on signed ``K``.

    Algorithm
    ---------
    1. Symmetrise ``K`` into ``W = (K + Kᵀ) / 2`` so the spectrum is
       real.
    2. Start with every node in community 0.
    3. Repeatedly pick the community whose split most improves the
       signed modularity. The split is driven by the sign of the
       Fiedler vector of the symmetric ``W``-restricted subgraph;
       when the graph has strong negative edges this naturally
       separates excitatory and inhibitory clusters.
    4. Stop when splitting any remaining community would either
       violate ``min_community_size`` or fail to raise the
       signed-modularity score.

    This is a lightweight stand-in for Leiden / Louvain on signed
    graphs that avoids bringing in ``leidenalg`` as a dependency; on
    planted-partition benchmarks it recovers the ground-truth
    communities with NMI ≥ 0.9 for typical sparsity levels.

    Label canonicalisation
    ----------------------
    The returned labels form a dense ``0..C-1`` range canonicalised
    so that the biggest community always has id ``0``; ties on size
    break on the smallest member index ascending. Together with the
    eigenvector-sign canonicalisation applied during every recursive
    split this makes the output *permutation-invariant* under small
    perturbations of ``K``: if two inputs produce the same partition
    they produce the same labels bit-for-bit. Downstream callers
    (``EmergentMetrics.R_cluster``, ``NetworkKuramotoFeature``) bind
    to these ids across batch recalibrations, so stability is a
    correctness invariant, not a cosmetic.
    """
    N = K.shape[0]
    W = 0.5 * (K + K.T)
    labels = np.zeros(N, dtype=np.int64)
    current_q = _signed_modularity(W, labels)
    rng = np.random.default_rng(random_state)

    while True:
        n_current = int(labels.max() + 1)
        if n_current >= n_clusters_max:
            break
        best_gain = 0.0
        best_split: tuple[int, np.ndarray] | None = None
        for c in range(n_current):
            mask = labels == c
            if mask.sum() < 2 * min_community_size:
                continue
            # Spectral sign split on W restricted to this community
            sub = W[np.ix_(mask, mask)]
            # Random tie-break vector to avoid degenerate ties
            sub = sub + 1e-9 * rng.standard_normal(sub.shape)
            sub_sym = 0.5 * (sub + sub.T)
            eigvals, eigvecs = np.linalg.eigh(sub_sym)
            # Fiedler-like split: use the eigenvector corresponding
            # to the largest eigenvalue (maximises intra-cluster
            # positive weight). ``eigh`` returns eigenvectors with
            # arbitrary sign; canonicalise so ``v >= 0`` has a
            # deterministic meaning (otherwise ``sub_a`` / ``sub_b``
            # permute under numerical perturbation and the new-id
            # assignment swaps cluster labels between calls).
            v = _canonical_eigvec_sign(eigvecs[:, -1])
            sub_a = v >= 0
            sub_b = ~sub_a
            if sub_a.sum() < min_community_size or sub_b.sum() < min_community_size:
                continue
            trial_labels = labels.copy()
            # New community id for the `b` half
            new_id = int(trial_labels.max() + 1)
            community_idx = np.where(mask)[0]
            trial_labels[community_idx[sub_b]] = new_id
            q = _signed_modularity(W, trial_labels)
            gain = q - current_q
            if gain > best_gain:
                best_gain = gain
                best_split = (c, trial_labels)
        if best_split is None:
            break
        _, labels = best_split
        current_q = current_q + best_gain

    # Canonicalise labels: biggest community first, ties broken by the
    # smallest member index. Without this, two runs on tiny
    # perturbations of the same ``K`` return the same partition but
    # with permuted ids — which breaks ``R_cluster`` dict keys and
    # downstream ``kuramoto_R_cluster_{c}`` feature vocabulary.
    return _canonicalize_labels(labels)


# ---------------------------------------------------------------------------
# Permutation entropy
# ---------------------------------------------------------------------------


def permutation_entropy(x: np.ndarray, order: int = 3) -> float:
    """Normalised permutation entropy (Bandt & Pompe, 2002).

    Returns a value in ``[0, 1]``. ``1`` means all ordinal patterns
    of length ``order`` are equally likely (maximum disorder); ``0``
    means the series is perfectly monotonic. Uses a pure-numpy
    implementation (no ``antropy`` dependency).
    """
    x = np.asarray(x, dtype=np.float64)
    if x.size < order:
        return 0.0
    # Sliding windows of length `order`
    n = x.size - order + 1
    windows = np.lib.stride_tricks.sliding_window_view(x, order)
    # Argsort ranks the positions; identical values are broken
    # deterministically by argsort's stable sort
    ranks = np.argsort(windows, axis=1)
    # Hash each permutation into a base-order integer
    weights = (order ** np.arange(order)).astype(np.int64)
    codes = ranks @ weights
    _, counts = np.unique(codes, return_counts=True)
    p = counts / n
    entropy = float(-np.sum(p * np.log(p)))
    # Normalise to [0, 1]
    max_entropy = float(np.log(math.factorial(order)))
    return entropy / max_entropy if max_entropy > 0 else 0.0


def _edge_entropy(K_series: np.ndarray | None, order: int) -> float:
    """Mean permutation entropy over all edges of a time-varying ``K``.

    Returns ``0.0`` for a static matrix (``K_series is None``).
    """
    if K_series is None or K_series.ndim != 3:
        return 0.0
    T_win, N, _ = K_series.shape
    scores: list[float] = []
    for i in range(N):
        for j in range(N):
            if i == j:
                continue
            series = K_series[:, i, j]
            if np.any(series != 0.0) and T_win >= order + 1:
                scores.append(permutation_entropy(series, order=order))
    return float(np.mean(scores)) if scores else 0.0


# ---------------------------------------------------------------------------
# High-level entry point
# ---------------------------------------------------------------------------


def compute_metrics(
    phases: PhaseMatrix,
    coupling: CouplingMatrix,
    *,
    config: MetricsConfig | None = None,
    K_series: np.ndarray | None = None,
) -> EmergentMetrics:
    """Assemble an :class:`EmergentMetrics` object from a full state.

    Parameters
    ----------
    phases
        Identified :class:`PhaseMatrix`.
    coupling
        Identified :class:`CouplingMatrix`.
    config
        Metric hyperparameters. Uses defaults if omitted.
    K_series
        Optional time-varying coupling tensor of shape ``(T_win, N, N)``
        produced by :mod:`core.kuramoto.dynamic_graph`. When supplied,
        the edge entropy uses the full trajectory; otherwise it is 0.
    """
    cfg = config or MetricsConfig()
    theta = np.asarray(phases.theta, dtype=np.float64)
    K = np.asarray(coupling.K, dtype=np.float64)
    T, N = theta.shape

    R_global = order_parameter(theta, axis=1)
    metastability = float(np.var(R_global, ddof=0))

    labels = signed_communities(
        K,
        n_clusters_max=cfg.n_clusters_max,
        min_community_size=cfg.min_community_size,
    )
    R_cluster: dict[int, np.ndarray] = {}
    for c in np.unique(labels):
        mask = labels == c
        if mask.sum() == 0:
            continue
        R_cluster[int(c)] = order_parameter(theta[:, mask], axis=1)

    chimera = chimera_index(theta, K)
    window = min(cfg.csd_window, T)
    csd_var, csd_ac = rolling_csd(R_global, window=window)

    edge_ent = _edge_entropy(K_series, cfg.perm_entropy_order)

    return EmergentMetrics(
        R_global=R_global,
        R_cluster=R_cluster,
        metastability=metastability,
        chimera_index=chimera,
        csd_variance=csd_var,
        csd_autocorr=csd_ac,
        edge_entropy=edge_ent,
        cluster_assignments=labels.astype(np.int64),
    )
