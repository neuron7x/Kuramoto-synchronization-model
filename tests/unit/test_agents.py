# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for agent components including bandits, memory, and strategies.

This module validates the multi-armed bandit algorithms, strategy memory system,
and PI (Predictive Invariance) agent behavior used for adaptive trading strategies.

Test Coverage:
- EpsilonGreedy bandit: exploration/exploitation balance
- UCB1 bandit: upper confidence bound selection
- StrategyMemory: temporal decay and ranking
- Strategy: mutation and performance simulation
- PiAgent: market regime adaptation and repair
"""

from __future__ import annotations

import math
import random
import time

import pytest

from core.agent.bandits import UCB1, EpsilonGreedy
from core.agent.memory import StrategyMemory, StrategyRecord
from core.agent.strategy import PiAgent, Strategy


def test_epsilon_greedy_prefers_best_arm_when_exploit() -> None:
    """Test that EpsilonGreedy selects the best-performing arm when exploiting.

    With epsilon=0.0 (pure exploitation), the agent should always select
    the arm with the highest average reward.
    """
    agent = EpsilonGreedy(["a", "b"], epsilon=0.0)
    agent.update("a", 0.1)
    agent.update("b", 0.5)
    assert agent.select() == "b", "Should select arm with highest reward"


def test_ucb1_selects_unseen_arm_first() -> None:
    """Test that UCB1 prioritizes arms that haven't been tried yet.

    Upper Confidence Bound algorithm should explore untried arms first
    before refining estimates of known arms.
    """
    agent = UCB1(["x", "y"])
    choice1 = agent.select()
    agent.update(choice1, 0.1)
    choice2 = agent.select()
    assert {choice1, choice2} == {"x", "y"}, "Should try both arms before repeating"


def test_epsilon_greedy_explores(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyRng:
        def random(self) -> float:
            return 0.0

        def choice(self, seq):  # type: ignore[no-untyped-def]
            return seq[-1]

    agent = EpsilonGreedy(["a", "b"], epsilon=1.0, rng=DummyRng())
    assert agent.select() == "b"


def test_epsilon_greedy_add_remove_arm() -> None:
    agent = EpsilonGreedy(["a"], epsilon=0.1)
    agent.add_arm("b")
    assert set(agent.arms) == {"a", "b"}
    agent.update("a", 1.0)
    agent.remove_arm("a")
    assert agent.arms == ("b",)
    with pytest.raises(KeyError):
        agent.update("a", 1.0)


def test_epsilon_greedy_invalid_epsilon() -> None:
    with pytest.raises(ValueError):
        EpsilonGreedy(["a"], epsilon=-0.01)


def test_ucb1_requires_known_arm() -> None:
    agent = UCB1(["a"])
    with pytest.raises(KeyError):
        agent.update("missing", 0.1)


def test_strategy_memory_topk_orders_by_freshness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    memory = StrategyMemory(decay_lambda=0.0)
    now = time.time()
    rec_old = StrategyRecord("old", (0, 0, 0, 0, 0), score=0.2, ts=now - 10)
    rec_new = StrategyRecord("new", (0, 0, 0, 0, 0), score=0.1, ts=now)
    memory.records = [rec_old, rec_new]
    top = memory.topk(1)
    assert top[0].name == "old"


def test_strategy_memory_cleanup_removes_low_scores() -> None:
    memory = StrategyMemory(decay_lambda=0.0)
    memory.add("keep", (0, 0, 0, 0, 0), 1.0)
    memory.add("drop", (0, 0, 0, 0, 0), -1.0)
    memory.cleanup(min_score=0.5)
    names = {r.name for r in memory.records}
    assert names == {"keep"}


def test_strategy_mutation_changes_numeric_parameters() -> None:
    random.seed(42)
    strategy = Strategy(name="base", params={"alpha": 1.0, "beta": 2})
    mutant = strategy.generate_mutation()
    assert mutant.name.startswith("base_mut")
    assert mutant.params["alpha"] != strategy.params["alpha"]


def test_strategy_simulate_performance_within_expected_range() -> None:
    random.seed(1)
    strategy = Strategy(name="strategy", params={})
    score = strategy.simulate_performance(data=None)
    assert -1.0 <= score <= 2.0


def test_pi_agent_detects_instability_and_repair() -> None:
    agent = PiAgent(strategy=Strategy(name="s", params={"alpha": 1.0, "beta": math.nan}))
    state = {"R": 0.8, "delta_H": -0.1, "kappa_mean": -0.05}
    assert agent.evaluate_and_adapt(state) == "enter"
    agent.repair()
    assert agent.strategy.params["beta"] == 0.0


def test_pi_agent_mutation_creates_new_strategy() -> None:
    random.seed(7)
    agent = PiAgent(strategy=Strategy(name="s", params={"alpha": 1.0}))
    mutant = agent.mutate()
    assert mutant.strategy.name != agent.strategy.name
    assert mutant.strategy.params["alpha"] != agent.strategy.params["alpha"]


def test_pi_agent_exit_and_hold_paths() -> None:
    agent = PiAgent(strategy=Strategy(name="s", params={}))
    exit_state = {"R": 0.3, "delta_H": 0.0, "kappa_mean": 0.1, "phase_reversal": True}
    assert agent.evaluate_and_adapt(exit_state) == "exit"
    hold_state = {"R": 0.2, "delta_H": 0.0, "kappa_mean": 0.1}
    assert agent.evaluate_and_adapt(hold_state) == "hold"
