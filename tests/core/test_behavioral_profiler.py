# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for core.neuro.serotonin.profiler.behavioral_profiler module."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

try:
    from core.neuro.serotonin.profiler.behavioral_profiler import (
        BehavioralProfile,
        ProfileStatistics,
        SerotoninProfiler,
        TonicPhasicCharacteristics,
        VetoCooldownCharacteristics,
    )
except ImportError:
    pytest.skip("behavioral_profiler not importable", allow_module_level=True)


def _sample_tonic_phasic():
    return TonicPhasicCharacteristics(
        tonic_baseline=0.3,
        tonic_peak=0.8,
        tonic_rise_time=10.0,
        tonic_decay_time=20.0,
        phasic_activation_threshold=1.5,
        phasic_peak_amplitude=0.6,
        phasic_burst_frequency=0.02,
        phasic_gate_transition_width=5.0,
        sensitivity_floor=0.4,
        sensitivity_recovery_rate=0.001,
        desensitization_onset_time=100.0,
    )


def _sample_veto_cooldown():
    return VetoCooldownCharacteristics(
        veto_threshold=0.7,
        veto_activation_latency=5.0,
        veto_deactivation_latency=10.0,
        cooldown_mean_duration=3.0,
        cooldown_max_duration=8.0,
        cooldown_frequency=2.5,
        hysteresis_width=0.1,
        recovery_threshold=0.5,
        gate_veto_contribution=40.0,
        phasic_veto_contribution=35.0,
        tonic_veto_contribution=25.0,
    )


def _sample_stats():
    return ProfileStatistics(
        total_steps=500,
        total_vetos=50,
        veto_rate=0.1,
        stress_mean=1.0,
        stress_std=0.5,
        stress_max=3.0,
        serotonin_mean=0.4,
        serotonin_std=0.2,
        serotonin_max=0.9,
        tonic_mean=0.3,
        phasic_mean=0.1,
        gate_mean=0.5,
    )


def _sample_profile():
    return BehavioralProfile(
        tonic_phasic=_sample_tonic_phasic(),
        veto_cooldown=_sample_veto_cooldown(),
        statistics=_sample_stats(),
        config_snapshot={"version": "1.0"},
        timestamp=time.time(),
    )


# ===================================================================
# TonicPhasicCharacteristics
# ===================================================================


class TestTonicPhasicCharacteristics:
    def test_to_dict(self):
        tp = _sample_tonic_phasic()
        d = tp.to_dict()
        assert d["tonic_baseline"] == 0.3
        assert isinstance(d["phasic_burst_frequency"], float)

    def test_all_fields_present(self):
        d = _sample_tonic_phasic().to_dict()
        expected = {
            "tonic_baseline",
            "tonic_peak",
            "tonic_rise_time",
            "tonic_decay_time",
            "phasic_activation_threshold",
            "phasic_peak_amplitude",
            "phasic_burst_frequency",
            "phasic_gate_transition_width",
            "sensitivity_floor",
            "sensitivity_recovery_rate",
            "desensitization_onset_time",
        }
        assert expected == set(d.keys())


# ===================================================================
# VetoCooldownCharacteristics
# ===================================================================


class TestVetoCooldownCharacteristics:
    def test_to_dict(self):
        vc = _sample_veto_cooldown()
        d = vc.to_dict()
        assert d["veto_threshold"] == 0.7
        assert d["gate_veto_contribution"] == 40.0

    def test_field_count(self):
        d = _sample_veto_cooldown().to_dict()
        assert len(d) == 11


# ===================================================================
# ProfileStatistics
# ===================================================================


class TestProfileStatistics:
    def test_to_dict(self):
        s = _sample_stats()
        d = s.to_dict()
        assert d["total_steps"] == 500
        assert d["veto_rate"] == 0.1

    def test_types(self):
        d = _sample_stats().to_dict()
        assert isinstance(d["total_steps"], int)
        assert isinstance(d["veto_rate"], float)


# ===================================================================
# BehavioralProfile
# ===================================================================


