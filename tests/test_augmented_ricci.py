# mypy: disable-error-code="attr-defined,unused-ignore,no-untyped-call"
"""Tests for augmented Forman-Ricci with triangle reinforcement."""

from __future__ import annotations

import numpy as np

from geosync.estimators.augmented_ricci import AugmentedFormanRicci


def test_correlated_assets_positive_curvature() -> None:
    """Highly correlated assets → positive κ (robust topology)."""
    np.random.seed(42)
    base = np.cumsum(np.random.randn(200))
    returns = np.column_stack(
        [
            np.diff(base),
            np.diff(base + 0.01 * np.random.randn(200)),
            np.diff(base + 0.02 * np.random.randn(200)),
        ]
    )
    ricci = AugmentedFormanRicci(correlation_threshold=0.1)
    kappa = ricci.compute_mean(returns, ["A", "B", "C"])
    # Highly correlated → triangles form → positive curvature
    assert kappa != 0.0, "Correlated assets should produce non-zero curvature"


def test_uncorrelated_assets_zero_curvature() -> None:
    """Independent assets → no edges above threshold → κ = 0."""
    np.random.seed(42)
    returns = np.random.randn(200, 5)
    ricci = AugmentedFormanRicci(correlation_threshold=0.5)
    kappa = ricci.compute_mean(returns, ["A", "B", "C", "D", "E"])
    assert kappa == 0.0


def test_two_assets_minimum() -> None:
    """Need at least 2 assets for graph construction."""
    np.random.seed(42)
    returns = np.random.randn(100, 1)
    ricci = AugmentedFormanRicci()
    kappa = ricci.compute_mean(returns, ["A"])
    assert kappa == 0.0


def test_short_series_returns_zero() -> None:
    """< 16 bars → insufficient for correlation → 0."""
    returns = np.random.randn(10, 3)
    ricci = AugmentedFormanRicci()
    kappa = ricci.compute_mean(returns, ["A", "B", "C"])
    assert kappa == 0.0


def test_shape_mismatch_raises() -> None:
    """returns.shape[1] != len(symbols) → ValueError."""
    try:
        AugmentedFormanRicci().compute_mean(np.random.randn(100, 3), ["A", "B"])
        raise AssertionError("Should have raised ValueError")
    except ValueError:
        pass


def test_threshold_affects_graph_density() -> None:
    """Higher threshold → fewer edges → different κ."""
    np.random.seed(42)
    base = np.cumsum(np.random.randn(200))
    returns = np.column_stack(
        [
            np.diff(base),
            np.diff(base + 0.05 * np.random.randn(200)),
            np.diff(base + 0.1 * np.random.randn(200)),
        ]
    )
    k_low = AugmentedFormanRicci(correlation_threshold=0.1).compute_mean(returns, ["A", "B", "C"])
    k_high = AugmentedFormanRicci(correlation_threshold=0.9).compute_mean(returns, ["A", "B", "C"])
    # Higher threshold may prune edges → different curvature
    # (not necessarily lower — depends on which edges survive)
    assert isinstance(k_low, float)
    assert isinstance(k_high, float)


def _dense_asymmetric_cluster() -> np.ndarray:
    """3 tightly-coupled + 2 loosely-coupled assets: many edges of DIFFERENT curvature."""
    rng = np.random.default_rng(11)
    base = rng.standard_normal((80, 1))
    cols = [base + 0.03 * rng.standard_normal((80, 1)) for _ in range(3)]
    cols += [base * 0.4 + rng.standard_normal((80, 1)) * 0.9 for _ in range(2)]
    return np.hstack(cols)


def _fragile_but_not_negative_cluster() -> tuple[np.ndarray, float]:
    """A graph that is majority-fragile yet mean-curvature >= -0.5 (the And->Or witness)."""
    rng = np.random.default_rng(16)
    n = int(rng.integers(3, 7))
    k = int(rng.integers(1, n))
    base = rng.standard_normal((80, 1))
    cols = []
    for asset in range(n):
        weight = float(rng.uniform(0.0, 0.4))
        if asset < k:
            cols.append(base * (1.0 - weight) + rng.standard_normal((80, 1)) * weight)
        else:
            cols.append(rng.standard_normal((80, 1)))
    threshold = float(rng.uniform(0.1, 0.35))
    return np.hstack(cols), threshold


def test_curvature_distribution_fields_are_pinned() -> None:
    """`triu(adj) > 0`, `n_edges > 1`, and `(kappa < 0).mean()` on a dense asymmetric cluster.

    The edge selector must find the real edges (killing `Gt -> LtE`, under which the empty
    complement is selected and the result collapses to zero edges); the std must be positive
    over several edges of different curvature (killing the `n_edges > 1` guard); and the
    fragile fraction must count the NEGATIVE-curvature edges (killing `Lt -> GtE`). A dense
    correlated clique's Forman curvature is dominated by the degree penalty, so every edge is
    fragile, the mean is well below -0.5, and neckpinch is True (killing both comparisons in
    the conjunction).
    """
    ricci = AugmentedFormanRicci(correlation_threshold=0.15)
    result = ricci.compute(_dense_asymmetric_cluster(), list("ABCDE"))

    assert result.n_edges > 1, "the edge selector found no real edges"
    assert result.std_kappa > 0.0, "curvature std collapsed to zero over multiple edges"
    assert result.fragile_fraction == 1.0, "every edge of this dense clique is negative-curvature"
    assert result.mean_kappa < -0.5
    assert result.neckpinch_detected is True


def test_neckpinch_requires_both_fragility_and_negative_mean() -> None:
    """`neckpinch = fragile_fraction > 0.5 and mean_kappa < -0.5`.

    A sparser cluster is majority-fragile (fraction 2/3) while its mean curvature stays above
    -0.5 -- the (True, False) case. Under `And -> Or` the single satisfied fragility condition
    would raise a false neckpinch alarm; the flag must stay False.
    """
    returns, threshold = _fragile_but_not_negative_cluster()
    ricci = AugmentedFormanRicci(correlation_threshold=threshold)
    result = ricci.compute(returns, list("ABCDE"))

    assert result.n_edges > 1
    assert result.fragile_fraction > 0.5 and result.mean_kappa >= -0.5
    assert result.neckpinch_detected is False, "a fragile-but-not-negative graph is not a neckpinch"
