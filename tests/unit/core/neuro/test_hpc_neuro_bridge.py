# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for HPC-Neuro integration bridge."""

import pytest

from core.neuro.hpc_neuro_bridge import HPCNeuroBridge
from core.neuro.signal_bus import NeuroSignalBus

pytestmark = pytest.mark.L3


@pytest.fixture
def bus():
    return NeuroSignalBus()


@pytest.fixture
def bridge(bus):
    return HPCNeuroBridge(bus)


class TestPWPEPublishing:
    """PWPE is published to the bus."""

    def test_pwpe_published(self, bus, bridge):
        bridge.process_hpc_output(pwpe=1.5, action=0, state_entropy=0.5)
        snapshot = bus.snapshot()
        assert snapshot.hpc_pwpe == pytest.approx(1.5, abs=1e-6)

    def test_negative_pwpe_published_as_abs(self, bus, bridge):
        bridge.process_hpc_output(pwpe=-2.0, action=0, state_entropy=0.5)
        snapshot = bus.snapshot()
        assert snapshot.hpc_pwpe == pytest.approx(2.0, abs=1e-6)


class TestSerotoninStressMapping:
    """High PWPE → high serotonin stress."""

    def test_high_pwpe_high_serotonin(self, bus, bridge):
        result = bridge.process_hpc_output(pwpe=5.0, action=0, state_entropy=0.5)
        assert result["stress"] > 0.9, "High PWPE should give high stress"
        snapshot = bus.snapshot()
        assert snapshot.serotonin_level > 0.9

    def test_zero_pwpe_moderate_serotonin(self, bus, bridge):
        result = bridge.process_hpc_output(pwpe=0.0, action=0, state_entropy=0.5)
        assert result["stress"] == pytest.approx(0.5, abs=0.01)

    def test_low_pwpe_lower_serotonin(self, bus, bridge):
        r_low = bridge.process_hpc_output(pwpe=0.1, action=0, state_entropy=0.5)
        bus2 = NeuroSignalBus()
        bridge2 = HPCNeuroBridge(bus2)
        r_high = bridge2.process_hpc_output(pwpe=3.0, action=0, state_entropy=0.5)
        assert r_low["stress"] < r_high["stress"]


class TestConfidenceMapping:
    """Low entropy → high confidence."""

    def test_low_entropy_high_confidence(self, bridge):
        result = bridge.process_hpc_output(pwpe=1.0, action=0, state_entropy=0.01)
        assert result["confidence"] > 0.9

    def test_high_entropy_low_confidence(self, bridge):
        result = bridge.process_hpc_output(pwpe=1.0, action=0, state_entropy=10.0)
        assert result["confidence"] < 0.15

    def test_zero_entropy_max_confidence(self, bridge):
        result = bridge.process_hpc_output(pwpe=1.0, action=0, state_entropy=0.0)
        assert result["confidence"] == pytest.approx(1.0)


class TestIntegratedDecision:
    """Integrated decision contains all required keys."""

    def test_all_keys_present(self, bridge):
        decision = bridge.get_integrated_decision(kelly_base=1.0)
        expected_keys = {
            "should_hold",
            "position_multiplier",
            "learning_rate",
            "regime",
            "kuramoto_R",
            "hpc_pwpe",
            "ecs_free_energy",
            "serotonin_level",
            "dopamine_rpe",
            "gaba_inhibition",
        }
        assert expected_keys.issubset(decision.keys())

    def test_decision_after_hpc_output(self, bus, bridge):
        bridge.process_hpc_output(pwpe=2.0, action=1, state_entropy=0.5)
        decision = bridge.get_integrated_decision(kelly_base=0.5)
        assert decision["hpc_pwpe"] == pytest.approx(2.0, abs=1e-6)
        assert decision["position_multiplier"] >= 0.0
        assert decision["learning_rate"] > 0.0


class TestAdaptiveThreshold:
    """Adaptive PWPE threshold tracks distribution."""

    def test_threshold_increases_with_higher_pwpe(self, bridge):
        low_history = [0.1, 0.2, 0.15, 0.3, 0.1, 0.25, 0.2, 0.1, 0.15, 0.2]
        high_history = [1.0, 2.0, 1.5, 3.0, 1.0, 2.5, 2.0, 1.0, 1.5, 2.0]
        t_low = bridge.compute_adaptive_threshold(low_history)
        t_high = bridge.compute_adaptive_threshold(high_history)
        assert t_high > t_low

    def test_empty_history_returns_zero(self, bridge):
        assert bridge.compute_adaptive_threshold([]) == 0.0

    def test_quantile_parameter(self, bridge):
        history = list(range(100))
        t_50 = bridge.compute_adaptive_threshold(history, quantile=0.5)
        t_90 = bridge.compute_adaptive_threshold(history, quantile=0.9)
        assert t_90 > t_50


class TestFullPipeline:
    """End-to-end: HPC output → bus signals → trading decision."""

    def test_hpc_to_decision_pipeline(self, bus, bridge):
        # 1. HPC produces output
        hpc_result = bridge.process_hpc_output(pwpe=1.5, action=2, state_entropy=0.3)

        # 2. Check bus state
        snapshot = bus.snapshot()
        assert snapshot.hpc_pwpe > 0
        assert snapshot.serotonin_level > 0

        # 3. Get integrated decision
        decision = bridge.get_integrated_decision(kelly_base=0.8)
        assert isinstance(decision["should_hold"], bool)
        assert 0.0 <= decision["position_multiplier"] <= 0.8 + 1e-6
        assert decision["learning_rate"] > 0
        assert decision["regime"] in {"normal", "elevated", "crisis", "recovery"}
