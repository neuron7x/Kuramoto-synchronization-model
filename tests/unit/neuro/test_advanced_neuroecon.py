"""Unit tests for the neuroeconomic actor-critic core."""

from __future__ import annotations

import math

import pytest

from core.neuro.advanced.neuroecon import AdvancedNeuroEconCore

try:
    import torch
except ModuleNotFoundError:  # pragma: no cover - fallback for environments without torch
    torch = None


@pytest.mark.skipif(torch is None, reason="PyTorch is required for AdvancedNeuroEconCore")
def test_simulate_decision_returns_expected_value() -> None:
    torch.manual_seed(7)
    core = AdvancedNeuroEconCore(risk_tolerance=0.55, uncertainty_reduction=0.25, psychiatric_mod=0.9)

    options = [
        {"reward": 120.0, "risk": 0.6, "cost": 40.0},
        {"reward": 60.0, "risk": 0.1, "cost": 15.0},
    ]
    choice, value = core.simulate_decision(options)

    expected_value = (
        options[choice]["reward"]
        * (1.0 + core.risk_tolerance * options[choice]["risk"])
        * core.psychiatric_mod
        - options[choice]["cost"] * (1.0 - core.uncertainty_reduction)
    )

    assert math.isclose(value, expected_value, rel_tol=1e-6)
    assert choice in {0, 1}


@pytest.mark.skipif(torch is None, reason="PyTorch is required for AdvancedNeuroEconCore")
def test_update_q_zero_modulation_preserves_values() -> None:
    core = AdvancedNeuroEconCore(psychiatric_mod=0.0)

    delta = core.update_Q(0.0, 1, 25.0, 0.5, 0)

    assert delta == 0.0
    assert core.get_q_value(0.0, 1) == 0.0


@pytest.mark.skipif(torch is None, reason="PyTorch is required for AdvancedNeuroEconCore")
def test_train_on_scenario_accumulates_learning_signal() -> None:
    core = AdvancedNeuroEconCore(dopamine_scale=0.6, psychiatric_mod=0.8, seed=3)

    states = [0.0, 0.4, 0.2]
    actions = [1, 0, 1]
    rewards = [10.0, -5.0]

    history = core.train_on_scenario(states, actions, rewards)

    assert len(history) == len(rewards)
    assert all(isinstance(delta, float) for delta in history)
    assert core.get_q_value(states[0], actions[0]) != 0.0
