import math

import numpy as np
import pytest

from tradepulse.protocol import (
    DivConvSignal,
    DivConvSnapshot,
    aggregate_signals,
    compute_divergence_functional,
    compute_kappa,
    compute_price_gradient,
    compute_theta,
    compute_threshold_tau_c,
    compute_threshold_tau_d,
    compute_time_warp_invariant_metric,
)


def test_compute_price_gradient_time_scaling_invariance():
    rng = np.random.default_rng(7)
    for length in range(2, 10):
        prices = rng.normal(size=length)
        times = np.linspace(0.1, 2.1, num=length)
        base = compute_price_gradient(prices)
        scaled = compute_price_gradient(prices, times=times)
        assert np.allclose(base, scaled * np.gradient(times), atol=1e-6)


def test_kappa_scale_invariance():
    rng = np.random.default_rng(19)
    for dimension in range(2, 7):
        for _ in range(25):
            vec = rng.normal(size=dimension)
            other = rng.normal(size=dimension)
            if np.linalg.norm(vec) < 1e-6 or np.linalg.norm(other) < 1e-6:
                continue
            base = compute_kappa(vec, other)
            scaled = compute_kappa(3.7 * vec, 0.5 * other)
            assert math.isclose(base, scaled, rel_tol=1e-9, abs_tol=1e-9)


def test_metric_is_positive_semidefinite():
    rng = np.random.default_rng(42)
    for rank in range(1, 6):
        basis = [rng.normal(size=rank) for _ in range(rank)]
        metric = compute_time_warp_invariant_metric(basis)
        eigvals = np.linalg.eigvalsh(metric)
        assert np.all(eigvals >= -1e-12)


def test_divergence_metric_matches_identity():
    price = np.array([1.0, 2.0, 3.0])
    flow = np.array([0.5, 1.5, 3.5])
    metric = np.eye(3)
    expected = np.dot(price - flow, price - flow)
    assert math.isclose(
        compute_divergence_functional(price, flow, metric=metric),
        expected,
        rel_tol=1e-12,
    )


def test_threshold_monotonicity():
    divergence = np.linspace(0.0, 10.0, num=50)
    tau_d = compute_threshold_tau_d(divergence, alpha=0.9)
    tau_c = compute_threshold_tau_c(divergence, beta=0.1)
    assert tau_c <= tau_d


def test_portfolio_aggregation_is_weighted_average():
    snapshot_a = DivConvSnapshot(
        price_gradient=np.array([1.0, 0.0]),
        flow_gradient=np.array([0.0, 1.0]),
        theta=compute_theta([1.0, 0.0], [0.0, 1.0]),
        kappa=compute_kappa([1.0, 0.0], [0.0, 1.0]),
        divergence=2.0,
    )
    snapshot_b = DivConvSnapshot(
        price_gradient=np.array([0.0, 1.0]),
        flow_gradient=np.array([1.0, 0.0]),
        theta=compute_theta([0.0, 1.0], [1.0, 0.0]),
        kappa=compute_kappa([0.0, 1.0], [1.0, 0.0]),
        divergence=1.0,
    )

    signals = [
        DivConvSignal(asset_id="A", snapshot=snapshot_a, risk_weight=0.7, exposure=1.0),
        DivConvSignal(asset_id="B", snapshot=snapshot_b, risk_weight=0.3, exposure=2.0),
    ]

    aggregated = aggregate_signals(signals)
    assert np.allclose(aggregated.price_gradient, np.array([0.7, 0.3]))
    assert np.allclose(aggregated.flow_gradient, np.array([0.3, 0.7]))
    assert math.isfinite(aggregated.theta)
    assert -1.0 <= aggregated.kappa <= 1.0
    assert math.isfinite(aggregated.divergence)


def test_portfolio_aggregation_preserves_divergence_for_short_weights():
    long_snapshot = DivConvSnapshot(
        price_gradient=np.array([2.0, 0.0]),
        flow_gradient=np.array([0.5, 1.5]),
        theta=compute_theta([2.0, 0.0], [0.5, 1.5]),
        kappa=compute_kappa([2.0, 0.0], [0.5, 1.5]),
        divergence=3.0,
    )
    short_snapshot = DivConvSnapshot(
        price_gradient=np.array([0.5, 1.5]),
        flow_gradient=np.array([1.5, 0.5]),
        theta=compute_theta([0.5, 1.5], [1.5, 0.5]),
        kappa=compute_kappa([0.5, 1.5], [1.5, 0.5]),
        divergence=1.2,
    )

    signals = [
        DivConvSignal(
            asset_id="LONG", snapshot=long_snapshot, risk_weight=0.6, exposure=1.0
        ),
        DivConvSignal(
            asset_id="SHORT", snapshot=short_snapshot, risk_weight=-0.4, exposure=1.0
        ),
    ]

    aggregated = aggregate_signals(signals)
    total_abs_weight = sum(abs(signal.risk_weight) for signal in signals)
    expected_divergence = sum(
        abs(signal.risk_weight) / total_abs_weight * signal.snapshot.divergence
        for signal in signals
    )
    assert math.isclose(aggregated.divergence, expected_divergence)
    assert aggregated.divergence >= 0.0


