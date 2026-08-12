# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for Basal Ganglia policy."""

# Import directly from module file to avoid package __init__
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "basal_ganglia",
    Path(__file__).parent.parent.parent.parent.parent / "src/geosync/policy/basal_ganglia.py",
)
basal_ganglia_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(basal_ganglia_module)
BasalGangliaPolicy = basal_ganglia_module.BasalGangliaPolicy


class TestBasalGangliaPolicy:
    """Test Basal Ganglia policy decision logic."""

    def test_no_go_on_kill(self):
        """Test NO_GO action when EWS is KILL."""
        policy = BasalGangliaPolicy()
        state = {"R": 0.8}

        action, size_hint = policy.decide(state, ews_state="KILL", risk_state="OK")

        assert action == "NO_GO"
        assert size_hint == 0.0

    def test_no_go_on_breach(self):
        """Test NO_GO action when risk state is BREACH."""
        policy = BasalGangliaPolicy()
        state = {"R": 0.8}

        action, size_hint = policy.decide(state, ews_state="EMERGENT", risk_state="BREACH")

        assert action == "NO_GO"
        assert size_hint == 0.0

    def test_go_on_emergent_and_ok(self):
        """Test GO action when EMERGENT and risk OK."""
        policy = BasalGangliaPolicy()
        state = {"R": 0.8}

        action, size_hint = policy.decide(state, ews_state="EMERGENT", risk_state="OK")

        assert action == "GO"
        # size_hint = 0.5 + 0.5 * 0.8 = 0.9
        assert abs(size_hint - 0.9) < 0.01

    def test_go_size_scales_with_r(self):
        """Test that GO size hint scales with R."""
        policy = BasalGangliaPolicy()

        # Low R
        state_low = {"R": 0.2}
        action_low, size_low = policy.decide(state_low, ews_state="EMERGENT", risk_state="OK")
        assert action_low == "GO"
        assert abs(size_low - 0.6) < 0.01

        # High R
        state_high = {"R": 0.9}
        action_high, size_high = policy.decide(state_high, ews_state="EMERGENT", risk_state="OK")
        assert action_high == "GO"
        assert abs(size_high - 0.95) < 0.01
        assert size_high > size_low

    def test_hold_on_caution(self):
        """Test HOLD action when CAUTION."""
        policy = BasalGangliaPolicy()
        state = {"R": 0.6}

        action, size_hint = policy.decide(state, ews_state="CAUTION", risk_state="OK")

        assert action == "HOLD"
        assert size_hint == 0.2
