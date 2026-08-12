# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Coverage battery for analytics.regime.src.consensus.hncm_neuro."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from analytics.regime.src.consensus.hncm_neuro import (
    AgentVote,
    ConsensusDecision,
    NeuroConsensusAdapter,
    clamp,
    ema,
    softmax,
)


def _adapter(tmp_path: Path, **kwargs: object) -> NeuroConsensusAdapter:
    return NeuroConsensusAdapter(state_path=tmp_path / "neuro_state.json", **kwargs)


# ---------- helpers ----------


def test_clamp_in_range_below_above() -> None:
    assert clamp(0.5, 0.0, 1.0) == 0.5
    assert clamp(-2.0, 0.0, 1.0) == 0.0
    assert clamp(2.0, 0.0, 1.0) == 1.0


def test_ema_step() -> None:
    assert ema(0.0, 1.0, 0.5) == 0.5
    assert ema(1.0, 1.0, 0.3) == 1.0


def test_softmax_empty_returns_empty() -> None:
    assert softmax({}, 0.7) == {}


def test_softmax_normalizes_to_one() -> None:
    out = softmax({"a": 1.0, "b": 0.0}, 0.7)
    assert pytest.approx(sum(out.values()), rel=1e-9) == 1.0
    assert out["a"] > out["b"]


def test_softmax_clamps_low_temperature() -> None:
    # temperature <= 1e-6 is floored; must not raise / divide-by-zero
    out = softmax({"a": 1.0, "b": 2.0}, -5.0)
    assert pytest.approx(sum(out.values()), rel=1e-9) == 1.0


# ---------- _State ----------


def test_state_created_when_absent(tmp_path: Path) -> None:
    a = _adapter(tmp_path)
    assert a.state.s["reward_ema"] == {}
    assert a.state.path.parent.exists()


def test_state_loads_existing_file(tmp_path: Path) -> None:
    p = tmp_path / "neuro_state.json"
    p.write_text(json.dumps({"reward_ema": {"x": 0.4}, "extra": 1}))
    a = NeuroConsensusAdapter(state_path=p)
    assert a.state.s["reward_ema"] == {"x": 0.4}
    assert a.state.s["extra"] == 1


def test_state_corrupt_file_is_backed_up(tmp_path: Path) -> None:
    p = tmp_path / "neuro_state.json"
    p.write_text("{not valid json")
    NeuroConsensusAdapter(state_path=p)
    assert p.with_suffix(".corrupt.json").exists()


def test_state_flush_roundtrip(tmp_path: Path) -> None:
    a = _adapter(tmp_path)
    a.state.s["reward_ema"]["z"] = 0.9
    a.state.flush()
    reloaded = json.loads(a.state.path.read_text())
    assert reloaded["reward_ema"]["z"] == 0.9


# ---------- effective weights / aggregate ----------


def test_effective_weights_learned_positive_total() -> None:
    w = NeuroConsensusAdapter._effective_weights(
        {"a": 1.0, "b": 1.0}, learned={"a": 2.0, "b": 2.0}
    )
    assert w["a"] == pytest.approx(w["b"])
    assert sum(w.values()) > 0


def test_effective_weights_learned_zero_total() -> None:
    w = NeuroConsensusAdapter._effective_weights({"a": 1.0}, learned={"a": 0.0, "b": 0.0})
    assert w["a"] == 0.0
    assert w["b"] == 0.0


def test_effective_weights_override_and_floor() -> None:
    w = NeuroConsensusAdapter._effective_weights(
        {"a": 1.0}, override={"a": -5.0, "b": 3.0}
    )
    assert w["a"] == 0.0  # floored
    assert w["b"] == 3.0


def test_aggregate_weighted_mean(tmp_path: Path) -> None:
    a = _adapter(tmp_path, base_weights={"x": 1.0, "y": 1.0})
    votes = [AgentVote("x", 1.0), AgentVote("y", -1.0, confidence=0.5)]
    score, weights = a.aggregate(votes)
    assert -1.0 <= score <= 1.0
    assert "x" in weights


def test_aggregate_empty_votes_zero(tmp_path: Path) -> None:
    a = _adapter(tmp_path)
    score, weights = a.aggregate([])
    assert score == 0.0
    assert weights == {}


def test_aggregate_clamps_out_of_range_inputs(tmp_path: Path) -> None:
    a = _adapter(tmp_path)
    score, _ = a.aggregate([AgentVote("x", 5.0, confidence=9.0)])
    assert score == 1.0


# ---------- action mapping ----------


def test_score_to_action_all_branches(tmp_path: Path) -> None:
    a = _adapter(tmp_path, buy_threshold=0.2, sell_threshold=-0.2)
    assert a.score_to_action(0.5) == "BUY"
    assert a.score_to_action(-0.5) == "SELL"
    assert a.score_to_action(0.0) == "HOLD"


def test_confidence_from_score() -> None:
    assert NeuroConsensusAdapter.confidence_from_score(-0.7) == pytest.approx(0.7)
    assert NeuroConsensusAdapter.confidence_from_score(5.0) == 1.0


# ---------- neuro internals ----------


def test_metaplasticity_gain_bounds(tmp_path: Path) -> None:
    a = _adapter(tmp_path)
    a.state.s["activation_ma"]["g"] = 0.1
    # high margin → capped at 2.5
    assert a._metaplasticity_gain("g", 1.0) <= 2.5
    # score below theta → margin 0 → gain 1.0
    assert a._metaplasticity_gain("g", 0.05) == pytest.approx(1.0)


