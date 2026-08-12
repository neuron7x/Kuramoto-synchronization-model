# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Invariant tests for :mod:`research.systemic_risk.topology` (v2 — directed)."""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from research.systemic_risk.topology import (
    InterbankTopology,
    barabasi_albert_null,
    from_exposure_matrix,
)


class TestInterbankTopologyInvariants:
    def test_inv_top1_directed_adjacency_accepted(self) -> None:
        # v2: asymmetric adjacency is ALLOWED — represents directed exposure.
        a = np.array([[0, 1, 0], [0, 0, 1], [1, 0, 0]], dtype=np.int8)
        topo = InterbankTopology(adjacency=a, node_labels=("a", "b", "c"), source_label="t")
        assert not topo.is_symmetric
        assert topo.asymmetry_fraction > 0.0

    def test_inv_top1_nonbinary_rejected(self) -> None:
        a = np.array([[0, 2], [2, 0]], dtype=np.int8)
        with pytest.raises(ValueError, match="INV-TOP1"):
            InterbankTopology(adjacency=a, node_labels=("a", "b"), source_label="t")

    def test_inv_top1_diagonal_must_be_zero(self) -> None:
        a = np.array([[1, 1], [1, 1]], dtype=np.int8)
        with pytest.raises(ValueError, match="INV-TOP1"):
            InterbankTopology(adjacency=a, node_labels=("a", "b"), source_label="t")

    def test_inv_top3_label_length_mismatch_rejected(self) -> None:
        a = np.zeros((3, 3), dtype=np.int8)
        with pytest.raises(ValueError, match="INV-TOP3"):
            InterbankTopology(adjacency=a, node_labels=("a", "b"), source_label="t")

    def test_inv_top2_negative_weights_rejected(self) -> None:
        a = np.array([[0, 1], [1, 0]], dtype=np.int8)
        w = np.array([[0.0, -1.0], [-1.0, 0.0]], dtype=np.float64)
        with pytest.raises(ValueError, match="INV-TOP2"):
            InterbankTopology(adjacency=a, weights=w, node_labels=("a", "b"), source_label="t")

    def test_arrays_are_immutable_after_construction(self) -> None:
        a = np.array([[0, 1], [1, 0]], dtype=np.int8)
        topo = InterbankTopology(adjacency=a, node_labels=("a", "b"), source_label="t")
        with pytest.raises(ValueError):
            topo.adjacency[0, 1] = 0

    def test_in_out_degree(self) -> None:
        # a→b, b→c, c→a (directed cycle)
        a = np.array([[0, 1, 0], [0, 0, 1], [1, 0, 0]], dtype=np.int8)
        topo = InterbankTopology(adjacency=a, node_labels=("a", "b", "c"), source_label="t")
        assert list(topo.in_degree) == [1, 1, 1]
        assert list(topo.out_degree) == [1, 1, 1]
        assert list(topo.degree) == [2, 2, 2]

    def test_snapshot_date_optional(self) -> None:
        a = np.zeros((2, 2), dtype=np.int8)
        snap = date(2011, 6, 30)
        topo = InterbankTopology(
            adjacency=a, node_labels=("a", "b"), source_label="t", snapshot_date=snap
        )
        assert topo.snapshot_date == snap


