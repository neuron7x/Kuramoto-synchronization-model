# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from __future__ import annotations

from analytics.regime.src.consensus.hncm_neuro import AgentVote, NeuroConsensusAdapter


class DummyEWS:
    def __init__(
        self, probability: float | None = None, ews_score: float | None = None
    ):
        self.probability = probability
        self.ews_score = ews_score


def test_decide_basic():
    adapter = NeuroConsensusAdapter(base_weights={"a": 1.0, "b": 1.0})
    votes = (AgentVote("a", 0.8, 1.0), AgentVote("b", -0.2, 1.0))
    decision = adapter.decide(votes)
    assert decision.action in ("BUY", "SELL", "HOLD")
    assert 0.0 <= decision.confidence <= 1.0
    assert -1.0 <= decision.score <= 1.0


def test_feedback_learning_increases_good_agent():
    adapter = NeuroConsensusAdapter()
    # simulate a good agent aligned with positive outcomes
    lw0 = adapter.learned_weights()
    adapter.update_feedback(realized=1.0, agent_scores={"good": 1.0, "bad": -1.0})
    lw1 = adapter.learned_weights()
    assert lw1.get("good", 0.0) >= lw0.get("good", 0.0)


def test_energy_budget_limits_delta():
    adapter = NeuroConsensusAdapter(energy_budget=0.1)
    adapter.state.s["last_weights"] = {"a": 0.5, "b": 0.5}
    # large change requested via rewards
    adapter.state.s["reward_ema"] = {"a": 1.0, "b": -1.0}
    new_w = adapter.update_feedback(realized=1.0, agent_scores={"a": 1.0, "b": -1.0})
    delta = sum(
        abs(new_w[k] - adapter.state.s["last_weights"].get(k, 0.0)) for k in new_w
    )
    assert delta <= 0.1000001
