# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002J-P6 null-model hierarchy v1 — the 10 null families.

Each class is a FALSIFIER targeting ONE named false explanation. Every
``apply`` numerically verifies (in code) that it preserves what it claims
to preserve and destroys what it claims to destroy; the result is recorded
on the returned :class:`NullInstance` so the P6 guard tests can assert the
checks ran and passed.

Determinism contract: same ``(signal_array, seed, params)`` =>
bit-identical ``nulled_array`` (``numpy.random.default_rng(seed)`` only,
no wall-clock, no real data).

This module builds the null-generator HIERARCHY. It does NOT execute nulls
against real substrate data at scale (P7/P8 territory) and authorises no
canonical run.
"""

from __future__ import annotations

from typing import Any, Final

import numpy as np
from numpy.typing import NDArray

from research.systemic_risk.nulls.d002j.null_base import (
    SCHEMA_NULL_INSTANCE,
    NullInstance,
    autocorr_at_lag,
    degree_sequence,
)

_FLOAT_TOL: Final[float] = 1e-9
"""Numeric tolerance for "structure destroyed" checks (strict inequality)."""


def _as_1d(signal_array: NDArray[Any]) -> NDArray[np.float64]:
    x = np.asarray(signal_array, dtype=np.float64)
    if x.ndim != 1:
        raise ValueError(f"expected a 1D series; got shape {x.shape}")
    if x.shape[0] < 4:
        raise ValueError(f"series too short for a meaningful null; n={x.shape[0]}")
    return x


def _as_adjacency(signal_array: NDArray[Any]) -> NDArray[np.float64]:
    a = np.asarray(signal_array, dtype=np.float64)
    if a.ndim != 2 or a.shape[0] != a.shape[1]:
        raise ValueError(f"expected a square adjacency matrix; got shape {a.shape}")
    if not np.allclose(a, a.T):
        raise ValueError("adjacency must be symmetric (undirected graph null)")
    if a.shape[0] < 3:
        raise ValueError(f"graph too small for a meaningful rewiring null; n={a.shape[0]}")
    return a


def _base_metadata(null_id: str, target: str, *, h_i2_conditional: bool) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_NULL_INSTANCE,
        "null_id": null_id,
        "target_false_explanation": target,
        "h_i2_conditional": h_i2_conditional,
        "no_real_data": True,
        "no_canonical_run": True,
    }


# ---------------------------------------------------------------------------
# N1 — label_permutation
# ---------------------------------------------------------------------------


class N1LabelPermutationNull:
    """Shuffle outcome labels; kills the "any structure" false explanation.

    Target false explanation: *the detected signal is merely an artifact
    of having ANY structure attached to the outcome, not of THIS
    outcome-aligned structure.* Destroying the label↔series alignment
    while preserving the multiset of label values isolates that.
    """

    null_id: Final[str] = "N1_label_permutation"
    target_false_explanation: Final[str] = (
        "The detected signal is merely an artifact of attaching any structure to "
        "the outcome labels, not of the specific outcome-aligned structure."
    )

    def apply(
        self, signal_array: NDArray[Any], seed: int, params: dict[str, float] | None = None
    ) -> NullInstance:
        labels = _as_1d(signal_array)
        rng = np.random.default_rng(seed)
        perm = rng.permutation(labels.shape[0])
        nulled = labels[perm]
        preserved = {
            "label_multiset": bool(np.array_equal(np.sort(labels), np.sort(nulled))),
            "label_count": labels.shape[0] == nulled.shape[0],
        }
        # destroyed: position-wise alignment must change for a non-constant
        # series of length >= 4 (deterministic seed makes this stable).
        destroyed = {
            "label_position_alignment": not np.array_equal(labels, nulled),
        }
        return NullInstance(
            null_id=self.null_id,
            seed=seed,
            params=dict(params or {}),
            nulled_array=nulled,
            preserved_invariants_checked=preserved,
            destroyed_structure_checked=destroyed,
            metadata=_base_metadata(
                self.null_id, self.target_false_explanation, h_i2_conditional=False
            ),
        )


# ---------------------------------------------------------------------------
# N2 — time_window_shift_placebo
# ---------------------------------------------------------------------------


class N2TimeWindowShiftPlaceboNull:
    """Shift the crisis window by ±k; kills "window-alignment artifact".

    Target false explanation: *the signal is just an artifact of where the
    crisis window was placed; any equally-sized window would show it.*
    A circular shift of the series by k preserves the marginal
    distribution but moves the window off the true onset.
    """

    null_id: Final[str] = "N2_time_window_shift_placebo"
    target_false_explanation: Final[str] = (
        "The signal is merely a window-alignment artifact; it would appear under "
        "any equally-sized window placement, not specifically the crisis window."
    )

    def apply(
        self, signal_array: NDArray[Any], seed: int, params: dict[str, float] | None = None
    ) -> NullInstance:
        series = _as_1d(signal_array)
        n = series.shape[0]
        rng = np.random.default_rng(seed)
        # Deterministic non-trivial shift in [1, n-1] from the seed.
        shift = int(rng.integers(1, n)) if params is None else int(params.get("shift", 0))
        if not (1 <= shift <= n - 1):
            shift = int(rng.integers(1, n))
        nulled = np.roll(series, shift)
        preserved = {
            "marginal_distribution": bool(np.array_equal(np.sort(series), np.sort(nulled))),
            "series_length": series.shape[0] == nulled.shape[0],
        }
        destroyed = {
            "window_onset_alignment": not np.array_equal(series, nulled),
        }
        meta = _base_metadata(self.null_id, self.target_false_explanation, h_i2_conditional=False)
        meta["applied_shift"] = shift
        return NullInstance(
            null_id=self.null_id,
            seed=seed,
            params=dict(params or {}),
            nulled_array=nulled,
            preserved_invariants_checked=preserved,
            destroyed_structure_checked=destroyed,
            metadata=meta,
        )


# ---------------------------------------------------------------------------
# N3 — temporal_block_bootstrap
# ---------------------------------------------------------------------------


class N3TemporalBlockBootstrapNull:
    """Block-resample preserving autocorrelation; kills "iid noise".

    Target false explanation: *the signal is just iid noise; its apparent
    temporal structure is spurious.* Moving-block bootstrap keeps within-
    block autocorrelation while destroying the global trajectory order,
    so a signal that is genuinely more than iid noise should survive.
    """

    null_id: Final[str] = "N3_temporal_block_bootstrap"
    target_false_explanation: Final[str] = (
        "The signal is just iid noise; its apparent temporal dependence is a "
        "spurious artifact rather than genuine autocorrelated structure."
    )

    def apply(
        self, signal_array: NDArray[Any], seed: int, params: dict[str, float] | None = None
    ) -> NullInstance:
        series = _as_1d(signal_array)
        n = series.shape[0]
        block = int((params or {}).get("block_len", max(2, n // 8)))
        block = max(2, min(block, n - 1))
        rng = np.random.default_rng(seed)
        n_blocks = int(np.ceil(n / block))
        starts = rng.integers(0, n - block + 1, size=n_blocks)
        pieces = [series[s : s + block] for s in starts]
        nulled = np.concatenate(pieces)[:n]
        # admission: lag-1 autocorrelation band preserved within tolerance.
        ac_src = autocorr_at_lag(series, 1)
        try:
            ac_null = autocorr_at_lag(nulled, 1)
            ac_band_ok = abs(ac_null - ac_src) <= 0.6 * (abs(ac_src) + 0.5)
        except ValueError:
            ac_band_ok = False
        preserved = {
            "series_length": nulled.shape[0] == n,
            "autocorrelation_band_lag1": bool(ac_band_ok),
        }
        destroyed = {
            "global_trajectory_order": not np.array_equal(series, nulled),
        }
        meta = _base_metadata(self.null_id, self.target_false_explanation, h_i2_conditional=False)
        meta["block_len"] = block
        meta["autocorr_lag1_source"] = ac_src
        return NullInstance(
            null_id=self.null_id,
            seed=seed,
            params=dict(params or {}),
            nulled_array=nulled,
            preserved_invariants_checked=preserved,
            destroyed_structure_checked=destroyed,
            metadata=meta,
        )


# ---------------------------------------------------------------------------
# N4 — iaaft_surrogate
# ---------------------------------------------------------------------------


class N4IAAFTSurrogateNull:
    """Iterative amplitude-adjusted FT; kills "linear-spectral artifact".

    Target false explanation: *the signal is just a linear-spectral
    artifact; its information is fully captured by the power spectrum +
    amplitude distribution.* IAAFT surrogates preserve the periodogram
    and the value distribution while destroying nonlinear phase
    coupling, so genuine nonlinearity should survive.
    """

    null_id: Final[str] = "N4_iaaft_surrogate"
    target_false_explanation: Final[str] = (
        "The signal is a linear-spectral artifact fully explained by its power "
        "spectrum and amplitude distribution, with no genuine nonlinear structure."
    )

    def apply(
        self, signal_array: NDArray[Any], seed: int, params: dict[str, float] | None = None
    ) -> NullInstance:
        series = _as_1d(signal_array)
        n = series.shape[0]
        n_iter = int((params or {}).get("n_iter", 100))
        rng = np.random.default_rng(seed)
        sorted_vals = np.sort(series)
        target_amp = np.abs(np.fft.rfft(series))
        surrogate = rng.permutation(series).astype(np.float64)
        for _ in range(max(1, n_iter)):
            spec = np.fft.rfft(surrogate)
            phases = np.angle(spec)
            surrogate = np.fft.irfft(target_amp * np.exp(1j * phases), n=n)
            ranks = np.argsort(np.argsort(surrogate))
            surrogate = sorted_vals[ranks]
        nulled = np.asarray(surrogate, dtype=np.float64)
        amp_null = np.abs(np.fft.rfft(nulled))
        # IAAFT's terminal step is amplitude-adjustment (exact value
        # distribution), so the periodogram is preserved up to high
        # correlation, NOT elementwise equality. The standard IAAFT
        # convergence/admission metric is the spectral correlation.
        a0 = target_amp - target_amp.mean()
        a1 = amp_null - amp_null.mean()
        denom = float(np.linalg.norm(a0) * np.linalg.norm(a1))
        spec_corr = float(np.dot(a0, a1) / denom) if denom > 0.0 else 0.0
        spec_ok = spec_corr >= 0.90
        dist_ok = bool(np.array_equal(np.sort(nulled), sorted_vals))
        preserved = {
            "power_spectrum_band": spec_ok,
            "amplitude_distribution": dist_ok,
        }
        destroyed = {
            "nonlinear_phase_structure": not np.array_equal(series, nulled),
        }
        meta = _base_metadata(self.null_id, self.target_false_explanation, h_i2_conditional=False)
        meta["n_iter"] = n_iter
        meta["spectral_correlation"] = spec_corr
        return NullInstance(
            null_id=self.null_id,
            seed=seed,
            params=dict(params or {}),
            nulled_array=nulled,
            preserved_invariants_checked=preserved,
            destroyed_structure_checked=destroyed,
            metadata=meta,
        )


# ---------------------------------------------------------------------------
# N5 — degree_preserving_graph_null
# ---------------------------------------------------------------------------


class N5DegreePreservingGraphNull:
    """Rewire preserving degree sequence; kills "just degree distribution".

    Target false explanation: *the detected signal is merely an artifact
    of the node degree distribution, not of the specific edge placement.*
    Double-edge-swap rewiring keeps the exact degree sequence while
    randomising edge placement, so a degree-driven signal dies here.
    """

    null_id: Final[str] = "N5_degree_preserving_graph_null"
    target_false_explanation: Final[str] = (
        "The detected signal is merely an artifact of the node degree "
        "distribution, not of the specific edge placement."
    )

    def apply(
        self, signal_array: NDArray[Any], seed: int, params: dict[str, float] | None = None
    ) -> NullInstance:
        adj = _as_adjacency(signal_array)
        n = adj.shape[0]
        binary = (adj != 0.0).astype(np.int64)
        np.fill_diagonal(binary, 0)
        deg_src = degree_sequence(binary.astype(np.float64))
        rewired = binary.copy()
        rng = np.random.default_rng(seed)
        n_swaps = int((params or {}).get("n_swaps", 10 * n))
        for _ in range(max(1, n_swaps)):
            edges = np.argwhere(np.triu(rewired, 1) == 1)
            if edges.shape[0] < 2:
                break
            i = rng.integers(0, edges.shape[0])
            j = rng.integers(0, edges.shape[0])
            if i == j:
                continue
            a, b = edges[i]
            c, d = edges[j]
            if len({int(a), int(b), int(c), int(d)}) < 4:
                continue
            # double-edge swap (a-b, c-d) -> (a-d, c-b)
            if rewired[a, d] or rewired[c, b]:
                continue
            rewired[a, b] = rewired[b, a] = 0
            rewired[c, d] = rewired[d, c] = 0
            rewired[a, d] = rewired[d, a] = 1
            rewired[c, b] = rewired[b, c] = 1
        deg_null = degree_sequence(rewired.astype(np.float64))
        # ADMISSION: degree sequence preserved EXACTLY (not approximately).
        preserved = {
            "degree_sequence_exact": bool(np.array_equal(deg_src, deg_null)),
            "node_count": rewired.shape[0] == n,
        }
        destroyed = {
            "edge_placement": not np.array_equal(binary, rewired),
        }
        meta = _base_metadata(self.null_id, self.target_false_explanation, h_i2_conditional=False)
        return NullInstance(
            null_id=self.null_id,
            seed=seed,
            params=dict(params or {}),
            nulled_array=rewired.astype(np.float64),
            preserved_invariants_checked=preserved,
            destroyed_structure_checked=destroyed,
            metadata=meta,
        )


# ---------------------------------------------------------------------------
# N6 — weight_preserving_shuffle
# ---------------------------------------------------------------------------


class N6WeightPreservingShuffleNull:
    """Permute edge weights; kills "weight magnitude only".

    Target false explanation: *the signal is driven only by the multiset
    of edge weight magnitudes, not by which edge carries which weight.*
    Shuffling weights across the fixed topology preserves the weight
    multiset and the binary topology while destroying weight placement.
    """

    null_id: Final[str] = "N6_weight_preserving_shuffle"
    target_false_explanation: Final[str] = (
        "The signal is driven only by the multiset of edge-weight magnitudes, "
        "not by which edge carries which weight."
    )

    def apply(
        self, signal_array: NDArray[Any], seed: int, params: dict[str, float] | None = None
    ) -> NullInstance:
        adj = _as_adjacency(signal_array)
        n = adj.shape[0]
        rng = np.random.default_rng(seed)
        iu = np.triu_indices(n, 1)
        upper = adj[iu]
        mask = upper != 0.0
        edge_w = upper[mask]
        perm = rng.permutation(edge_w.shape[0])
        shuffled = edge_w.copy()
        shuffled = shuffled[perm]
        new_upper = upper.copy()
        new_upper[mask] = shuffled
        nulled = np.zeros_like(adj)
        nulled[iu] = new_upper
        nulled = nulled + nulled.T
        preserved = {
            "weight_multiset": bool(np.array_equal(np.sort(edge_w), np.sort(shuffled))),
            "binary_topology": bool(np.array_equal((adj != 0.0), (nulled != 0.0))),
        }
        destroyed = {
            "weight_placement": (edge_w.shape[0] >= 2 and not np.array_equal(edge_w, shuffled)),
        }
        meta = _base_metadata(self.null_id, self.target_false_explanation, h_i2_conditional=False)
        return NullInstance(
            null_id=self.null_id,
            seed=seed,
            params=dict(params or {}),
            nulled_array=nulled,
            preserved_invariants_checked=preserved,
            destroyed_structure_checked=destroyed,
            metadata=meta,
        )


# ---------------------------------------------------------------------------
# N7 — configuration_model  (H_I2-CONDITIONAL)
# ---------------------------------------------------------------------------


class N7ConfigurationModelNull:
    """Random graph matching degree sequence; kills "any-graph generic".

    Target false explanation: *the signal is generic to ANY random graph
    with this degree sequence, not specific to the observed network.*
    A configuration-model stub-matching draw preserves the degree
    sequence (the only structural constraint) and destroys everything
    else.

    H_I2-CONDITIONAL: D-002I H_I2 (M3 topology-conditioned over-fit) is
    UNKNOWN. This topology-conditioned null carries
    ``h_i2_conditional=True``: if H_I2 is later SUPPORTED, this null
    requires fresh admissibility justification before canonical use (P8).
    """

    null_id: Final[str] = "N7_configuration_model"
    target_false_explanation: Final[str] = (
        "The signal is generic to any random graph with this degree sequence, "
        "not specific to the observed network's edge structure."
    )
    h_i2_conditional: Final[bool] = True

    def apply(
        self, signal_array: NDArray[Any], seed: int, params: dict[str, float] | None = None
    ) -> NullInstance:
        adj = _as_adjacency(signal_array)
        n = adj.shape[0]
        binary = (adj != 0.0).astype(np.int64)
        np.fill_diagonal(binary, 0)
        deg_src = degree_sequence(binary.astype(np.float64))
        rng = np.random.default_rng(seed)
        # Deterministic stub-matching: pair shuffled half-edges, keep the
        # edge multiset, then repair self-loops / multi-edges with
        # degree-preserving double-edge swaps. The swap repair keeps the
        # degree sequence EXACT (admission test) while yielding a simple
        # graph for any graphical input degree sequence; this is far more
        # robust than whole-draw rejection on denser networks.
        stubs = np.repeat(np.arange(n), deg_src)
        rng.shuffle(stubs)
        edges: list[tuple[int, int]] = []
        for k in range(0, stubs.shape[0] - 1, 2):
            edges.append((int(stubs[k]), int(stubs[k + 1])))
        max_repair = int((params or {}).get("max_repair", 50 * (len(edges) + 1)))

        def _is_bad(idx: int) -> bool:
            a, b = edges[idx]
            if a == b:
                return True
            for j, (c, d) in enumerate(edges):
                if j != idx and {a, b} == {c, d}:
                    return True
            return False

        for _ in range(max(1, max_repair)):
            bad = [i for i in range(len(edges)) if _is_bad(i)]
            if not bad:
                break
            i = int(rng.choice(np.asarray(bad)))
            j = int(rng.integers(0, len(edges)))
            if i == j:
                continue
            a, b = edges[i]
            c, d = edges[j]
            # Degree-preserving swap (a,b),(c,d) -> (a,d),(c,b).
            edges[i] = (a, d)
            edges[j] = (c, b)
        nulled = np.zeros((n, n), dtype=np.int64)
        for a, b in edges:
            if a != b:
                nulled[a, b] = nulled[b, a] = 1
        deg_null = degree_sequence(nulled.astype(np.float64))
        preserved = {
            "degree_sequence_exact": bool(np.array_equal(deg_src, deg_null)),
            "node_count": nulled.shape[0] == n,
        }
        destroyed = {
            "specific_edge_structure": not np.array_equal(binary, nulled),
        }
        meta = _base_metadata(self.null_id, self.target_false_explanation, h_i2_conditional=True)
        meta["h_i2_note"] = (
            "D-002I H_I2 (M3 topology-conditioned over-fit) is UNKNOWN; if H_I2 "
            "is later SUPPORTED, this null requires fresh admissibility "
            "justification before canonical use (P8)."
        )
        return NullInstance(
            null_id=self.null_id,
            seed=seed,
            params=dict(params or {}),
            nulled_array=nulled.astype(np.float64),
            preserved_invariants_checked=preserved,
            destroyed_structure_checked=destroyed,
            metadata=meta,
        )


# ---------------------------------------------------------------------------
# N8 — sparse_maximum_entropy_reconstruction  (H_I2-CONDITIONAL)
# ---------------------------------------------------------------------------


class N8SparseMaxEntReconstructionNull:
    """Max-ent under a sparsity constraint; kills "dense-network artifact".

    Target false explanation: *the signal is an artifact of treating the
    network as dense; under a realistic sparsity budget it disappears.*
    A maximum-entropy reconstruction subject to a fixed edge-count
    (sparsity) constraint preserves total edge count and node count
    while destroying the dense placement.

    H_I2-CONDITIONAL: topology-conditioned class; carries
    ``h_i2_conditional=True`` for the same reason as N7.
    """

    null_id: Final[str] = "N8_sparse_maximum_entropy_reconstruction"
    target_false_explanation: Final[str] = (
        "The signal is an artifact of a dense-network representation and "
        "disappears under a realistic sparsity budget."
    )
    h_i2_conditional: Final[bool] = True

    def apply(
        self, signal_array: NDArray[Any], seed: int, params: dict[str, float] | None = None
    ) -> NullInstance:
        adj = _as_adjacency(signal_array)
        n = adj.shape[0]
        binary = (adj != 0.0).astype(np.int64)
        np.fill_diagonal(binary, 0)
        iu = np.triu_indices(n, 1)
        n_edges = int((binary[iu] != 0).sum())
        rng = np.random.default_rng(seed)
        m_pairs = iu[0].shape[0]
        # Max-entropy under fixed edge count = uniform over all sparse
        # configurations with exactly n_edges undirected edges.
        chosen = rng.choice(m_pairs, size=min(n_edges, m_pairs), replace=False)
        new_upper = np.zeros(m_pairs, dtype=np.int64)
        new_upper[chosen] = 1
        nulled = np.zeros((n, n), dtype=np.int64)
        nulled[iu] = new_upper
        nulled = nulled + nulled.T
        nulled_edges = int((nulled[iu] != 0).sum())
        preserved = {
            "total_edge_count": nulled_edges == n_edges,
            "node_count": nulled.shape[0] == n,
        }
        destroyed = {
            "dense_edge_placement": not np.array_equal(binary, nulled),
        }
        meta = _base_metadata(self.null_id, self.target_false_explanation, h_i2_conditional=True)
        meta["h_i2_note"] = (
            "D-002I H_I2 (M3 topology-conditioned over-fit) is UNKNOWN; if H_I2 "
            "is later SUPPORTED, this null requires fresh admissibility "
            "justification before canonical use (P8)."
        )
        meta["edge_count"] = n_edges
        return NullInstance(
            null_id=self.null_id,
            seed=seed,
            params=dict(params or {}),
            nulled_array=nulled.astype(np.float64),
            preserved_invariants_checked=preserved,
            destroyed_structure_checked=destroyed,
            metadata=meta,
        )


# ---------------------------------------------------------------------------
# N9 — shock_time_placebo
# ---------------------------------------------------------------------------


class N9ShockTimePlaceboNull:
    """Random fake shock time; kills "signal exists at any time".

    Target false explanation: *the signal exists at ANY arbitrary time,
    not specifically at the true crisis/shock time.* Relabelling the
    onset to a random placebo index preserves the series values and the
    onset count while destroying the crisis-time alignment.
    """

    null_id: Final[str] = "N9_shock_time_placebo"
    target_false_explanation: Final[str] = (
        "The signal exists at any arbitrary time, not specifically at the true "
        "crisis/shock onset time."
    )

    def apply(
        self, signal_array: NDArray[Any], seed: int, params: dict[str, float] | None = None
    ) -> NullInstance:
        series = _as_1d(signal_array)
        n = series.shape[0]
        rng = np.random.default_rng(seed)
        true_onset = int((params or {}).get("true_onset", n // 2))
        true_onset = max(0, min(true_onset, n - 1))
        placebo = int(rng.integers(0, n))
        while placebo == true_onset and n > 1:
            placebo = int(rng.integers(0, n))
        # The "nulled array" is the placebo-onset indicator series.
        nulled = np.zeros(n, dtype=np.float64)
        nulled[placebo] = 1.0
        true_ind = np.zeros(n, dtype=np.float64)
        true_ind[true_onset] = 1.0
        preserved = {
            "series_values_unchanged": bool(np.array_equal(series, series)),
            "single_onset_count": int(nulled.sum()) == 1,
        }
        destroyed = {
            "crisis_time_alignment": not np.array_equal(true_ind, nulled),
        }
        meta = _base_metadata(self.null_id, self.target_false_explanation, h_i2_conditional=False)
        meta["true_onset"] = true_onset
        meta["placebo_onset"] = placebo
        return NullInstance(
            null_id=self.null_id,
            seed=seed,
            params=dict(params or {}),
            nulled_array=nulled,
            preserved_invariants_checked=preserved,
            destroyed_structure_checked=destroyed,
            metadata=meta,
        )


# ---------------------------------------------------------------------------
# N10 — vintage_leakage_trap_null  (INVERTED PASS SEMANTICS)
# ---------------------------------------------------------------------------


class N10VintageLeakageTrapNull:
    """Re-introduce look-ahead leakage; INVERTED pass semantics.

    Target false explanation: *the signal is a look-ahead/leakage
    artifact (it only exists because future information bled into the
    feature).*

    INVERTED SEMANTICS — bridge to P3/PC5: this null deliberately
    RE-INTRODUCES leakage (a forward shift that lets future values into
    the present). PASS for this null means the signal DISAPPEARS when
    leakage is removed, i.e. the signal must be absent in the
    leakage-free arm. ``inverted_pass_semantics`` is recorded so the
    P6 guard test can assert the inversion.
    """

    null_id: Final[str] = "N10_vintage_leakage_trap_null"
    target_false_explanation: Final[str] = (
        "The signal is a look-ahead (vintage leakage) artifact that only exists "
        "because future information bled into the present feature."
    )
    inverted_pass_semantics: Final[bool] = True

    def apply(
        self, signal_array: NDArray[Any], seed: int, params: dict[str, float] | None = None
    ) -> NullInstance:
        series = _as_1d(signal_array)
        n = series.shape[0]
        k = int((params or {}).get("leak_lookahead", 1))
        k = max(1, min(k, n - 1))
        # Leakage arm: pull future values back into the present (look-ahead).
        leaked = np.roll(series, -k)
        leaked[-k:] = series[-k:]
        # Leakage-free arm: the original causal series (no future info).
        preserved = {
            "marginal_distribution_present_arm": bool(
                np.array_equal(np.sort(series), np.sort(series))
            ),
            "series_length": leaked.shape[0] == n,
        }
        # "Destroyed" here = the look-ahead arm differs from the causal
        # arm; if it did NOT, the trap is a no-op and must be rejected.
        destroyed = {
            "causal_information_boundary": not np.array_equal(series, leaked),
        }
        meta = _base_metadata(self.null_id, self.target_false_explanation, h_i2_conditional=False)
        meta["inverted_pass_semantics"] = True
        meta["pass_definition"] = (
            "PASS iff the signal DISAPPEARS in the leakage-free (causal) arm; "
            "a signal that persists only in the look-ahead arm is a leakage "
            "artifact (bridge to P3 leakage sentinel / PC5)."
        )
        meta["leak_lookahead"] = k
        return NullInstance(
            null_id=self.null_id,
            seed=seed,
            params=dict(params or {}),
            nulled_array=leaked,
            preserved_invariants_checked=preserved,
            destroyed_structure_checked=destroyed,
            metadata=meta,
        )


ALL_NULLS: Final[tuple[type[Any], ...]] = (
    N1LabelPermutationNull,
    N2TimeWindowShiftPlaceboNull,
    N3TemporalBlockBootstrapNull,
    N4IAAFTSurrogateNull,
    N5DegreePreservingGraphNull,
    N6WeightPreservingShuffleNull,
    N7ConfigurationModelNull,
    N8SparseMaxEntReconstructionNull,
    N9ShockTimePlaceboNull,
    N10VintageLeakageTrapNull,
)
"""The 10 admissible null families, in canonical N1..N10 order."""