class TestFromExposureMatrix:
    def test_directed_default_preserves_asymmetry(self) -> None:
        # Asymmetric exposure: a → b strong, b → a weak.
        e = np.array([[0.0, 5.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 0.0]], dtype=np.float64)
        topo = from_exposure_matrix(e, node_labels=("a", "b", "c"), threshold=2.0)
        # a → b passes threshold, b → a does NOT (1.0 <= 2.0).
        assert topo.adjacency[0, 1] == 1, "INV-TOP1d: directed edge a→b should be present"
        assert topo.adjacency[1, 0] == 0, (
            "INV-TOP1d: directed edge b→a below threshold should be absent; "
            "v2 must NOT auto-symmetrise"
        )

    def test_symmetric_mode_averages(self) -> None:
        e = np.array([[0.0, 1.0, 0.0], [3.0, 0.0, 0.0], [0.0, 0.0, 0.0]], dtype=np.float64)
        topo = from_exposure_matrix(e, node_labels=("a", "b", "c"), directed=False)
        # (1+3)/2 = 2 → both edges present.
        assert topo.adjacency[0, 1] == 1
        assert topo.adjacency[1, 0] == 1
        assert topo.is_symmetric

    def test_threshold_excludes_small_exposures(self) -> None:
        e = np.array([[0.0, 0.5], [0.5, 0.0]], dtype=np.float64)
        topo = from_exposure_matrix(e, node_labels=("a", "b"), threshold=1.0)
        assert topo.adjacency[0, 1] == 0

    def test_negative_exposure_rejected(self) -> None:
        e = np.array([[0.0, -1.0], [-1.0, 0.0]], dtype=np.float64)
        with pytest.raises(ValueError):
            from_exposure_matrix(e, node_labels=("a", "b"))

    def test_nan_exposure_rejected(self) -> None:
        e = np.array([[0.0, np.nan], [0.0, 0.0]], dtype=np.float64)
        with pytest.raises(ValueError, match="finite"):
            from_exposure_matrix(e, node_labels=("a", "b"))

    def test_snapshot_date_propagates(self) -> None:
        e = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=np.float64)
        snap = date(2011, 6, 30)
        topo = from_exposure_matrix(e, node_labels=("a", "b"), snapshot_date=snap)
        assert topo.snapshot_date == snap

    def test_single_node_graph_accepted(self) -> None:
        e = np.zeros((1, 1), dtype=np.float64)
        topo = from_exposure_matrix(e, ("solo",))
        assert topo.n_nodes == 1
        assert topo.adjacency.sum() == 0

    def test_all_zero_matrix_accepted_as_empty_graph(self) -> None:
        e = np.zeros((5, 5), dtype=np.float64)
        topo = from_exposure_matrix(e, tuple(f"b{i}" for i in range(5)))
        assert topo.adjacency.sum() == 0
        assert np.all(topo.in_degree == 0)
        assert np.all(topo.out_degree == 0)

    def test_asymmetry_invariant_on_directed_data(self) -> None:
        # v2 protocol's asymmetry invariant: empirical e-MID, BIS, ECB
        # interbank exposures are documented at ≥ 60% asymmetry
        # (Bardoscia et al. 2021 NRP, fig. 2). The test uses a
        # deterministic upper-triangular construction so the bound
        # is hit by structure, not by statistical luck.
        n = 20
        e = np.zeros((n, n), dtype=np.float64)
        for i in range(n):
            for j in range(i + 1, n):
                e[i, j] = float((i + 1) * (j + 1))
        topo = from_exposure_matrix(e, node_labels=tuple(f"b{i}" for i in range(n)))
        assert topo.asymmetry_fraction > 0.5, (
            f"asymmetry invariant VIOLATED: fraction={topo.asymmetry_fraction:.3f} "
            f"<= 0.5 on upper-triangular directed input. At N={n} (deterministic)"
        )


class TestBarabasiAlbertNull:
    @pytest.mark.parametrize("m", [2, 3, 4])
    def test_topology_invariants_hold(self, m: int) -> None:
        topo = barabasi_albert_null(n_nodes=50, m=m, seed=42)
        assert topo.adjacency.shape == (50, 50)
        assert np.array_equal(topo.adjacency, topo.adjacency.T)
        assert np.all(np.diag(topo.adjacency) == 0)
        assert np.all((topo.adjacency == 0) | (topo.adjacency == 1))

    def test_seed_determinism(self) -> None:
        a = barabasi_albert_null(n_nodes=30, m=3, seed=7)
        b = barabasi_albert_null(n_nodes=30, m=3, seed=7)
        assert np.array_equal(a.adjacency, b.adjacency)

    def test_different_seeds_differ(self) -> None:
        a = barabasi_albert_null(n_nodes=50, m=3, seed=1)
        b = barabasi_albert_null(n_nodes=50, m=3, seed=2)
        assert not np.array_equal(a.adjacency, b.adjacency)

    def test_mean_out_degree_close_to_2m(self) -> None:
        # Statistical: ensemble of 50 BA graphs, mean OUT-degree → 2m (the
        # symmetric BA mean degree per Albert-Barabási 2002). The total
        # `degree` property in v2 sums in+out, so a symmetric graph has
        # mean(degree) = 2*mean(out_degree) ≈ 4m — guarded separately.
        m = 3
        n = 200
        means = [
            float(barabasi_albert_null(n_nodes=n, m=m, seed=seed).out_degree.mean())
            for seed in range(50)
        ]
        ensemble_mean = float(np.mean(means))
        assert abs(ensemble_mean - 2 * m) < 0.5, (
            f"BA mean-out-degree drift: ensemble_mean={ensemble_mean:.3f}, "
            f"expected 2m={2 * m} ± 0.5 at N={n}, m={m}, n_seeds=50"
        )

    def test_invalid_m_rejected(self) -> None:
        with pytest.raises(ValueError):
            barabasi_albert_null(n_nodes=10, m=0, seed=0)
        with pytest.raises(ValueError):
            barabasi_albert_null(n_nodes=3, m=5, seed=0)
