# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Coverage battery for analytics.regime.src.consensus.hncm_adapter."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pytest

from analytics.regime.src.consensus.hncm_adapter import (
    AgentVote,
    ConsensusDecision,
    HNCMConsensusAdapter,
    _StateStore,
    clamp,
    ema,
    ews_to_vote,
)


def _adapter(tmp_path: Path, **kwargs: object) -> HNCMConsensusAdapter:
    return HNCMConsensusAdapter(state_path=tmp_path / "hncm_state.json", **kwargs)


# ---------- helpers ----------


def test_clamp() -> None:
    assert clamp(0.5, 0.0, 1.0) == 0.5
    assert clamp(-1.0, 0.0, 1.0) == 0.0
    assert clamp(9.0, 0.0, 1.0) == 1.0


def test_ema() -> None:
    assert ema(0.0, 1.0, 1.0) == 1.0
    assert ema(0.0, 1.0, 0.5) == 0.5


# ---------- _StateStore ----------


def test_statestore_fresh_when_absent(tmp_path: Path) -> None:
    s = _StateStore(tmp_path / "hncm_state.json")
    assert s.state == {"reward_ema": {}, "agent_weights": {}}


def test_statestore_loads_valid(tmp_path: Path) -> None:
    p = tmp_path / "hncm_state.json"
    p.write_text(json.dumps({"reward_ema": {"a": 0.5}, "agent_weights": {"a": -1.0}}))
    s = _StateStore(p)
    assert s.get_reward("a") == 0.5
    # negative weight floored to 0
    assert s.get_weight("a") == 0.0


def test_statestore_corrupt_file_backed_up(tmp_path: Path) -> None:
    p = tmp_path / "hncm_state.json"
    p.write_text("<<<not json>>>")
    s = _StateStore(p)
    assert s.state == {"reward_ema": {}, "agent_weights": {}}
    assert p.with_suffix(".corrupt.json").exists()


def test_statestore_non_mapping_json_resets(tmp_path: Path) -> None:
    p = tmp_path / "hncm_state.json"
    p.write_text(json.dumps([1, 2, 3]))
    s = _StateStore(p)
    assert s.state == {"reward_ema": {}, "agent_weights": {}}


def test_statestore_wrong_inner_types_reset(tmp_path: Path) -> None:
    p = tmp_path / "hncm_state.json"
    p.write_text(json.dumps({"reward_ema": [1], "agent_weights": {}}))
    s = _StateStore(p)
    assert s.state == {"reward_ema": {}, "agent_weights": {}}


def test_statestore_getters_defaults(tmp_path: Path) -> None:
    s = _StateStore(tmp_path / "hncm_state.json")
    assert s.get_reward("missing") == 0.0
    assert s.get_weight("missing") == 1.0


def test_statestore_setters_and_flush(tmp_path: Path) -> None:
    p = tmp_path / "hncm_state.json"
    s = _StateStore(p)
    s.set_reward("a", 0.7)
    s.set_weight("a", -2.0)  # floored
    s.flush()
    assert s.get_reward("a") == 0.7
    assert s.get_weight("a") == 0.0
    reloaded = json.loads(p.read_text())
    assert reloaded["reward_ema"]["a"] == 0.7


# ---------- validation ----------


def test_validate_base_weights_rejects_negative(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="non-negative"):
        _adapter(tmp_path, base_weights={"a": -0.1})


def test_validate_alpha_rejects_out_of_range(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="alpha"):
        _adapter(tmp_path, alpha=0.0)
    with pytest.raises(ValueError, match="alpha"):
        _adapter(tmp_path, alpha=1.5)


def test_validate_alpha_accepts_boundary(tmp_path: Path) -> None:
    a = _adapter(tmp_path, alpha=1.0)
    assert a.alpha == 1.0


def test_validate_thresholds_rejects_inverted(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="thresholds"):
        _adapter(tmp_path, buy_threshold=-0.5, sell_threshold=0.5)


# ---------- aggregate / mapping ----------


def test_aggregate_sets_default_weight_for_new_agent(tmp_path: Path) -> None:
    a = _adapter(tmp_path)
    score, weights = a.aggregate([AgentVote("new", 1.0)])
    assert weights["new"] == 1.0
    assert score == pytest.approx(1.0)


