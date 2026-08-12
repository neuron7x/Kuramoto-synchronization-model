# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Null-model baseline generators for the falsification battery.

The official validation protocol (§ 8) requires every claimed
detection to be compared against at least six orthogonal null
baselines. A claim that does not survive *all six* is, by
construction, indistinguishable from chance and may not advance
beyond ``HYPOTHESIS`` tier.

The six baselines, in order of stringency:

1. **degree-preserving randomization** — rewires edges while
   preserving each node's in-degree and out-degree (Maslov-Sneppen
   shuffling on directed graphs). Tests whether the *signal*
   depends on more than the marginal connectivity.
2. **shuffled time labels** — the score time series is permuted
   along the time axis. Destroys temporal ordering. Tests whether
   any pre-event elevation is real or an artefact of sample size.
3. **random exposure weights** — the binary adjacency is held
   fixed, but every non-zero weight is replaced by an independent
   draw from the empirical weight distribution. Tests whether the
   *magnitudes* carry signal beyond the support graph.
4. **static topology baseline** — the time-averaged adjacency is
   substituted for every snapshot. Tests whether the temporal
   evolution of the graph carries any predictive signal.
5. **non-Kuramoto baseline** — replaces the order-parameter score
   with the equivalent statistic from a linear-correlation
   surrogate (mean pairwise Pearson correlation). Tests whether
   the *non-linearity* of phase-coupling matters.
6. **crisis-date permutation baseline** — the crisis dates
   themselves are shuffled across the data span. Tests whether the
   detection coincides with the labelled events or with arbitrary
   dates.

Each generator is a pure function returning a :class:`NullSurrogate`
that the caller passes back through the appropriate detector path
(score-replacing surrogates feed :func:`run_falsification`;
topology-replacing surrogates feed the score-construction stack).
A single composed audit entry-point that orchestrates all six is
deferred until the empirical-data ingest lands — at that point the
contract for "valid score from a surrogate topology" becomes
testable end-to-end.

Pure-function API. No I/O. Determinism via explicit ``seed``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from .event_ledger import BankingCrisisEvent, BankingCrisisLedger
from .topology import InterbankTopology

__all__ = [
    "NullName",
    "NullSurrogate",
    "degree_preserving_randomization",
    "shuffled_time_labels",
    "random_exposure_weights",
    "static_topology_baseline",
    "linear_correlation_surrogate",
    "permuted_crisis_dates",
]


NullName = Literal[
    "degree_preserving",
    "shuffled_time_labels",
    "random_exposure_weights",
    "static_topology",
    "linear_correlation",
    "permuted_crisis_dates",
]


@dataclass(frozen=True, slots=True)
class NullSurrogate:
    """A single null-baseline output paired with its provenance."""

    name: NullName
    score: NDArray[np.float64] | None
    topology: InterbankTopology | None
    ledger: BankingCrisisLedger | None
    seed: int


# ---------------------------------------------------------------------------
# 1. degree-preserving randomization (Maslov-Sneppen on directed graph)
# ---------------------------------------------------------------------------


def degree_preserving_randomization(
    topology: InterbankTopology,
    *,
    seed: int,
    n_swaps: int | None = None,
) -> NullSurrogate:
    """Maslov-Sneppen edge swap preserving in- and out-degree per node.

    Implementation: pick two directed edges ``(a→b)`` and ``(c→d)``
    uniformly at random; if ``a≠c``, ``a≠d``, ``b≠c``, ``b≠d`` and
    neither ``(a→d)`` nor ``(c→b)`` already exists, rewire to
    ``(a→d)`` and ``(c→b)``. Repeat ``n_swaps`` times. Default
    ``n_swaps = 10 * E`` (Milo et al. 2003).
    """
    rng = np.random.default_rng(seed)
    a = np.array(topology.adjacency, dtype=np.int8, copy=True)
    a.flags.writeable = True
    edges_iv = np.argwhere(a == 1)
    n_edges = edges_iv.shape[0]
    if n_edges < 2:
        # Nothing to swap; return a defensive copy.
        return NullSurrogate(
            name="degree_preserving",
            score=None,
            topology=InterbankTopology(
                adjacency=a,
                node_labels=topology.node_labels,
                source_label=f"{topology.source_label}::degree_preserving::seed={seed}",
            ),
            ledger=None,
            seed=seed,
        )
    if n_swaps is None:
        n_swaps = 10 * n_edges
    edges = [tuple(int(x) for x in row) for row in edges_iv]
    for _ in range(n_swaps):
        i, j = int(rng.integers(0, n_edges)), int(rng.integers(0, n_edges))
        if i == j:
            continue
        a_i, b_i = edges[i]
        c_i, d_i = edges[j]
        if len({a_i, b_i, c_i, d_i}) < 4:
            continue
        if a[a_i, d_i] == 1 or a[c_i, b_i] == 1:
            continue
        a[a_i, b_i] = 0
        a[c_i, d_i] = 0
        a[a_i, d_i] = 1
        a[c_i, b_i] = 1
        edges[i] = (a_i, d_i)
        edges[j] = (c_i, b_i)
    return NullSurrogate(
        name="degree_preserving",
        score=None,
        topology=InterbankTopology(
            adjacency=a,
            node_labels=topology.node_labels,
            source_label=f"{topology.source_label}::degree_preserving::seed={seed}",
        ),
        ledger=None,
        seed=seed,
    )


