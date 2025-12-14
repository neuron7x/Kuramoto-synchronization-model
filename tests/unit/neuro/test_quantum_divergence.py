"""Tests for the quantum-active divergence computation stack."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.neuro.advanced import (
    DivergenceConfig,
    compute_divergence_convergence_phi,
    granger_causality,
    quantum_relative_entropy,
    to_density_matrix,
)


def test_quantum_relative_entropy_positive_and_zero_at_identity() -> None:
    vector_a = np.array([1.0, 0.0])
    vector_b = np.array([0.7, 0.3])

    rho_a = to_density_matrix(vector_a)
    rho_b = to_density_matrix(vector_b)

    assert quantum_relative_entropy(rho_a, rho_a) == pytest.approx(0.0, abs=1e-9)
    assert quantum_relative_entropy(rho_a, rho_b) > 0.0


def test_compute_divergence_quantum_mode_updates_phi() -> None:
    index = pd.RangeIndex(10)
    price = pd.Series(np.linspace(100.0, 101.8, len(index)), index=index)
    feature = pd.Series(np.linspace(0.2, 0.5, len(index)), index=index, name="momentum")
    features = pd.DataFrame(
        {"momentum": feature, "volume": np.linspace(1.0, 2.0, len(index))}
    )

    config = DivergenceConfig(
        divergence_mode="quantum", learning_rate=0.2, entropy_weight=0.1
    )
    output = compute_divergence_convergence_phi(price, features, config=config)

    assert not output.frame.empty
    assert (output.frame["phi"].diff().abs() > 0).any()
    assert output.frame["divergence"].dropna().ge(0.0).all()


def test_granger_causality_detects_linear_dependence() -> None:
    base = np.linspace(0.0, 1.0, 200)
    noise = np.random.default_rng(7).normal(0.0, 0.05, size=200)
    driver = base + noise
    response = 0.5 * np.roll(driver, 1) + np.random.default_rng(11).normal(
        0.0, 0.01, size=200
    )

    result = granger_causality(response, driver, max_lag=2, p_threshold=0.05)

    assert result.causes
    assert 0.0 <= result.p_value <= 0.05


def test_normalisation_reduces_scale_bias() -> None:
    rng = np.random.default_rng(21)
    index = pd.RangeIndex(250)

    price = pd.Series(
        np.linspace(100.0, 104.0, len(index)) + rng.normal(0.0, 0.05, len(index)),
        index=index,
    )
    features = pd.DataFrame(
        {
            "feature": price * 120 + rng.normal(0.0, 5.0, len(index)),
            "volume": price * 800 + rng.normal(0.0, 20.0, len(index)),
        },
        index=index,
    )

    baseline = compute_divergence_convergence_phi(
        price,
        features,
        config=DivergenceConfig(normalisation="none", causal_p_threshold=None),
    )
    normalised = compute_divergence_convergence_phi(
        price,
        features,
        config=DivergenceConfig(normalisation="robust", causal_p_threshold=None),
    )

    assert normalised.convergence.mean() > baseline.convergence.mean()
    assert normalised.divergence.mean() < baseline.divergence.mean()
