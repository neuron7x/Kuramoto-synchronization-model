"""Tests for the fractal motivation controller."""

from __future__ import annotations

import math

import numpy as np

from core.neuro.advanced import FractalMotivationController


def test_guardrail_violation_triggers_pause_and_audit() -> None:
    controller = FractalMotivationController(
        ["open_long", "hold"], rng=np.random.default_rng(1)
    )

    state = [0.1, 0.2, 0.3]
    signals = {"risk_ok": False, "compliance_ok": True, "PnL": 0.0}

    action = controller.get_recommended_action(state, signals)

    assert action == "pause_and_audit"
    assert controller.total_count == 0


def test_ucb_scores_are_finite_after_update() -> None:
    actions = ["open_long", "open_short", "hold"]
    weights = np.array([0.2, -0.1, 0.05], dtype=float)
    controller = FractalMotivationController(
        actions,
        exploration_coef=0.5,
        value_weights=weights,
        rng=np.random.default_rng(7),
    )

    state = [0.1, -0.2, 0.4]
    signals = {"PnL": 0.01, "risk_ok": True, "compliance_ok": True}

    recommended = controller.get_recommended_action(state, signals)
    scores = controller.ucb_scores()

    assert recommended in actions
    assert controller.total_count == 1
    assert math.isfinite(scores[recommended])


def test_hazard_penalty_reduces_open_action_values() -> None:
    actions = ["open_long", "open_short", "hold"]
    weights = np.array([0.0, 0.0, 0.0], dtype=float)

    safe_controller = FractalMotivationController(
        actions, value_weights=weights, rng=np.random.default_rng(42)
    )
    hazard_controller = FractalMotivationController(
        actions, value_weights=weights, rng=np.random.default_rng(42)
    )

    state = [0.0, 0.0, 0.0]
    safe_signals = {"PnL": 0.0, "risk_ok": True, "compliance_ok": True, "hazard": False}
    hazard_signals = {
        "PnL": 0.0,
        "risk_ok": True,
        "compliance_ok": True,
        "hazard": True,
    }

    safe_controller.get_recommended_action(state, safe_signals)
    hazard_controller.get_recommended_action(state, hazard_signals)

    assert hazard_controller.total_count == 1
    assert (
        hazard_controller.ucb_scores()["open_long"]
        <= safe_controller.ucb_scores()["open_long"]
    )
