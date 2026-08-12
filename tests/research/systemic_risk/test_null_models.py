# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the six required null-baseline generators (§ 8 of the
official validation protocol).

Each baseline must:
* preserve a documented invariant of the empirical input;
* be deterministic under a fixed seed;
* leave the *to-be-tested* property destroyed.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from research.systemic_risk.event_ledger import (
    BankingCrisisEvent,
    BankingCrisisLedger,
)
from research.systemic_risk.null_models import (
    degree_preserving_randomization,
    linear_correlation_surrogate,
    permuted_crisis_dates,
    random_exposure_weights,
    shuffled_time_labels,
    static_topology_baseline,
)
from research.systemic_risk.topology import (
    InterbankTopology,
    barabasi_albert_null,
    from_exposure_matrix,
)


def _empirical_topo(seed: int) -> InterbankTopology:
    rng = np.random.default_rng(seed)
    n = 30
    e = rng.exponential(1.0, size=(n, n)).astype(np.float64)
    e *= rng.random((n, n)) > 0.5
    np.fill_diagonal(e, 0.0)
    return from_exposure_matrix(e, tuple(f"b{i}" for i in range(n)))


class TestDegreePreservingRandomization:
    def test_preserves_in_and_out_degree(self) -> None:
        topo = _empirical_topo(seed=0)
        out = degree_preserving_randomization(topo, seed=42)
        assert out.topology is not None
        np.testing.assert_array_equal(out.topology.in_degree, topo.in_degree)
        np.testing.assert_array_equal(out.topology.out_degree, topo.out_degree)

    def test_seed_determinism(self) -> None:
        topo = _empirical_topo(seed=0)
        a = degree_preserving_randomization(topo, seed=11)
        b = degree_preserving_randomization(topo, seed=11)
        assert a.topology is not None and b.topology is not None
        np.testing.assert_array_equal(a.topology.adjacency, b.topology.adjacency)

    def test_destroys_specific_edges(self) -> None:
        # With enough swaps the rewired graph differs from the input
        # while preserving the marginals.
        topo = _empirical_topo(seed=0)
        out = degree_preserving_randomization(topo, seed=7, n_swaps=200)
        assert out.topology is not None
        diff = float((out.topology.adjacency != topo.adjacency).mean())
        assert diff > 0.05, (
            f"degree-preserving rewire too conservative: "
            f"{diff:.3f} of entries differ; expected > 0.05 at n_swaps=200"
        )


class TestShuffledTimeLabels:
    def test_preserves_marginal_distribution(self) -> None:
        rng = np.random.default_rng(0)
        score = rng.standard_normal(500)
        out = shuffled_time_labels(score, seed=1)
        assert out.score is not None
        # Marginal moments preserved (it's a permutation).
        np.testing.assert_allclose(out.score.mean(), score.mean(), atol=1e-12)
        np.testing.assert_allclose(out.score.std(), score.std(), atol=1e-12)

    def test_destroys_temporal_ordering(self) -> None:
        # A strongly autocorrelated series loses its lag-1 autocorr.
        rng = np.random.default_rng(0)
        n = 1000
        eps = rng.standard_normal(n)
        ar = np.zeros(n, dtype=np.float64)
        for t in range(1, n):
            ar[t] = 0.95 * ar[t - 1] + eps[t]
        out = shuffled_time_labels(ar, seed=11)
        assert out.score is not None
        rho_before = float(np.corrcoef(ar[:-1], ar[1:])[0, 1])
        rho_after = float(np.corrcoef(out.score[:-1], out.score[1:])[0, 1])
        assert abs(rho_after) < abs(rho_before) - 0.5, (
            f"shuffle did not destroy lag-1 autocorr: "
            f"|ρ| {abs(rho_before):.3f} → {abs(rho_after):.3f} on AR(0.95) n=1000"
        )

    def test_rejects_non_1d(self) -> None:
        with pytest.raises(ValueError, match="1-D"):
            shuffled_time_labels(np.zeros((10, 3)), seed=0)


