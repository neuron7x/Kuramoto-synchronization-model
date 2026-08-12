# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the adaptive recovery agent."""

import numpy as np

from runtime.recovery_agent import AdaptiveRecoveryAgent, RecoveryAction, RecoveryState


def test_agent_initialises_with_defaults() -> None:
    agent = AdaptiveRecoveryAgent()
    assert agent.alpha == 0.1
    assert agent.gamma == 0.95
    assert agent.epsilon == 0.1


def test_state_discretisation_bounds() -> None:
    agent = AdaptiveRecoveryAgent()
    state = RecoveryState(F_current=0.12, F_baseline=0.10, latency_spike=4.0, steps_in_crisis=20)
    discrete = agent.discretize_state(state)
    assert len(discrete) == 3
    assert all(isinstance(value, int) for value in discrete)


def test_choose_action_uses_epsilon_greedy() -> None:
    rng = np.random.default_rng(seed=42)
    agent = AdaptiveRecoveryAgent(epsilon=0.0, rng=rng)
    state = RecoveryState(F_current=0.11, F_baseline=0.10, latency_spike=2.0, steps_in_crisis=3)
    action = agent.choose_action(state)
    assert action in RecoveryAction.ALL


def test_q_update_improves_value() -> None:
    agent = AdaptiveRecoveryAgent(alpha=0.5)
    state = RecoveryState(F_current=0.11, F_baseline=0.10, latency_spike=2.0, steps_in_crisis=3)
    next_state = RecoveryState(
        F_current=0.105, F_baseline=0.10, latency_spike=1.5, steps_in_crisis=4
    )
    action = RecoveryAction.MEDIUM
    before = agent.Q[(agent.discretize_state(state), action)]
    agent.update(state, action, reward=0.002, next_state=next_state)
    after = agent.Q[(agent.discretize_state(state), action)]
    assert after > before


def test_recovery_params_are_monotonic() -> None:
    agent = AdaptiveRecoveryAgent()
    slow = agent.get_recovery_params(RecoveryAction.SLOW)
    fast = agent.get_recovery_params(RecoveryAction.FAST)
    assert slow["mutation_rate"] < fast["mutation_rate"]
    assert slow["recovery_speed"] < fast["recovery_speed"]