class TestBehavioralProfile:
    def test_to_dict(self):
        p = _sample_profile()
        d = p.to_dict()
        assert "tonic_phasic" in d
        assert "veto_cooldown" in d
        assert "statistics" in d
        assert "config_snapshot" in d
        assert "timestamp" in d

    def test_save_and_load(self, tmp_path):
        p = _sample_profile()
        path = str(tmp_path / "profile.json")
        p.save(path)
        loaded = BehavioralProfile.load(path)
        assert loaded.statistics.total_steps == 500
        assert loaded.tonic_phasic.tonic_baseline == pytest.approx(0.3)

    def test_save_creates_parent_dirs(self, tmp_path):
        p = _sample_profile()
        path = str(tmp_path / "deep" / "nested" / "profile.json")
        p.save(path)
        assert Path(path).exists()

    def test_generate_report(self):
        p = _sample_profile()
        report = p.generate_report()
        assert "BEHAVIORAL PROFILE" in report
        assert "Tonic Baseline" in report
        assert "Veto Threshold" in report

    def test_roundtrip_json(self, tmp_path):
        p = _sample_profile()
        d = p.to_dict()
        path = tmp_path / "rt.json"
        with open(path, "w") as f:
            json.dump(d, f)
        with open(path) as f:
            loaded = json.load(f)
        assert loaded["statistics"]["total_steps"] == 500


# ===================================================================
# SerotoninProfiler (with mocked controller)
# ===================================================================


def _make_mock_controller():
    ctrl = MagicMock()
    ctrl.tonic_level = 0.3
    ctrl.phasic_level = 0.1
    ctrl.gate_level = 0.5
    ctrl.sensitivity = 0.9
    ctrl.config = {
        "phase_threshold": 1.5,
        "phase_kappa": 5.0,
        "desens_rate": 0.001,
        "desens_threshold_ticks": 100,
        "cooldown_threshold": 0.7,
        "gate_veto": 0.6,
        "phasic_veto": 0.4,
    }
    ctrl.step.return_value = (0.5, False, 0.0, 0.4)
    ctrl.reset.return_value = None
    return ctrl


class TestSerotoninProfiler:
    def test_reset_history(self):
        ctrl = _make_mock_controller()
        profiler = SerotoninProfiler(ctrl)
        profiler._history = [{"dummy": 1}]
        profiler.reset_history()
        assert profiler._history == []

    def test_profile_stress_response(self):
        ctrl = _make_mock_controller()
        profiler = SerotoninProfiler(ctrl)
        profile = profiler.profile_stress_response(
            stress_levels=[0.5, 1.0, 2.0],
            steps_per_level=10,
        )
        assert isinstance(profile, BehavioralProfile)
        assert profile.statistics.total_steps == 30
        ctrl.reset.assert_called_once()

    def test_profile_stress_ramp(self):
        ctrl = _make_mock_controller()
        profiler = SerotoninProfiler(ctrl)
        profile = profiler.profile_stress_ramp(total_steps=50)
        assert profile.statistics.total_steps == 50

    def test_profile_stress_pulse(self):
        ctrl = _make_mock_controller()
        profiler = SerotoninProfiler(ctrl)
        profile = profiler.profile_stress_pulse(
            num_pulses=2,
            pulse_duration=10,
            recovery_duration=10,
        )
        assert profile.statistics.total_steps == 40

    def test_estimate_rise_time_empty(self):
        ctrl = _make_mock_controller()
        profiler = SerotoninProfiler(ctrl)
        assert profiler._estimate_rise_time(np.array([1.0])) == 0.0

    def test_estimate_decay_time_empty(self):
        ctrl = _make_mock_controller()
        profiler = SerotoninProfiler(ctrl)
        assert profiler._estimate_decay_time(np.array([1.0])) == 0.0

    def test_count_peaks(self):
        ctrl = _make_mock_controller()
        profiler = SerotoninProfiler(ctrl)
        signal = np.array([0, 0.5, 0, 0.8, 0, 0.3, 0])
        assert profiler._count_peaks(signal, prominence=0.1) >= 2

    def test_count_peaks_short(self):
        ctrl = _make_mock_controller()
        profiler = SerotoninProfiler(ctrl)
        assert profiler._count_peaks(np.array([1.0, 2.0])) == 0

    def test_plot_profile_no_matplotlib(self):
        ctrl = _make_mock_controller()
        profiler = SerotoninProfiler(ctrl)
        profile = _sample_profile()
        with patch.dict("sys.modules", {"matplotlib": None, "matplotlib.pyplot": None}):
            profiler.plot_profile(profile)  # should not raise

    def test_record_step_tracks_veto(self):
        ctrl = _make_mock_controller()
        ctrl.step.return_value = (0.5, True, 0.0, 0.8)
        profiler = SerotoninProfiler(ctrl)
        profiler._record_step(2.0, -0.03, 0.5)
        assert len(profiler._history) == 1
        assert profiler._history[0]["veto"] is True
