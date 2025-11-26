"""Unit tests for the neuroeconomic actor-critic core."""

from __future__ import annotations

import math
from typing import Sequence

import pytest

from core.neuro.advanced.neuroecon import AdvancedNeuroEconCore, DecisionOption

try:
    import torch
except (
    ModuleNotFoundError
):  # pragma: no cover - fallback for environments without torch
    torch = None


@pytest.mark.skipif(
    torch is None, reason="PyTorch is required for AdvancedNeuroEconCore"
)
def test_simulate_decision_returns_expected_value() -> None:
    torch.manual_seed(7)
    core = AdvancedNeuroEconCore(
        risk_tolerance=0.55,
        uncertainty_reduction=0.25,
        psychiatric_mod=0.9,
        temperature=0.75,
    )

    options: Sequence[DecisionOption] = (
        DecisionOption(reward=120.0, risk=0.6, cost=40.0),
        DecisionOption(reward=60.0, risk=0.1, cost=15.0),
    )
    distribution, values = core.policy_distribution(options)
    choice, value = core.simulate_decision(options, deterministic=True)

    assert choice == int(torch.argmax(distribution.probs).item())
    assert math.isclose(value, float(values[choice]), rel_tol=1e-6)
    assert math.isclose(value, core.evaluate_option(options[choice]), rel_tol=1e-6)


@pytest.mark.skipif(
    torch is None, reason="PyTorch is required for AdvancedNeuroEconCore"
)
def test_update_q_zero_modulation_preserves_values() -> None:
    core = AdvancedNeuroEconCore(psychiatric_mod=0.0)

    delta = core.update_Q(0.0, 1, 25.0, 0.5, 0)

    assert delta == 0.0
    assert core.get_q_value(0.0, 1) == 0.0


@pytest.mark.skipif(
    torch is None, reason="PyTorch is required for AdvancedNeuroEconCore"
)
def test_temporal_difference_error_matches_update_delta() -> None:
    core = AdvancedNeuroEconCore(
        alpha=0.2, dopamine_scale=0.5, psychiatric_mod=0.75, seed=11
    )

    td_error = core.temporal_difference_error(0.0, 1, 10.0, 0.3, 0)
    expected_delta = td_error * core.dopamine_scale * core.psychiatric_mod
    previous_q = core.get_q_value(0.0, 1)

    delta = core.update_Q(0.0, 1, 10.0, 0.3, 0)

    assert math.isclose(delta, expected_delta, rel_tol=1e-6)
    assert math.isclose(
        core.get_q_value(0.0, 1),
        previous_q + core.alpha * expected_delta,
        rel_tol=1e-6,
    )


@pytest.mark.skipif(
    torch is None, reason="PyTorch is required for AdvancedNeuroEconCore"
)
def test_train_on_scenario_accumulates_learning_signal() -> None:
    core = AdvancedNeuroEconCore(dopamine_scale=0.6, psychiatric_mod=0.8, seed=3)

    states = [0.0, 0.4, 0.2]
    actions = [1, 0, 1]
    rewards = [10.0, -5.0]

    history = core.train_on_scenario(states, actions, rewards)

    assert len(history) == len(rewards)
    assert all(isinstance(delta, float) for delta in history)
    assert core.get_q_value(states[0], actions[0]) != 0.0


@pytest.mark.skipif(
    torch is None, reason="PyTorch is required for AdvancedNeuroEconCore"
)
def test_policy_distribution_temperature_controls_entropy() -> None:
    core = AdvancedNeuroEconCore(seed=17)
    options = (
        {"reward": 100.0, "risk": 0.5, "cost": 25.0},
        {"reward": 70.0, "risk": 0.2, "cost": 15.0},
        {"reward": 40.0, "risk": 0.05, "cost": 5.0},
    )

    cold, _ = core.policy_distribution(options, temperature=0.25)
    hot, _ = core.policy_distribution(options, temperature=3.0)

    assert float(cold.probs.max()) > float(hot.probs.max())
    assert math.isclose(float(cold.probs.sum()), 1.0, rel_tol=1e-6)
    assert math.isclose(float(hot.probs.sum()), 1.0, rel_tol=1e-6)


@pytest.mark.skipif(
    torch is None, reason="PyTorch is required for AdvancedNeuroEconCore"
)
def test_evaluate_option_accepts_dataclass_instance() -> None:
    core = AdvancedNeuroEconCore(
        risk_tolerance=0.6, uncertainty_reduction=0.1, psychiatric_mod=0.85
    )
    option = DecisionOption(reward=150.0, risk=0.4, cost=25.0)

    value = core.evaluate_option(option)
    manual = option.reward * (
        1.0 + core.risk_tolerance * option.risk
    ) * core.psychiatric_mod - option.cost * (1.0 - core.uncertainty_reduction)

    assert math.isclose(value, manual, rel_tol=1e-6)
