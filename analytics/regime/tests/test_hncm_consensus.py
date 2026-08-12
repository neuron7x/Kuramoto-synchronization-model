# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from analytics.regime.src.consensus.hncm_adapter import (
    AgentVote,
    HNCMConsensusAdapter,
    ews_to_vote,
)
from application.microservices.hncm_consensus import build_signal_with_consensus
from domain.signals import SignalAction


class DummyEWS:
    def __init__(self, probability: float | None = None, ews_score: float | None = None):
        self.probability = probability
        self.ews_score = ews_score


def read_state(path: Path) -> dict:
    return json.loads(path.read_text())


def test_aggregate_and_decide(tmp_path: Path):
    adapter = HNCMConsensusAdapter(state_path=tmp_path / "state.json")
    votes = (AgentVote("a", 0.6, 1.0), AgentVote("b", -0.2, 0.5))
    score, weights = adapter.aggregate(votes)
    assert -1.0 <= score <= 1.0
    assert set(weights) >= {"a", "b"}
    decision = adapter.decide(votes)
    assert decision.action in ("BUY", "SELL", "HOLD")
    assert math.isclose(abs(decision.score), decision.confidence, rel_tol=1e-9)
    assert decision.votes == votes


def test_learned_weights_influence(tmp_path: Path):
    adapter = HNCMConsensusAdapter(
        base_weights={"a": 1.0, "b": 1.0}, state_path=tmp_path / "state.json"
    )
    votes = (AgentVote("a", 1.0, 1.0), AgentVote("b", -1.0, 1.0))
    # зсунути ваги на користь "a"
    lw = {"a": 1.0, "b": 0.1}
    score, _ = adapter.aggregate(votes, learned_weights=lw)
    assert score > 0.0


def test_decide_respects_override_weights(tmp_path: Path):
    adapter = HNCMConsensusAdapter(
        base_weights={"a": 0.1, "b": 0.1}, state_path=tmp_path / "state.json"
    )
    votes = (AgentVote("a", -1.0, 1.0), AgentVote("b", 1.0, 1.0))
    decision = adapter.decide(votes, override_weights={"a": 5.0})
    assert decision.score < 0
    assert decision.weights["a"] == pytest.approx(5.0)


def test_feedback_updates_rewards(tmp_path: Path):
    adapter = HNCMConsensusAdapter(alpha=0.5, state_path=tmp_path / "state.json")
    learned = adapter.update_feedback(realized=1.0, agent_scores={"x": 1.0, "y": -1.0})
    assert learned["x"] > learned["y"]
    # перевірка персистентності
    again = HNCMConsensusAdapter(alpha=0.5, state_path=tmp_path / "state.json")
    learned2 = again.learned_weights()
    assert learned2["x"] > learned2["y"]


def test_feedback_state_is_persisted(tmp_path: Path):
    state_path = tmp_path / "state.json"
    adapter = HNCMConsensusAdapter(alpha=1.0, state_path=state_path)
    adapter.update_feedback(realized=0.5, agent_scores={"x": 0.25})
    payload = read_state(state_path)
    assert payload["reward_ema"]["x"] != 0


def test_state_store_recovers_from_corruption(tmp_path: Path):
    state_path = tmp_path / "state.json"
    state_path.write_text("{not-json}")
    adapter = HNCMConsensusAdapter(state_path=state_path)
    corrupt = state_path.with_suffix(".corrupt.json")
    assert corrupt.exists()
    assert adapter.learned_weights() == {}


def test_ews_to_vote_probability():
    v = ews_to_vote("ews", DummyEWS(probability=0.8))
    assert 0.0 <= v.score <= 1.0 and v.score > 0.0


def test_ews_to_vote_score():
    v = ews_to_vote("ews", DummyEWS(probability=None, ews_score=-0.7), use_probability=True)
    assert v.score == -0.7


def test_ews_to_vote_probability_clamped():
    v = ews_to_vote("ews", DummyEWS(probability=2.0))
    assert math.isclose(v.score, 1.0)


def test_threshold_validation():
    with pytest.raises(ValueError):
        HNCMConsensusAdapter(buy_threshold=-0.5, sell_threshold=0.5)


def test_alpha_validation():
    with pytest.raises(ValueError):
        HNCMConsensusAdapter(alpha=0)


def test_build_signal_with_consensus(tmp_path: Path):
    state_path = tmp_path / "state.json"
    adapter = HNCMConsensusAdapter(state_path=state_path)
    signal = build_signal_with_consensus(
        symbol="ETHUSDT",
        ews_result=DummyEWS(probability=0.75),
        agent_scores={"breakout": 0.5, "mean_revert": -0.25},
        adapter=adapter,
    )
    assert signal.symbol == "ETHUSDT"
    assert signal.action in {SignalAction.BUY, SignalAction.SELL, SignalAction.HOLD}
    assert signal.metadata
    assert {vote["agent"] for vote in signal.metadata["votes"]} >= {
        "ews",
        "breakout",
        "mean_revert",
    }
    assert all("rationale" in vote for vote in signal.metadata["votes"])
