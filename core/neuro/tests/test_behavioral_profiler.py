"""Tests for SerotoninController behavioral profiler."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

# Direct import to avoid dependency issues in tests
spec = importlib.util.spec_from_file_location(
    "serotonin_controller",
    Path(__file__).parent.parent / "serotonin" / "serotonin_controller.py",
)
serotonin_module = importlib.util.module_from_spec(spec)
sys.modules["serotonin_controller"] = serotonin_module
spec.loader.exec_module(serotonin_module)

SerotoninController = serotonin_module.SerotoninController

# Import profiler
profiler_spec = importlib.util.spec_from_file_location(
    "behavioral_profiler",
    Path(__file__).parent.parent / "serotonin" / "profiler" / "behavioral_profiler.py",
)
profiler_module = importlib.util.module_from_spec(profiler_spec)
sys.modules["behavioral_profiler"] = profiler_module
profiler_spec.loader.exec_module(profiler_module)

SerotoninProfiler = profiler_module.SerotoninProfiler
BehavioralProfile = profiler_module.BehavioralProfile

pytestmark = pytest.mark.L1


V24_CONFIG = {
    "alpha": 0.42,
    "beta": 0.28,
    "gamma": 0.32,
    "delta_rho": 0.18,
    "k": 1.0,
    "theta": 0.5,
    "delta": 0.8,
    "za_bias": -0.33,
    "decay_rate": 0.05,
    "cooldown_threshold": 0.7,
    "desens_threshold_ticks": 100,
    "desens_rate": 0.01,
    "target_dd": -0.05,
    "target_sharpe": 1.0,
    "beta_temper": 0.12,
    "max_desens_counter": 1000,
    "phase_threshold": 0.4,
    "burst_factor": 2.5,
    "mod_t_max": 4.0,
    "mod_t_half": 24.0,
    "mod_k": 0.7,
    "tick_hours": 1.0,
    "phase_kappa": 0.08,
    "desens_gain": 0.12,
    "gate_veto": 0.9,
    "phasic_veto": 1.0,
    "temperature_floor_min": 0.05,
    "temperature_floor_max": 0.4,
}

ACTIVE_PROFILE_V24 = "v24"

WRAPPED_V24_CONFIG = {"active_profile": ACTIVE_PROFILE_V24, "serotonin_v24": V24_CONFIG}


@pytest.fixture
def controller(tmp_path):
    """Create a controller for testing."""
    import yaml

    config = WRAPPED_V24_CONFIG
    cfg_path = tmp_path / "serotonin.yaml"
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, sort_keys=True)

    return SerotoninController(str(cfg_path))


@pytest.fixture
def profiler(controller):
    """Create a profiler for testing."""
    return SerotoninProfiler(controller)


def test_profiler_initialization(profiler):
    """Test profiler initializes correctly."""
    assert profiler.controller is not None
    assert profiler._history == []
    assert profiler._veto_events == []
    assert profiler._cooldown_events == []


def test_serotonin_config_schema_validation(tmp_path):
    """Ensure wrapped serotonin config schema is enforced."""
    import yaml

    cfg_path = tmp_path / "serotonin_valid.yaml"
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(WRAPPED_V24_CONFIG, f, sort_keys=True)

    controller = SerotoninController(str(cfg_path))
    assert controller._active_profile == "v24"

    bad_cfg = {**WRAPPED_V24_CONFIG, "invalid_root_key": 1}
    bad_path = tmp_path / "serotonin_invalid.yaml"
    with open(bad_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(bad_cfg, f, sort_keys=True)

    with pytest.raises(ValueError, match="Unknown root keys"):
        SerotoninController(str(bad_path))


def test_profiler_reset_history(profiler):
    """Test profiler history reset."""
    # Add some data
    profiler._record_step(1.0, -0.02, 0.5)
    profiler._record_step(1.5, -0.03, 0.6)

    assert len(profiler._history) > 0

    profiler.reset_history()

    assert profiler._history == []
    assert profiler._veto_events == []
    assert profiler._cooldown_events == []


def test_profile_stress_response(profiler):
    """Test profiling stress response across levels."""
    stress_levels = [0.5, 1.0, 1.5, 2.0, 2.5]

    profile = profiler.profile_stress_response(
        stress_levels=stress_levels, steps_per_level=20
    )

    assert profile is not None
    assert profile.statistics.total_steps == len(stress_levels) * 20
    assert profile.tonic_phasic.tonic_baseline >= 0
    assert profile.tonic_phasic.tonic_peak > profile.tonic_phasic.tonic_baseline
    assert (
        profile.veto_cooldown.veto_threshold
        == profiler.controller.config["cooldown_threshold"]
    )


def test_profile_stress_ramp(profiler):
    """Test profiling with ramping stress."""
    profile = profiler.profile_stress_ramp(
        stress_min=0.0, stress_max=3.0, total_steps=200
    )

    assert profile is not None
    assert profile.statistics.total_steps == 200
    assert profile.statistics.stress_mean > 0
    assert profile.statistics.stress_max >= 2.9


def test_profile_stress_pulse(profiler):
    """Test profiling with stress pulses."""
    profile = profiler.profile_stress_pulse(
        baseline_stress=0.5,
        pulse_stress=2.5,
        pulse_duration=30,
        recovery_duration=70,
        num_pulses=3,
    )

    assert profile is not None
    assert profile.statistics.total_steps == (30 + 70) * 3
    # Should see veto activations during pulses
    assert profile.statistics.total_vetos > 0


def test_tonic_phasic_characteristics(profiler):
    """Test tonic/phasic characteristics are computed."""
    profile = profiler.profile_stress_ramp(total_steps=100)

    tp = profile.tonic_phasic

    assert tp.tonic_baseline >= 0
    assert tp.tonic_peak >= tp.tonic_baseline
    assert tp.tonic_rise_time >= 0
    assert tp.tonic_decay_time >= 0
    assert tp.phasic_activation_threshold > 0
    assert tp.phasic_peak_amplitude >= 0
    assert tp.phasic_burst_frequency >= 0
    assert tp.sensitivity_floor > 0
    assert tp.sensitivity_recovery_rate > 0


def test_veto_cooldown_characteristics(profiler):
    """Test veto/cooldown characteristics are computed."""
    profile = profiler.profile_stress_pulse(
        pulse_stress=3.0, pulse_duration=50, recovery_duration=50, num_pulses=2
    )

    vc = profile.veto_cooldown

    assert vc.veto_threshold > 0
    assert vc.veto_activation_latency >= 0
    assert vc.veto_deactivation_latency >= 0
    assert vc.cooldown_frequency >= 0
    # Should see cooldowns
    if profile.statistics.total_vetos > 0:
        assert vc.cooldown_mean_duration >= 0


def test_profile_statistics(profiler):
    """Test profile statistics are computed correctly."""
    stress_levels = [1.0, 2.0, 3.0]
    profile = profiler.profile_stress_response(
        stress_levels=stress_levels, steps_per_level=50
    )

    stats = profile.statistics

    assert stats.total_steps == 150
    assert stats.total_vetos >= 0
    assert 0 <= stats.veto_rate <= 1
    assert stats.stress_mean > 0
    assert stats.stress_std >= 0
    assert stats.stress_max > 0
    assert stats.serotonin_mean >= 0
    assert stats.serotonin_std >= 0
    assert stats.tonic_mean >= 0
    assert stats.phasic_mean >= 0
    assert stats.gate_mean >= 0


def test_profile_save_and_load(profiler, tmp_path):
    """Test saving and loading profiles."""
    profile = profiler.profile_stress_response(
        stress_levels=[0.5, 1.5, 2.5], steps_per_level=20
    )

    profile_path = tmp_path / "test_profile.json"
    profile.save(str(profile_path))

    assert profile_path.exists()

    # Load and verify
    loaded_profile = BehavioralProfile.load(str(profile_path))

    assert loaded_profile.statistics.total_steps == profile.statistics.total_steps
    assert (
        loaded_profile.tonic_phasic.tonic_baseline
        == profile.tonic_phasic.tonic_baseline
    )
    assert (
        loaded_profile.veto_cooldown.veto_threshold
        == profile.veto_cooldown.veto_threshold
    )


def test_profile_to_dict(profiler):
    """Test profile serialization to dict."""
    profile = profiler.profile_stress_ramp(total_steps=100)

    profile_dict = profile.to_dict()

    assert "tonic_phasic" in profile_dict
    assert "veto_cooldown" in profile_dict
    assert "statistics" in profile_dict
    assert "config_snapshot" in profile_dict
    assert "timestamp" in profile_dict

    # Verify JSON serializable
    json_str = json.dumps(profile_dict)
    assert len(json_str) > 0


def test_profile_generate_report(profiler):
    """Test profile report generation."""
    profile = profiler.profile_stress_response(
        stress_levels=[1.0, 2.0], steps_per_level=30
    )

    report = profile.generate_report()

    assert "SEROTONIN CONTROLLER BEHAVIORAL PROFILE" in report
    assert "TONIC/PHASIC CHARACTERISTICS" in report
    assert "VETO/COOLDOWN CHARACTERISTICS" in report
    assert "STATISTICAL SUMMARY" in report
    assert "Tonic Baseline:" in report
    assert "Veto Threshold:" in report


def test_profiler_records_veto_events(profiler):
    """Test profiler records veto events correctly."""
    # Run high stress to trigger vetos
    for _ in range(100):
        profiler._record_step(3.0, -0.1, 2.0)

    # Check veto events were recorded
    assert len(profiler._veto_events) > 0


def test_profiler_tracks_cooldown_duration(profiler):
    """Test profiler tracks cooldown durations."""
    # Trigger cooldown
    for _ in range(50):
        profiler._record_step(3.0, -0.1, 2.0)

    # Exit cooldown
    for _ in range(100):
        profiler._record_step(0.1, -0.01, 0.1)

    # Check cooldown events tracked
    cooldown_durations = [
        e.get("max_duration", 0)
        for e in profiler._cooldown_events
        if "max_duration" in e
    ]
    if cooldown_durations:
        assert max(cooldown_durations) > 0


def test_profile_detects_desensitization(profiler):
    """Test profile detects sensitivity reduction."""
    # Sustained high stress should trigger desensitization
    profile = profiler.profile_stress_ramp(
        stress_min=2.5, stress_max=3.0, total_steps=300
    )

    # Sensitivity floor should be lower than 1.0
    assert profile.tonic_phasic.sensitivity_floor < 1.0


def test_profile_multiple_pulses(profiler):
    """Test profiling multiple stress pulses."""
    profile = profiler.profile_stress_pulse(
        baseline_stress=0.3,
        pulse_stress=2.8,
        pulse_duration=40,
        recovery_duration=60,
        num_pulses=5,
    )

    # Should see multiple veto events
    assert profile.statistics.total_vetos > 0
    # Cooldown frequency should be meaningful
    assert profile.veto_cooldown.cooldown_frequency > 0


def test_estimate_rise_time(profiler):
    """Test rise time estimation."""
    signal = np.array([0.0, 0.2, 0.4, 0.6, 0.8, 0.9, 0.95, 1.0])
    rise_time = profiler._estimate_rise_time(signal, threshold=0.63)

    assert rise_time > 0
    assert rise_time < len(signal)


def test_estimate_decay_time(profiler):
    """Test decay time estimation."""
    signal = np.array([0.0, 0.5, 1.0, 0.8, 0.5, 0.3, 0.1, 0.0])
    decay_time = profiler._estimate_decay_time(signal, threshold=0.37)

    assert decay_time >= 0


def test_count_peaks(profiler):
    """Test peak counting."""
    # Signal with 3 peaks
    signal = np.array([0, 0.5, 0.2, 0.6, 0.1, 0.7, 0.3, 0])
    peaks = profiler._count_peaks(signal, prominence=0.1)

    assert peaks > 0


def test_profile_with_zero_stress(profiler):
    """Test profiling with zero stress."""
    profile = profiler.profile_stress_response(stress_levels=[0.0], steps_per_level=50)

    # Should have minimal activity
    assert profile.statistics.stress_mean < 0.1
    assert profile.tonic_phasic.tonic_baseline < 0.5


def test_profile_consistency(profiler):
    """Test profile consistency across runs."""
    profiler.controller.reset()
    profile1 = profiler.profile_stress_response([1.0, 2.0], steps_per_level=30)

    profiler.controller.reset()
    profile2 = profiler.profile_stress_response([1.0, 2.0], steps_per_level=30)

    # Should get similar results
    assert (
        abs(profile1.statistics.serotonin_mean - profile2.statistics.serotonin_mean)
        < 0.1
    )
    assert (
        abs(profile1.tonic_phasic.tonic_baseline - profile2.tonic_phasic.tonic_baseline)
        < 0.1
    )


def test_profile_config_snapshot(profiler):
    """Test profile includes config snapshot."""
    profile = profiler.profile_stress_ramp(total_steps=50)

    assert profile.config_snapshot is not None
    assert "alpha" in profile.config_snapshot
    assert "cooldown_threshold" in profile.config_snapshot


def test_profiler_empty_history_error(profiler):
    """Test profiler raises error with empty history."""
    with pytest.raises(ValueError):
        profiler._analyze_and_build_profile()