# ---------------------------------------------------------------------------
# 2. shuffled time labels
# ---------------------------------------------------------------------------


def shuffled_time_labels(
    score: NDArray[np.float64],
    *,
    seed: int,
) -> NullSurrogate:
    """Permute the score series along the time axis. Destroys ordering."""
    s = np.asarray(score, dtype=np.float64)
    if s.ndim != 1:
        raise ValueError(f"score must be 1-D, got shape={s.shape}")
    rng = np.random.default_rng(seed)
    permuted = rng.permutation(s)
    return NullSurrogate(
        name="shuffled_time_labels",
        score=permuted,
        topology=None,
        ledger=None,
        seed=seed,
    )


# ---------------------------------------------------------------------------
# 3. random exposure weights (preserves binary support)
# ---------------------------------------------------------------------------


def random_exposure_weights(
    topology: InterbankTopology,
    *,
    seed: int,
) -> NullSurrogate:
    """Resample weights from the empirical distribution while preserving the
    binary adjacency.

    Implementation note: only meaningful when ``topology.weights is not None``.
    For a topology without empirical weights (e.g. BA null), returns a
    surrogate whose weights are zeroed.
    """
    rng = np.random.default_rng(seed)
    a = np.array(topology.adjacency, dtype=np.int8, copy=True)
    n = a.shape[0]
    if topology.weights is None:
        new_w: NDArray[np.float64] | None = None
    else:
        empirical = topology.weights[a == 1]
        if empirical.size == 0:
            new_w = np.zeros((n, n), dtype=np.float64)
        else:
            sampled = rng.choice(empirical, size=int(a.sum()), replace=True)
            new_w = np.zeros((n, n), dtype=np.float64)
            new_w[a == 1] = sampled
            np.fill_diagonal(new_w, 0.0)
    return NullSurrogate(
        name="random_exposure_weights",
        score=None,
        topology=InterbankTopology(
            adjacency=a,
            weights=new_w,
            node_labels=topology.node_labels,
            source_label=f"{topology.source_label}::random_weights::seed={seed}",
        ),
        ledger=None,
        seed=seed,
    )


# ---------------------------------------------------------------------------
# 4. static topology baseline (time-mean adjacency)
# ---------------------------------------------------------------------------


def static_topology_baseline(
    snapshots: tuple[InterbankTopology, ...],
    *,
    seed: int,
) -> NullSurrogate:
    """Substitute the time-mean adjacency for every snapshot.

    Strips temporal evolution of the graph. Returns a single
    surrogate topology whose binary support is the union of all
    snapshot supports and whose weights (if present on every
    snapshot) are the snapshot mean.
    """
    if len(snapshots) == 0:
        raise ValueError("snapshots tuple must be non-empty")
    n = snapshots[0].n_nodes
    if any(t.n_nodes != n for t in snapshots):
        raise ValueError("all snapshots must share the same node count")
    union = np.zeros((n, n), dtype=np.int8)
    for t in snapshots:
        union |= t.adjacency
    # Mean weights only when every snapshot carries a weights matrix.
    if all(t.weights is not None for t in snapshots):
        mean_w = np.mean(
            np.stack([t.weights for t in snapshots]),  # type: ignore[misc]
            axis=0,
        ).astype(np.float64)
        np.fill_diagonal(mean_w, 0.0)
    else:
        mean_w = None
    return NullSurrogate(
        name="static_topology",
        score=None,
        topology=InterbankTopology(
            adjacency=union,
            weights=mean_w,
            node_labels=snapshots[0].node_labels,
            source_label=f"static_topology::N_snapshots={len(snapshots)}::seed={seed}",
        ),
        ledger=None,
        seed=seed,
    )


