# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the risk-sensitive MisanthropicAgent runtime component."""

from __future__ import annotations

import numpy as np
import pytest
import torch

from runtime.misanthropic_agent import MisanthropicAgent


class SyntheticMarketEnv:
    """Deterministic-ish synthetic limit order book environment for tests."""

    def __init__(self, *, num_steps: int = 32, seed: int = 42) -> None:
        self._rng = np.random.default_rng(seed)
        self.num_steps = num_steps
        self._step = 0
        self._price = 100.0

    def reset(self) -> dict[str, object]:
        self._step = 0
        self._price = 100.0
        return self._state()

    def step(self, action: int) -> tuple[dict[str, object], float, bool]:
        self._step += 1
        drift = 0.04 if action == 0 else -0.04 if action == 1 else 0.0
        shock = float(self._rng.normal(0.0, 0.03))
        self._price += drift + shock
        reward = drift + shock
        done = self._step >= self.num_steps
        return self._state(), reward, done

    def _state(self) -> dict[str, object]:
        lob_data = {
            "delta_ask_vol": self._rng.normal(0.0, 1.0, size=10),
            "delta_bid_vol": self._rng.normal(0.0, 1.0, size=10),
            "depth": float(self._rng.uniform(20.0, 120.0)),
            "rv": float(self._rng.normal(0.0, 0.2)),
            "skew": float(self._rng.uniform(-1.0, 1.0)),
        }
        return {"lob_data": lob_data, "price": float(self._price)}


@pytest.fixture(name="telemetry_buffer")
def fixture_telemetry_buffer() -> list[dict[str, float]]:
    return []


@pytest.fixture(name="agent")
def fixture_agent(telemetry_buffer: list[dict[str, float]]) -> MisanthropicAgent:
    torch.manual_seed(123)
    return MisanthropicAgent(
        rng=np.random.default_rng(7),
        telemetry_hook=telemetry_buffer.append,
        write_metrics=False,
    )


@pytest.fixture(name="env")
def fixture_env() -> SyntheticMarketEnv:
    return SyntheticMarketEnv(num_steps=24, seed=99)


def test_step_returns_valid_action_and_size(
    agent: MisanthropicAgent, env: SyntheticMarketEnv
) -> None:
    state = env.reset()
    action, size = agent.step(state["lob_data"], state["price"])
    assert action in {0, 1, 2}
    assert np.isfinite(size)
    assert size >= 0.0


def test_repose_raises_lambda_on_cvar_violation(agent: MisanthropicAgent) -> None:
    agent.batch_size = 4
    agent.cvar_floor = 0.1
    agent.lambda_cvar = 0.0

    zero_state = np.zeros(agent.state_size, dtype=np.float32)
    for _ in range(agent.batch_size):
        agent.replay.add((zero_state, 0, -0.2, zero_state, False))

    initial_priorities = list(agent.replay.priorities)

    for param in agent.model.parameters():
        torch.nn.init.constant_(param, 0.0)
    for param in agent.target_model.parameters():
        torch.nn.init.constant_(param, 0.0)

    agent.repose()

    assert agent.lambda_cvar > 0.0
    assert agent.replay.priorities[0] != initial_priorities[0]


def test_train_updates_metrics(agent: MisanthropicAgent, env: SyntheticMarketEnv) -> None:
    agent.batch_size = 8
    agent.train(env, episodes=1, save_artifacts=False)

    coverage = agent.conformal_coverage()
    assert 0.0 <= coverage <= 1.0
    assert agent.lambda_cvar >= 0.0

    stream = []
    state = env.reset()
    for _ in range(16):
        stream.append((state["lob_data"], state["price"]))
        state, _, _ = env.step(action=2)

    metrics = agent.evaluate_stream(stream)
    assert set(metrics) == {"pnl_mean", "cvar_95", "coverage", "r2_ofi"}
    assert np.isfinite(metrics["pnl_mean"])
    assert 0.0 <= metrics["coverage"] <= 1.0


def test_telemetry_hook_receives_metrics(
    agent: MisanthropicAgent,
    env: SyntheticMarketEnv,
    telemetry_buffer: list[dict[str, float]],
) -> None:
    state = env.reset()
    agent.step(state["lob_data"], state["price"])
    assert telemetry_buffer, "telemetry hook must receive metrics"
    latest = telemetry_buffer[-1]
    assert {"threat", "lambda_cvar", "coverage"} <= latest.keys()


def test_apply_thermo_feedback_adjusts_controls(agent: MisanthropicAgent) -> None:
    base_capital = agent.capital
    agent.apply_thermo_feedback(
        latency_ratio=1.2,
        coherency=0.3,
        tail_risk=0.1,
        coverage_shortfall=0.2,
    )
    assert agent.capital < base_capital
    aggressive_lambda = agent.lambda_cvar
    assert aggressive_lambda > 0.0

    agent.apply_thermo_feedback(
        latency_ratio=1.0,
        coherency=0.9,
        tail_risk=0.0,
        coverage_shortfall=0.0,
    )
    assert agent.lambda_cvar <= aggressive_lambda