class TestRandomExposureWeights:
    def test_preserves_binary_support(self) -> None:
        topo = _empirical_topo(seed=0)
        out = random_exposure_weights(topo, seed=3)
        assert out.topology is not None
        np.testing.assert_array_equal(out.topology.adjacency, topo.adjacency)

    def test_no_weights_yields_zero_weights(self) -> None:
        topo = barabasi_albert_null(n_nodes=20, m=2, seed=0)
        out = random_exposure_weights(topo, seed=0)
        assert out.topology is not None
        # BA null has no empirical weights → surrogate has weights=None.
        assert out.topology.weights is None

    def test_seed_determinism(self) -> None:
        topo = _empirical_topo(seed=0)
        a = random_exposure_weights(topo, seed=99)
        b = random_exposure_weights(topo, seed=99)
        assert a.topology is not None and b.topology is not None
        if a.topology.weights is not None:
            assert b.topology.weights is not None
            np.testing.assert_array_equal(a.topology.weights, b.topology.weights)


class TestStaticTopologyBaseline:
    def test_union_preserves_every_edge(self) -> None:
        snapshots = tuple(_empirical_topo(seed=s) for s in (0, 1, 2))
        out = static_topology_baseline(snapshots, seed=0)
        assert out.topology is not None
        # Every edge that ever existed survives.
        for snap in snapshots:
            assert np.all(out.topology.adjacency[snap.adjacency == 1] == 1)

    def test_rejects_empty(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            static_topology_baseline(tuple(), seed=0)

    def test_rejects_size_mismatch(self) -> None:
        a = _empirical_topo(seed=0)
        b = barabasi_albert_null(n_nodes=10, m=2, seed=0)  # different N
        with pytest.raises(ValueError, match="node count"):
            static_topology_baseline((a, b), seed=0)


class TestLinearCorrelationSurrogate:
    def test_in_unit_interval(self) -> None:
        rng = np.random.default_rng(0)
        s = rng.standard_normal((200, 8))
        out = linear_correlation_surrogate(s, seed=0)
        assert out.score is not None
        finite = out.score[np.isfinite(out.score)]
        assert finite.size > 0
        # Mean off-diagonal Pearson is bounded by ±1.
        assert np.all(finite >= -1.0 - 1e-9) and np.all(finite <= 1.0 + 1e-9)

    def test_short_input_rejected(self) -> None:
        with pytest.raises(ValueError, match="2 time samples"):
            linear_correlation_surrogate(np.zeros((1, 4)), seed=0)


class TestPermutedCrisisDates:
    def test_preserves_event_count_and_durations(self) -> None:
        ledger = BankingCrisisLedger(
            events=(
                BankingCrisisEvent(
                    country="USA",
                    start=date(2008, 9, 15),
                    end=date(2009, 6, 30),
                    source="LV2018",
                    label="GFC_USA",
                ),
                BankingCrisisEvent(
                    country="GRC",
                    start=date(2010, 5, 1),
                    end=date(2012, 12, 31),
                    source="LV2018",
                    label="EZ_GRC",
                ),
            )
        )
        out = permuted_crisis_dates(
            ledger, earliest=date(2005, 1, 1), latest=date(2025, 12, 31), seed=11
        )
        assert out.ledger is not None
        assert len(out.ledger.events) == 2
        for orig, permuted in zip(ledger.events, out.ledger.events):
            assert (permuted.end - permuted.start) == (orig.end - orig.start)

    def test_seed_determinism(self) -> None:
        ledger = BankingCrisisLedger(
            events=(
                BankingCrisisEvent(
                    country="USA",
                    start=date(2008, 9, 15),
                    end=date(2009, 6, 30),
                    source="LV2018",
                    label="GFC_USA",
                ),
            )
        )
        a = permuted_crisis_dates(
            ledger, earliest=date(2005, 1, 1), latest=date(2025, 12, 31), seed=42
        )
        b = permuted_crisis_dates(
            ledger, earliest=date(2005, 1, 1), latest=date(2025, 12, 31), seed=42
        )
        assert a.ledger is not None and b.ledger is not None
        assert a.ledger.events[0].start == b.ledger.events[0].start

    def test_invalid_window_rejected(self) -> None:
        with pytest.raises(ValueError, match="latest"):
            permuted_crisis_dates(
                BankingCrisisLedger(events=tuple()),
                earliest=date(2010, 1, 1),
                latest=date(2010, 1, 1),
                seed=0,
            )