def test_compute_price_gradient_requires_strictly_increasing_times():
    prices = np.array([1.0, 2.0, 3.0])
    times = np.array([0.0, 0.0, 1.0])
    with pytest.raises(ValueError, match="strictly increasing"):
        compute_price_gradient(prices, times=times)


def test_compute_price_gradient_requires_matching_times_shape():
    prices = np.array([1.0, 2.0, 3.0])
    times = np.array([0.0, 0.5])
    with pytest.raises(ValueError, match="same shape"):
        compute_price_gradient(prices, times=times)


def test_compute_theta_rejects_zero_norm_vectors():
    with pytest.raises(ValueError, match="near-zero"):
        compute_theta([0.0, 0.0, 0.0], [1.0, 0.0, 0.0])


def test_compute_kappa_requires_matching_shapes():
    with pytest.raises(ValueError, match="same dimensionality"):
        compute_kappa([1.0, 0.0], [1.0, 0.0, 0.0])


def test_time_warp_metric_weight_alignment_validation():
    basis = [np.array([1.0, 0.0]), np.array([0.0, 1.0])]
    weights = [0.5]
    with pytest.raises(ValueError, match="must align"):
        compute_time_warp_invariant_metric(basis, weights=weights)


def test_time_warp_metric_rejects_non_vector_inputs():
    basis = [np.ones((2, 2))]
    with pytest.raises(ValueError, match="one-dimensional"):
        compute_time_warp_invariant_metric(basis)


def test_divergence_functional_validates_metric_shape():
    price = np.array([1.0, 2.0])
    flow = np.array([0.5, 1.5])
    with pytest.raises(ValueError, match="square"):
        compute_divergence_functional(price, flow, metric=np.ones((2, 3)))
    with pytest.raises(ValueError, match="dimensionality"):
        compute_divergence_functional(price, flow, metric=np.eye(3))


def test_threshold_helpers_validate_parameters():
    divergence = np.array([0.1, 0.2, 0.3])
    with pytest.raises(ValueError, match="alpha"):
        compute_threshold_tau_d(divergence, alpha=1.5)
    with pytest.raises(ValueError, match="beta"):
        compute_threshold_tau_c(divergence, beta=0.0)
    with pytest.raises(ValueError, match="must not be empty"):
        compute_threshold_tau_d([], alpha=0.5)


def test_aggregate_signals_requires_non_empty_iterable():
    with pytest.raises(ValueError, match="at least one"):
        aggregate_signals([])


def test_aggregate_signals_rejects_zero_normalised_weights():
    snapshot = DivConvSnapshot(
        price_gradient=np.array([1.0, 0.0]),
        flow_gradient=np.array([0.0, 1.0]),
        theta=compute_theta([1.0, 0.0], [0.0, 1.0]),
        kappa=compute_kappa([1.0, 0.0], [0.0, 1.0]),
        divergence=1.0,
    )
    signals = [
        DivConvSignal(asset_id="A", snapshot=snapshot, risk_weight=0.0, exposure=1.0),
        DivConvSignal(asset_id="B", snapshot=snapshot, risk_weight=0.0, exposure=1.0),
    ]
    with pytest.raises(ValueError, match="must not all be zero"):
        aggregate_signals(signals)


def test_aggregate_signals_accepts_pre_normalised_weights():
    snapshot_a = DivConvSnapshot(
        price_gradient=np.array([1.0, 0.0]),
        flow_gradient=np.array([0.0, 1.0]),
        theta=compute_theta([1.0, 0.0], [0.0, 1.0]),
        kappa=compute_kappa([1.0, 0.0], [0.0, 1.0]),
        divergence=1.0,
    )
    snapshot_b = DivConvSnapshot(
        price_gradient=np.array([0.0, 1.0]),
        flow_gradient=np.array([1.0, 0.0]),
        theta=compute_theta([0.0, 1.0], [1.0, 0.0]),
        kappa=compute_kappa([0.0, 1.0], [1.0, 0.0]),
        divergence=2.0,
    )
    signals = [
        DivConvSignal(asset_id="A", snapshot=snapshot_a, risk_weight=0.6, exposure=1.0),
        DivConvSignal(asset_id="B", snapshot=snapshot_b, risk_weight=0.4, exposure=1.0),
    ]
    aggregated = aggregate_signals(signals, normalise_weights=False)
    assert np.allclose(aggregated.price_gradient, np.array([0.6, 0.4]))
    assert np.allclose(aggregated.flow_gradient, np.array([0.4, 0.6]))
    assert math.isclose(aggregated.divergence, 1.4)