def test_effective_weights_override(tmp_path: Path) -> None:
    w = HNCMConsensusAdapter._effective_weights(
        {"a": 1.0}, learned={"a": 2.0}, override={"a": 5.0, "b": 3.0}
    )
    assert w["a"] == 5.0
    assert w["b"] == 3.0


def test_decide_with_override_weights(tmp_path: Path) -> None:
    a = _adapter(tmp_path, base_weights={"x": 1.0})
    dec = a.decide([AgentVote("x", 0.9)], override_weights={"x": 2.0})
    assert dec.weights["x"] == 2.0


def test_aggregate_empty_votes(tmp_path: Path) -> None:
    a = _adapter(tmp_path)
    score, weights = a.aggregate([])
    assert score == 0.0
    assert weights == {}


def test_aggregate_zero_confidence_yields_zero(tmp_path: Path) -> None:
    a = _adapter(tmp_path)
    score, _ = a.aggregate([AgentVote("x", 1.0, confidence=0.0)])
    assert score == 0.0


def test_score_to_action_branches(tmp_path: Path) -> None:
    a = _adapter(tmp_path, buy_threshold=0.15, sell_threshold=-0.15)
    assert a.score_to_action(0.9) == "BUY"
    assert a.score_to_action(-0.9) == "SELL"
    assert a.score_to_action(0.0) == "HOLD"


def test_confidence_from_score(tmp_path: Path) -> None:
    a = _adapter(tmp_path)
    assert a.confidence_from_score(-0.4) == pytest.approx(0.4)


# ---------- online learning ----------


def test_update_feedback_updates_rewards(tmp_path: Path) -> None:
    a = _adapter(tmp_path, alpha=0.5)
    w = a.update_feedback(1.0, {"x": 1.0, "y": -1.0})
    assert set(w) == {"x", "y"}
    assert w["x"] > w["y"]


def test_learned_weights_maps_reward_range(tmp_path: Path) -> None:
    a = _adapter(tmp_path)
    a.store.set_reward("a", -1.0)
    a.store.set_reward("b", 1.0)
    w = a.learned_weights()
    assert w["a"] == pytest.approx(0.05)
    assert w["b"] == pytest.approx(1.0)


# ---------- high-level decide ----------


def test_decide_default_learned_weights(tmp_path: Path) -> None:
    a = _adapter(tmp_path, base_weights={"x": 1.0})
    dec = a.decide([AgentVote("x", 0.9)])
    assert isinstance(dec, ConsensusDecision)
    assert dec.action == "BUY"


def test_decide_with_explicit_learned_weights_override(tmp_path: Path) -> None:
    a = _adapter(tmp_path, base_weights={"x": 1.0, "y": 1.0})
    dec = a.decide(
        [AgentVote("x", -1.0), AgentVote("y", -1.0)],
        learned_weights={"x": 2.0},
    )
    assert dec.action == "SELL"
    assert dec.confidence == pytest.approx(1.0)


# ---------- ews_to_vote ----------


@dataclass
class _EWSProb:
    probability: float


@dataclass
class _EWSScore:
    ews_score: float


@dataclass
class _EWSEmpty:
    other: Optional[float] = None


def test_ews_to_vote_uses_probability() -> None:
    vote = ews_to_vote("agentP", _EWSProb(probability=1.0))
    assert vote.agent == "agentP"
    assert vote.score == pytest.approx(1.0)


def test_ews_to_vote_probability_zero_maps_negative() -> None:
    vote = ews_to_vote("agentP", _EWSProb(probability=0.0))
    assert vote.score == pytest.approx(-1.0)


def test_ews_to_vote_falls_back_to_ews_score() -> None:
    vote = ews_to_vote("agentS", _EWSScore(ews_score=0.5))
    assert vote.score == pytest.approx(0.5)


def test_ews_to_vote_disable_probability_uses_score() -> None:
    vote = ews_to_vote("agentS", _EWSScore(ews_score=-0.3), use_probability=False)
    assert vote.score == pytest.approx(-0.3)


def test_ews_to_vote_neither_defaults_zero() -> None:
    vote = ews_to_vote("agentE", _EWSEmpty())
    assert vote.score == 0.0
