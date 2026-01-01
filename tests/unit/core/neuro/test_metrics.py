"""Unit tests for neuro metrics helpers."""

import pytest

from tradepulse.core.neuro.metrics import (
    BalanceMetrics,
    compute_balance_metrics,
    compute_objective,
    compute_stability,
)


def test_compute_balance_metrics_fixed_state():
    state = {
        "dopamine_level": 0.6,
        "serotonin_level": 0.3,
        "gaba_inhibition": 0.4,
        "na_arousal": 1.2,
        "ach_attention": 0.8,
    }
    setpoints = {"da_5ht_ratio": 1.67, "excitation_inhibition": 1.5}

    metrics = compute_balance_metrics(state, setpoints)

    assert metrics.dopamine_serotonin_ratio == pytest.approx(1.9999933333555557)
    assert metrics.gaba_excitation_balance == pytest.approx(2.571424897964431)
    assert metrics.arousal_attention_coherence == pytest.approx(0.8)
    assert metrics.homeostatic_deviation == pytest.approx(0.45594203186306065)
    assert metrics.overall_balance_score == pytest.approx(0.6868405321882042)


def test_compute_stability_with_flat_history():
    history = [0.5, 0.5, 0.5, 0.5]
    stability = compute_stability(history, history_window=4)
    assert stability == pytest.approx(1.0)


def test_compute_stability_with_insufficient_history():
    stability = compute_stability([0.5], history_window=4)
    assert stability == pytest.approx(0.5)


def test_compute_objective_fixed_values():
    balance = BalanceMetrics(
        dopamine_serotonin_ratio=2.0,
        gaba_excitation_balance=2.5,
        arousal_attention_coherence=0.8,
        overall_balance_score=0.7,
        homeostatic_deviation=0.4,
    )
    stability = 0.8

    objective = compute_objective(
        1.0,
        balance,
        stability,
        performance_min=-2.0,
        performance_max=3.0,
        performance_weight=0.45,
        balance_weight=0.35,
        stability_weight=0.2,
    )

    assert objective == pytest.approx(0.675)
