# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for core.neuro.ecs_regulator module."""

from __future__ import annotations

import pytest

from core.neuro.ecs_regulator import (
    ECSInspiredRegulator,
    ECSMetrics,
    StabilityMetrics,
    StressMode,
)


class TestStressMode:
    def test_values(self):
        assert StressMode.NORMAL.value == "NORMAL"
        assert StressMode.ELEVATED.value == "ELEVATED"
        assert StressMode.CRISIS.value == "CRISIS"

    def test_is_str_enum(self):
        assert isinstance(StressMode.NORMAL, str)


class TestECSMetrics:
    def test_creation(self):
        m = ECSMetrics(
            timestamp=1000,
            stress_level=0.5,
            free_energy_proxy=0.2,
            risk_threshold=0.1,
            compensatory_factor=1.0,
            chronic_counter=0,
            is_chronic=False,
        )
        assert m.timestamp == 1000
        assert m.stress_level == 0.5
        assert m.is_chronic is False


class TestStabilityMetrics:
    def test_creation(self):
        m = StabilityMetrics(
            monotonicity_violations=0,
            gradient_clipping_events=0,
            lyapunov_value=0.1,
            stability_margin=0.5,
            volatility_regime="normal",
            risk_aversion_active=False,
        )
        assert m.lyapunov_value == 0.1
        assert m.risk_aversion_active is False


class TestECSInspiredRegulator:
    def test_default_init(self):
        reg = ECSInspiredRegulator()
        assert reg.risk_threshold == pytest.approx(0.05)
        assert reg.stress_level == 0.0
        assert reg.compensatory_factor == 1.0

    def test_custom_init(self):
        reg = ECSInspiredRegulator(
            initial_risk_threshold=0.1,
            smoothing_alpha=0.8,
            stress_threshold=0.2,
            chronic_threshold=10,
        )
        assert reg.risk_threshold == pytest.approx(0.1)
        assert reg.smoothing_alpha == pytest.approx(0.8)

    def test_invalid_risk_threshold(self):
        with pytest.raises(ValueError, match="initial_risk_threshold"):
            ECSInspiredRegulator(initial_risk_threshold=0.0)

    def test_invalid_risk_threshold_too_high(self):
        with pytest.raises(ValueError, match="initial_risk_threshold"):
            ECSInspiredRegulator(initial_risk_threshold=1.5)

    def test_invalid_smoothing_alpha(self):
        with pytest.raises(ValueError, match="smoothing_alpha"):
            ECSInspiredRegulator(smoothing_alpha=0.0)

    def test_invalid_stress_threshold(self):
        with pytest.raises(ValueError, match="stress_threshold"):
            ECSInspiredRegulator(stress_threshold=-0.1)

    def test_crisis_must_exceed_stress(self):
        with pytest.raises(ValueError, match="crisis_threshold"):
            ECSInspiredRegulator(stress_threshold=0.3, crisis_threshold=0.2)

    def test_invalid_chronic_threshold(self):
        with pytest.raises(ValueError, match="chronic_threshold"):
            ECSInspiredRegulator(chronic_threshold=0)

    def test_invalid_fe_scaling(self):
        with pytest.raises(ValueError, match="fe_scaling"):
            ECSInspiredRegulator(fe_scaling=-1.0)

    def test_invalid_fe_step_up(self):
        with pytest.raises(ValueError, match="max_fe_step_up"):
            ECSInspiredRegulator(max_fe_step_up=-1.0)

    def test_invalid_crisis_action_mode(self):
        with pytest.raises(ValueError, match="crisis_action_mode"):
            ECSInspiredRegulator(crisis_action_mode="invalid_mode")

    def test_valid_crisis_action_modes(self):
        reg1 = ECSInspiredRegulator(crisis_action_mode="hold")
        reg2 = ECSInspiredRegulator(crisis_action_mode="reduce_only")
        assert reg1 is not None
        assert reg2 is not None

    def test_invalid_calibration_window(self):
        with pytest.raises(ValueError, match="calibration_window"):
            ECSInspiredRegulator(calibration_window=0)

    def test_invalid_alpha(self):
        with pytest.raises(ValueError, match="alpha"):
            ECSInspiredRegulator(alpha=1.5)

    def test_alpha_zero_raises(self):
        with pytest.raises(ValueError, match="alpha"):
            ECSInspiredRegulator(alpha=0.0)

    def test_invalid_min_calibration(self):
        with pytest.raises(ValueError, match="min_calibration"):
            ECSInspiredRegulator(min_calibration=-1)

    def test_invalid_stress_multiplier(self):
        with pytest.raises(ValueError, match="multipliers"):
            ECSInspiredRegulator(stress_q_multiplier=0.5)

    def test_action_threshold_deprecation_warning(self):
        with pytest.warns(DeprecationWarning, match="action_threshold"):
            ECSInspiredRegulator(action_threshold=0.1)

    def test_action_threshold_supersedes_risk(self):
        with pytest.warns(DeprecationWarning):
            reg = ECSInspiredRegulator(initial_risk_threshold=0.05, action_threshold=0.2)
        assert reg.risk_threshold == pytest.approx(0.2)

    def test_seed_reproducibility(self):
        reg1 = ECSInspiredRegulator(seed=42)
        reg2 = ECSInspiredRegulator(seed=42)
        assert reg1.risk_threshold == reg2.risk_threshold

    @pytest.mark.parametrize("rt", [0.01, 0.05, 0.1, 0.5, 1.0])
    def test_various_risk_thresholds(self, rt):
        reg = ECSInspiredRegulator(initial_risk_threshold=rt)
        assert reg.risk_threshold == pytest.approx(rt)