# ---------------------------------------------------------------------------
# 5. linear-correlation surrogate (non-Kuramoto)
# ---------------------------------------------------------------------------


def linear_correlation_surrogate(
    spreads: NDArray[np.float64],
    *,
    seed: int,
) -> NullSurrogate:
    """Replace the Kuramoto order parameter with mean pairwise Pearson
    correlation over a rolling window — a *linear* coherence statistic.

    Returns a per-bank-pair correlation matrix collapsed to a single
    series (mean off-diagonal correlation per time-step) for direct
    A/B comparison with the Kuramoto-based score.

    Parameters
    ----------
    spreads
        Shape ``(T, N_banks)``, finite log-returns or interbank
        spreads (canonical ``(T, N)`` layout).
    """
    s = np.asarray(spreads, dtype=np.float64)
    if s.ndim != 2:
        raise ValueError(f"spreads must be 2-D (T, N), got shape={s.shape}")
    if s.shape[0] < 2:
        raise ValueError(f"spreads must have at least 2 time samples, got T={s.shape[0]}")
    if not np.isfinite(s).all():
        raise ValueError("spreads must be finite")
    # Mean off-diagonal Pearson correlation per single rolling step
    # is collapsed here into a single time-resolved series via a
    # 30-step trailing window. Caller may override via direct
    # composition if a different window is needed.
    window = min(30, s.shape[0])
    out = np.full(s.shape[0], np.nan, dtype=np.float64)
    for t in range(window - 1, s.shape[0]):
        seg = s[t - window + 1 : t + 1]
        # Centre + scale.
        seg_c = seg - seg.mean(axis=0, keepdims=True)
        std = seg_c.std(axis=0, ddof=1)
        # bounds: zero-variance columns ⇒ undefined Pearson;
        # set their pairwise contribution to NaN so the mean
        # propagates the signal honestly.
        std_safe = np.where(std > 0, std, np.nan)
        norm = seg_c / std_safe
        corr = (norm.T @ norm) / (window - 1)
        np.fill_diagonal(corr, np.nan)
        out[t] = float(np.nanmean(corr))
    return NullSurrogate(
        name="linear_correlation",
        score=out,
        topology=None,
        ledger=None,
        seed=seed,
    )


# ---------------------------------------------------------------------------
# 6. permuted crisis dates
# ---------------------------------------------------------------------------


def permuted_crisis_dates(
    ledger: BankingCrisisLedger,
    *,
    earliest: date,
    latest: date,
    seed: int,
) -> NullSurrogate:
    """Shuffle every event start (and matching end) to a uniformly random
    date in ``[earliest, latest - duration]``.

    Preserves the per-event duration distribution so the null
    population is comparable to the empirical one.
    """
    if latest <= earliest:
        raise ValueError(f"latest={latest} must exceed earliest={earliest}")
    span_days = (latest - earliest).days
    rng = np.random.default_rng(seed)
    permuted: list[BankingCrisisEvent] = []
    from datetime import timedelta as _td

    for ev in ledger.events:
        duration_days = (ev.end - ev.start).days
        max_offset = max(0, span_days - duration_days)
        offset = int(rng.integers(0, max_offset + 1))
        new_start = earliest + _td(days=offset)
        new_end = new_start + _td(days=duration_days)
        permuted.append(
            BankingCrisisEvent(
                country=ev.country,
                start=new_start,
                end=new_end,
                source=ev.source,
                label=f"{ev.label}_permuted",
            )
        )
    return NullSurrogate(
        name="permuted_crisis_dates",
        score=None,
        topology=None,
        ledger=BankingCrisisLedger(events=tuple(permuted)),
        seed=seed,
    )
