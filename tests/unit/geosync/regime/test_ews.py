# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for EWS aggregator."""

# Import directly from module file to avoid package __init__
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "ews",
    Path(__file__).parent.parent.parent.parent.parent / "src/geosync/regime/ews.py",
)
ews_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ews_module)
EWSAggregator = ews_module.EWSAggregator
EWSConfig = ews_module.EWSConfig


class TestEWSAggregator:
    """Test EWS aggregation logic."""

    def test_kill_state_sharp_drop_negative_curvature(self):
        """Test KILL state: sharp ΔR drop with negative curvature."""
        ews = EWSAggregator()

        # Sharp drop in R and negative curvature
        state, confidence = ews.decide(
            R=0.5,
            dR=-0.15,  # Below -0.1 threshold
            kappa_min=-0.1,  # Negative
            topo_score=0.05,
            te_pass=True,
        )

        assert state == "KILL"
        assert confidence > 0.8

    def test_kill_state_extreme_curvature(self):
        """Test KILL state: extreme negative curvature."""
        ews = EWSAggregator()

        # Extreme negative curvature
        state, confidence = ews.decide(
            R=0.6,
            dR=0.0,
            kappa_min=-0.5,  # Extreme negative
            topo_score=0.05,
            te_pass=True,
        )

        assert state == "KILL"
        assert confidence > 0.9

    def test_kill_state_topo_anomaly(self):
        """Test KILL state: high topological anomaly."""
        ews = EWSAggregator()

        # High topological anomaly
        state, confidence = ews.decide(
            R=0.6,
            dR=0.0,
            kappa_min=0.1,
            topo_score=0.20,  # Above 0.15 threshold
            te_pass=True,
        )

        assert state == "KILL"
        assert confidence > 0.7

    def test_kill_state_no_causality(self):
        """Test KILL state: failed causality test."""
        ews = EWSAggregator()

        # Failed causality test
        state, confidence = ews.decide(
            R=0.6,
            dR=0.0,
            kappa_min=0.1,
            topo_score=0.05,
            te_pass=False,  # Failed
        )

        assert state == "KILL"
        assert confidence > 0.6

    def test_emergent_state_strong_signals(self):
        """Test EMERGENT state: all positive signals."""
        ews = EWSAggregator()

        # Strong positive signals
        state, confidence = ews.decide(
            R=0.85,  # High synchrony
            dR=0.05,  # Increasing
            kappa_min=0.3,  # Positive curvature
            topo_score=0.02,  # Low anomaly
            te_pass=True,
        )

        assert state == "EMERGENT"
        assert confidence > 0.6

    def test_caution_state_neutral(self):
        """Test CAUTION state: neutral conditions."""
        ews = EWSAggregator()

        # Neutral conditions - not KILL, not strong EMERGENT
        state, confidence = ews.decide(
            R=0.5,
            dR=0.0,
            kappa_min=0.0,
            topo_score=0.08,
            te_pass=True,
        )

        assert state == "CAUTION"
        assert 0.3 <= confidence <= 0.9

    def test_boundary_conditions_dr_threshold(self):
        """Test behavior at ΔR threshold boundary."""
        ews = EWSAggregator()

        # Just above threshold - should not trigger KILL
        state1, _ = ews.decide(
            R=0.5,
            dR=-0.09,  # Just above -0.1
            kappa_min=-0.1,
            topo_score=0.05,
            te_pass=True,
        )
        assert state1 != "KILL"  # Should be CAUTION

        # Just below threshold - should trigger KILL
        state2, _ = ews.decide(
            R=0.5,
            dR=-0.11,  # Just below -0.1
            kappa_min=-0.1,
            topo_score=0.05,
            te_pass=True,
        )
        assert state2 == "KILL"

    def test_custom_thresholds(self):
        """Test with custom threshold configuration."""
        config = EWSConfig(dr_threshold=0.2, topo_threshold=0.25)
        ews = EWSAggregator(config)

        # Value that would trigger KILL with default thresholds
        state, _ = ews.decide(
            R=0.5,
            dR=-0.15,  # Would trigger with default 0.1
            kappa_min=-0.1,
            topo_score=0.05,
            te_pass=True,
        )

        # With higher threshold, should not trigger KILL
        assert state != "KILL"

    def test_config_preserves_zero_thresholds(self, monkeypatch):
        """Ensure explicit zero thresholds are not replaced by env defaults."""
        monkeypatch.setenv("TP_EWS_DR_THRESHOLD", "0.5")
        monkeypatch.setenv("TP_EWS_TOPO_THRESHOLD", "0.75")

        config = EWSConfig(dr_threshold=0.0, topo_threshold=0.0)

        assert config.dr_threshold == 0.0
        assert config.topo_threshold == 0.0

        # Zero ΔR threshold should trigger KILL on any drop below 0
        ews = EWSAggregator(config)
        state, _ = ews.decide(
            R=0.5,
            dR=-0.01,
            kappa_min=-0.05,
            topo_score=0.01,
            te_pass=True,
        )

        assert state == "KILL"