def test_update_activation_ma_clamped(tmp_path: Path) -> None:
    a = _adapter(tmp_path)
    a._update_activation_ma("m", 0.9)
    assert 0.0 <= a.state.s["activation_ma"]["m"] <= 1.0


def test_update_eligibility_accumulates_and_clamps(tmp_path: Path) -> None:
    a = _adapter(tmp_path, lambda_trace=0.9)
    for _ in range(50):
        e = a._update_eligibility("e", 1.0)
    assert e <= 5.0


def test_update_reliability_neutral_zero_score(tmp_path: Path) -> None:
    a = _adapter(tmp_path)
    a._update_reliability("r", realized=1.0, score=0.0)
    assert 0.0 <= a.state.s["reliability"]["r"] <= 1.0


def test_update_reliability_aligned_and_opposed(tmp_path: Path) -> None:
    a = _adapter(tmp_path)
    a._update_reliability("aligned", realized=1.0, score=0.8)
    a._update_reliability("opposed", realized=1.0, score=-0.8)
    assert a.state.s["reliability"]["aligned"] > a.state.s["reliability"]["opposed"]


def test_page_hinkley_detects_change(tmp_path: Path) -> None:
    a = _adapter(tmp_path, ph_threshold=0.01, ph_delta=0.5)
    detected = any(a._page_hinkley_update(-1.0) for _ in range(20))
    assert detected is True


def test_page_hinkley_stable_no_change(tmp_path: Path) -> None:
    a = _adapter(tmp_path, ph_threshold=10.0)
    assert a._page_hinkley_update(0.0) is False


def test_consolidate_moves_toward_weights(tmp_path: Path) -> None:
    a = _adapter(tmp_path)
    a._consolidate({"c": 1.0}, beta=0.5)
    assert a.state.s["consolidated"]["c"] == pytest.approx(1.0)
    a._consolidate({"c": 0.0}, beta=0.5)
    assert a.state.s["consolidated"]["c"] == pytest.approx(0.5)


def test_energy_budget_none_passthrough(tmp_path: Path) -> None:
    a = _adapter(tmp_path, energy_budget=None)
    new = {"a": 5.0}
    assert a._apply_energy_budget({"a": 0.0}, new) == new


def test_energy_budget_within_budget(tmp_path: Path) -> None:
    a = _adapter(tmp_path, energy_budget=10.0)
    new = {"a": 1.0}
    assert a._apply_energy_budget({"a": 0.0}, new) == new


def test_energy_budget_zero_delta(tmp_path: Path) -> None:
    a = _adapter(tmp_path, energy_budget=0.1)
    new = {"a": 1.0}
    assert a._apply_energy_budget({"a": 1.0}, new) == new


def test_energy_budget_scales_down(tmp_path: Path) -> None:
    a = _adapter(tmp_path, energy_budget=0.5)
    out = a._apply_energy_budget({"a": 0.0}, {"a": 2.0})
    assert out["a"] == pytest.approx(0.5)


def test_r_to_preweight_monotone(tmp_path: Path) -> None:
    a = _adapter(tmp_path)
    assert a._r_to_preweight(-1.0) >= 1e-3
    assert a._r_to_preweight(1.0) > a._r_to_preweight(-1.0)


def test_learned_weights_empty_when_no_rewards(tmp_path: Path) -> None:
    a = _adapter(tmp_path)
    assert a.learned_weights() == {}


def test_learned_weights_with_consolidation(tmp_path: Path) -> None:
    a = _adapter(tmp_path, ewc_strength=0.5)
    a.state.s["reward_ema"] = {"a": 0.8, "b": -0.3}
    a.state.s["consolidated"] = {"a": 0.9, "b": 0.1}
    w = a.learned_weights()
    assert pytest.approx(sum(w.values()), rel=1e-9) == 1.0


def test_learned_weights_without_consolidation(tmp_path: Path) -> None:
    a = _adapter(tmp_path, ewc_strength=0.0)
    a.state.s["reward_ema"] = {"a": 0.8, "b": -0.3}
    w = a.learned_weights()
    assert pytest.approx(sum(w.values()), rel=1e-9) == 1.0


# ---------- main API ----------


def test_decide_returns_decision(tmp_path: Path) -> None:
    a = _adapter(tmp_path, base_weights={"x": 1.0})
    dec = a.decide([AgentVote("x", 0.9)])
    assert isinstance(dec, ConsensusDecision)
    assert dec.action == "BUY"
    assert a.state.s["last_weights"]


def test_decide_with_explicit_learned_weights(tmp_path: Path) -> None:
    a = _adapter(tmp_path, base_weights={"x": 1.0})
    dec = a.decide([AgentVote("x", -0.9)], learned_weights={"x": 1.0})
    assert dec.action == "SELL"


def test_update_feedback_learns_and_persists(tmp_path: Path) -> None:
    a = _adapter(tmp_path, base_weights={"x": 1.0, "y": 1.0})
    w = a.update_feedback(0.8, {"x": 0.9, "y": -0.5})
    assert isinstance(w, dict)
    assert a.state.path.exists()
    reloaded = json.loads(a.state.path.read_text())
    assert "reward_ema" in reloaded


def test_update_feedback_change_regime_adapts_tau(tmp_path: Path) -> None:
    a = _adapter(tmp_path, ph_threshold=0.001, ph_delta=0.5, tau=1.5)
    tau_before = a.tau
    for _ in range(15):
        a.update_feedback(-1.0, {"x": 0.5})
    assert a.tau <= tau_before
