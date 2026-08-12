# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for the fractal motivation module."""

from __future__ import annotations

import math

import numpy as np

from core.neuro.motivation import (
    FractalMotivationController,
    FractalMotivationEngine,
    RealTimeMotivationMonitor,
)


def test_fractal_motivation_engine_signal_is_finite() -> None:
    engine = FractalMotivationEngine(state_dim=4)
    hidden_states = np.ones((4, 4), dtype=float)
    current = np.array([0.2, 0.4, 0.6, 0.8], dtype=float)
    previous = np.array([0.1, 0.3, 0.5, 0.7], dtype=float)

    signal = engine.compute_contextual_motivation(
        hidden_states=hidden_states, current=current, previous=previous
    )

    assert math.isfinite(signal)
    metrics = engine.latest_fractal_metrics
    assert set(metrics) == {
        "hurst",
        "fractal_dim",
        "volatility",
        "scaling_exponent",
        "stability",
        "energy",
    }


def test_controller_recommend_handles_guardrails() -> None:
    controller = FractalMotivationController(
        actions=("exploit", "explore", "deepen", "broaden", "stabilize"),
        exploration_coef=0.9,
    )
    decision = controller.recommend(
        state=[0.15, 0.05, 0.62],
        signals={"PnL": 0.03, "risk_ok": False, "compliance_ok": True},
    )

    assert decision.action == "pause_and_audit"
    assert decision.scores["pause_and_audit"] >= 1e6


def test_controller_updates_monitoring_metrics() -> None:
    controller = FractalMotivationController(
        actions=("exploit", "explore", "deepen", "broaden", "stabilize"),
        exploration_coef=1.1,
    )
    decision = controller.recommend(
        state=[0.12, 0.07, 0.51, 0.33],
        signals={"PnL": 0.01, "risk_ok": True, "compliance_ok": True},
    )

    metrics = decision.monitor_metrics
    assert set(metrics) == {
        "signal_mean",
        "signal_std",
        "reward_mean",
        "score_mean",
        "action_entropy",
    }
    assert math.isfinite(metrics["signal_mean"])


def test_monitor_entropy_range() -> None:
    monitor = RealTimeMotivationMonitor(window=8)
    metrics = monitor.observe(0.1, 0.05, {"explore": 1.0}, "explore")

    assert 0.0 <= metrics["action_entropy"] <= 1.0
