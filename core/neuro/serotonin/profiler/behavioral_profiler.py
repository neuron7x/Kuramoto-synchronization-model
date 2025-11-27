"""Behavioral profiler for comprehensive characterization of SerotoninController.

This module provides tools to profile and analyze the tonic/phasic dynamics,
veto/cooldown patterns, and overall behavior of the serotonin controller under
various stress scenarios.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import numpy as np


@dataclass
class TonicPhasicCharacteristics:
    """Characterization of tonic and phasic serotonin dynamics."""

    tonic_baseline: float  # Average tonic level under low stress
    tonic_peak: float  # Maximum tonic level observed
    tonic_rise_time: float  # Time to reach 63% of peak (tau equivalent)
    tonic_decay_time: float  # Time to decay to 37% after stress removal

    phasic_activation_threshold: float  # Stress level triggering phasic bursts
    phasic_peak_amplitude: float  # Maximum phasic component magnitude
    phasic_burst_frequency: float  # Bursts per unit time
    phasic_gate_transition_width: float  # Smoothness of gate sigmoid

    sensitivity_floor: float  # Minimum sensitivity after desensitization
    sensitivity_recovery_rate: float  # Recovery rate per step
    desensitization_onset_time: float  # Steps to trigger desensitization

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "tonic_baseline": float(self.tonic_baseline),
            "tonic_peak": float(self.tonic_peak),
            "tonic_rise_time": float(self.tonic_rise_time),
            "tonic_decay_time": float(self.tonic_decay_time),
            "phasic_activation_threshold": float(self.phasic_activation_threshold),
            "phasic_peak_amplitude": float(self.phasic_peak_amplitude),
            "phasic_burst_frequency": float(self.phasic_burst_frequency),
            "phasic_gate_transition_width": float(self.phasic_gate_transition_width),
            "sensitivity_floor": float(self.sensitivity_floor),
            "sensitivity_recovery_rate": float(self.sensitivity_recovery_rate),
            "desensitization_onset_time": float(self.desensitization_onset_time),
        }


@dataclass
class VetoCooldownCharacteristics:
    """Characterization of veto/cooldown behavior."""

    veto_threshold: float  # Serotonin level triggering veto
    veto_activation_latency: float  # Steps to activate veto
    veto_deactivation_latency: float  # Steps to deactivate veto

    cooldown_mean_duration: float  # Average cooldown duration
    cooldown_max_duration: float  # Maximum cooldown observed
    cooldown_frequency: float  # Cooldown events per 100 steps

    hysteresis_width: float  # Difference between activation/deactivation levels
    recovery_threshold: float  # Level at which cooldown exits

    gate_veto_contribution: float  # Percentage of vetoes from gate level
    phasic_veto_contribution: float  # Percentage of vetoes from phasic level
    tonic_veto_contribution: float  # Percentage of vetoes from tonic level

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "veto_threshold": float(self.veto_threshold),
            "veto_activation_latency": float(self.veto_activation_latency),
            "veto_deactivation_latency": float(self.veto_deactivation_latency),
            "cooldown_mean_duration": float(self.cooldown_mean_duration),
            "cooldown_max_duration": float(self.cooldown_max_duration),
            "cooldown_frequency": float(self.cooldown_frequency),
            "hysteresis_width": float(self.hysteresis_width),
            "recovery_threshold": float(self.recovery_threshold),
            "gate_veto_contribution": float(self.gate_veto_contribution),
            "phasic_veto_contribution": float(self.phasic_veto_contribution),
            "tonic_veto_contribution": float(self.tonic_veto_contribution),
        }


@dataclass
class ProfileStatistics:
    """Statistical summary of profiling run."""

    total_steps: int
    total_vetos: int
    veto_rate: float

    stress_mean: float
    stress_std: float
    stress_max: float

    serotonin_mean: float
    serotonin_std: float
    serotonin_max: float

    tonic_mean: float
    phasic_mean: float
    gate_mean: float

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "total_steps": int(self.total_steps),
            "total_vetos": int(self.total_vetos),
            "veto_rate": float(self.veto_rate),
            "stress_mean": float(self.stress_mean),
            "stress_std": float(self.stress_std),
            "stress_max": float(self.stress_max),
            "serotonin_mean": float(self.serotonin_mean),
            "serotonin_std": float(self.serotonin_std),
            "serotonin_max": float(self.serotonin_max),
            "tonic_mean": float(self.tonic_mean),
            "phasic_mean": float(self.phasic_mean),
            "gate_mean": float(self.gate_mean),
        }


@dataclass
class BehavioralProfile:
    """Complete behavioral characterization of SerotoninController."""

    tonic_phasic: TonicPhasicCharacteristics
    veto_cooldown: VetoCooldownCharacteristics
    statistics: ProfileStatistics
    config_snapshot: dict
    timestamp: float

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "tonic_phasic": self.tonic_phasic.to_dict(),
            "veto_cooldown": self.veto_cooldown.to_dict(),
            "statistics": self.statistics.to_dict(),
            "config_snapshot": self.config_snapshot,
            "timestamp": float(self.timestamp),
        }

    def save(self, path: str) -> None:
        """Save profile to JSON file."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, sort_keys=True)
        logging.getLogger(__name__).info("Saved behavioral profile to %s", path)

    @classmethod
    def load(cls, path: str) -> BehavioralProfile:
        """Load profile from JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        tonic_phasic = TonicPhasicCharacteristics(**data["tonic_phasic"])
        veto_cooldown = VetoCooldownCharacteristics(**data["veto_cooldown"])
        statistics = ProfileStatistics(**data["statistics"])

        return cls(
            tonic_phasic=tonic_phasic,
            veto_cooldown=veto_cooldown,
            statistics=statistics,
            config_snapshot=data["config_snapshot"],
            timestamp=data["timestamp"],
        )

    def generate_report(self) -> str:
        """Generate a formatted report of the behavioral profile."""
        lines = [
            "=" * 80,
            "SEROTONIN CONTROLLER BEHAVIORAL PROFILE",
            "=" * 80,
            "",
            "TONIC/PHASIC CHARACTERISTICS",
            "-" * 80,
            f"  Tonic Baseline:               {self.tonic_phasic.tonic_baseline:.4f}",
            f"  Tonic Peak:                   {self.tonic_phasic.tonic_peak:.4f}",
            f"  Tonic Rise Time:              {self.tonic_phasic.tonic_rise_time:.2f} steps",
            f"  Tonic Decay Time:             {self.tonic_phasic.tonic_decay_time:.2f} steps",
            "",
            f"  Phasic Activation Threshold:  {self.tonic_phasic.phasic_activation_threshold:.4f}",
            f"  Phasic Peak Amplitude:        {self.tonic_phasic.phasic_peak_amplitude:.4f}",
            f"  Phasic Burst Frequency:       {self.tonic_phasic.phasic_burst_frequency:.4f} bursts/step",
            f"  Gate Transition Width:        {self.tonic_phasic.phasic_gate_transition_width:.4f}",
            "",
            f"  Sensitivity Floor:            {self.tonic_phasic.sensitivity_floor:.4f}",
            f"  Sensitivity Recovery Rate:    {self.tonic_phasic.sensitivity_recovery_rate:.6f}",
            f"  Desensitization Onset:        {self.tonic_phasic.desensitization_onset_time:.0f} steps",
            "",
            "VETO/COOLDOWN CHARACTERISTICS",
            "-" * 80,
            f"  Veto Threshold:               {self.veto_cooldown.veto_threshold:.4f}",
            f"  Veto Activation Latency:      {self.veto_cooldown.veto_activation_latency:.2f} steps",
            f"  Veto Deactivation Latency:    {self.veto_cooldown.veto_deactivation_latency:.2f} steps",
            "",
            f"  Cooldown Mean Duration:       {self.veto_cooldown.cooldown_mean_duration:.2f} s",
            f"  Cooldown Max Duration:        {self.veto_cooldown.cooldown_max_duration:.2f} s",
            f"  Cooldown Frequency:           {self.veto_cooldown.cooldown_frequency:.2f} per 100 steps",
            "",
            f"  Hysteresis Width:             {self.veto_cooldown.hysteresis_width:.4f}",
            f"  Recovery Threshold:           {self.veto_cooldown.recovery_threshold:.4f}",
            "",
            "  Veto Contributions:",
            f"    Gate Level:                 {self.veto_cooldown.gate_veto_contribution:.1f}%",
            f"    Phasic Level:               {self.veto_cooldown.phasic_veto_contribution:.1f}%",
            f"    Tonic Level:                {self.veto_cooldown.tonic_veto_contribution:.1f}%",
            "",
            "STATISTICAL SUMMARY",
            "-" * 80,
            f"  Total Steps:                  {self.statistics.total_steps}",
            f"  Total Vetoes:                 {self.statistics.total_vetos}",
            f"  Veto Rate:                    {self.statistics.veto_rate:.2%}",
            "",
            f"  Stress Mean ± Std:            {self.statistics.stress_mean:.3f} "
            f"± {self.statistics.stress_std:.3f}",
            f"  Stress Max:                   {self.statistics.stress_max:.3f}",
            "",
            f"  Serotonin Mean ± Std:         {self.statistics.serotonin_mean:.3f} "
            f"± {self.statistics.serotonin_std:.3f}",
            f"  Serotonin Max:                {self.statistics.serotonin_max:.3f}",
            "",
            f"  Tonic Mean:                   {self.statistics.tonic_mean:.3f}",
            f"  Phasic Mean:                  {self.statistics.phasic_mean:.3f}",
            f"  Gate Mean:                    {self.statistics.gate_mean:.3f}",
            "",
            "=" * 80,
        ]
        return "\n".join(lines)


class SerotoninProfiler:
    """Profiler for comprehensive behavioral characterization of SerotoninController."""

    def __init__(self, controller):
        """Initialize profiler with a controller instance.

        Args:
            controller: SerotoninController instance to profile.
        """
        self.controller = controller
        self._history: List[dict] = []
        self._veto_events: List[dict] = []
        self._cooldown_events: List[dict] = []

    def reset_history(self) -> None:
        """Clear profiling history."""
        self._history = []
        self._veto_events = []
        self._cooldown_events = []

    def profile_stress_response(
        self,
        stress_levels: List[float],
        drawdown: float = -0.03,
        novelty: float = 0.5,
        steps_per_level: int = 50,
    ) -> BehavioralProfile:
        """Profile controller response to varying stress levels.

        Args:
            stress_levels: List of stress levels to test.
            drawdown: Constant drawdown to use.
            novelty: Constant novelty to use.
            steps_per_level: Number of steps at each stress level.

        Returns:
            Complete behavioral profile.
        """
        self.controller.reset()
        self.reset_history()

        for stress in stress_levels:
            for _ in range(steps_per_level):
                self._record_step(stress, drawdown, novelty)

        return self._analyze_and_build_profile()

    def profile_stress_ramp(
        self,
        stress_min: float = 0.0,
        stress_max: float = 3.0,
        total_steps: int = 500,
        drawdown: float = -0.03,
        novelty: float = 0.5,
    ) -> BehavioralProfile:
        """Profile controller response to ramping stress.

        Args:
            stress_min: Initial stress level.
            stress_max: Final stress level.
            total_steps: Total profiling steps.
            drawdown: Constant drawdown to use.
            novelty: Constant novelty to use.

        Returns:
            Complete behavioral profile.
        """
        self.controller.reset()
        self.reset_history()

        for i in range(total_steps):
            t = i / total_steps
            stress = stress_min + (stress_max - stress_min) * t
            self._record_step(stress, drawdown, novelty)

        return self._analyze_and_build_profile()

    def profile_stress_pulse(
        self,
        baseline_stress: float = 0.5,
        pulse_stress: float = 2.5,
        pulse_duration: int = 100,
        recovery_duration: int = 200,
        num_pulses: int = 3,
        drawdown: float = -0.03,
        novelty: float = 0.5,
    ) -> BehavioralProfile:
        """Profile controller response to stress pulses.

        Args:
            baseline_stress: Baseline stress level.
            pulse_stress: Stress level during pulses.
            pulse_duration: Duration of each pulse in steps.
            recovery_duration: Duration between pulses in steps.
            num_pulses: Number of pulses to generate.
            drawdown: Constant drawdown to use.
            novelty: Constant novelty to use.

        Returns:
            Complete behavioral profile.
        """
        self.controller.reset()
        self.reset_history()

        for _ in range(num_pulses):
            # Pulse
            for _ in range(pulse_duration):
                self._record_step(pulse_stress, drawdown, novelty)
            # Recovery
            for _ in range(recovery_duration):
                self._record_step(baseline_stress, drawdown, novelty)

        return self._analyze_and_build_profile()

    def _record_step(self, stress: float, drawdown: float, novelty: float) -> None:
        """Record a single profiling step."""
        hold, veto, cooldown_s, level = self.controller.step(stress, drawdown, novelty)

        record = {
            "stress": stress,
            "drawdown": drawdown,
            "novelty": novelty,
            "hold": hold,
            "veto": veto,
            "cooldown_s": cooldown_s,
            "level": level,
            "tonic": self.controller.tonic_level,
            "phasic": self.controller.phasic_level,
            "gate": self.controller.gate_level,
            "sensitivity": self.controller.sensitivity,
        }

        self._history.append(record)

        # Track veto events
        if veto and (
            not self._veto_events or not self._veto_events[-1].get("active", False)
        ):
            self._veto_events.append(
                {
                    "start_step": len(self._history) - 1,
                    "start_level": level,
                    "active": True,
                }
            )
        elif (
            not veto
            and self._veto_events
            and self._veto_events[-1].get("active", False)
        ):
            self._veto_events[-1]["end_step"] = len(self._history) - 1
            self._veto_events[-1]["end_level"] = level
            self._veto_events[-1]["active"] = False
            self._veto_events[-1]["duration"] = (
                self._veto_events[-1]["end_step"] - self._veto_events[-1]["start_step"]
            )

        # Track cooldown events
        if cooldown_s > 0:
            if (
                not self._cooldown_events
                or self._cooldown_events[-1].get("max_duration", 0) < cooldown_s
            ):
                if (
                    self._cooldown_events
                    and "max_duration" not in self._cooldown_events[-1]
                ):
                    self._cooldown_events[-1]["max_duration"] = cooldown_s
                elif not self._cooldown_events:
                    self._cooldown_events.append({"max_duration": cooldown_s})
        elif self._cooldown_events and "max_duration" in self._cooldown_events[-1]:
            # Cooldown ended, start tracking next one
            self._cooldown_events.append({})

    def _analyze_and_build_profile(self) -> BehavioralProfile:
        """Analyze collected history and build behavioral profile."""
        import time

        if not self._history:
            raise ValueError("No profiling data collected")

        # Extract time series
        stress_series = np.array([r["stress"] for r in self._history])
        level_series = np.array([r["level"] for r in self._history])
        tonic_series = np.array([r["tonic"] for r in self._history])
        phasic_series = np.array([r["phasic"] for r in self._history])
        gate_series = np.array([r["gate"] for r in self._history])
        sensitivity_series = np.array([r["sensitivity"] for r in self._history])
        veto_series = np.array([r["veto"] for r in self._history])

        # Analyze tonic/phasic characteristics
        tonic_phasic = self._analyze_tonic_phasic(
            stress_series, tonic_series, phasic_series, gate_series, sensitivity_series
        )

        # Analyze veto/cooldown characteristics
        veto_cooldown = self._analyze_veto_cooldown(
            level_series, tonic_series, phasic_series, gate_series, veto_series
        )

        # Compute statistics
        statistics = ProfileStatistics(
            total_steps=len(self._history),
            total_vetos=int(np.sum(veto_series)),
            veto_rate=float(np.mean(veto_series)),
            stress_mean=float(np.mean(stress_series)),
            stress_std=float(np.std(stress_series)),
            stress_max=float(np.max(stress_series)),
            serotonin_mean=float(np.mean(level_series)),
            serotonin_std=float(np.std(level_series)),
            serotonin_max=float(np.max(level_series)),
            tonic_mean=float(np.mean(tonic_series)),
            phasic_mean=float(np.mean(phasic_series)),
            gate_mean=float(np.mean(gate_series)),
        )

        return BehavioralProfile(
            tonic_phasic=tonic_phasic,
            veto_cooldown=veto_cooldown,
            statistics=statistics,
            config_snapshot=self.controller.config.copy(),
            timestamp=time.time(),
        )

    def _analyze_tonic_phasic(
        self,
        stress: np.ndarray,
        tonic: np.ndarray,
        phasic: np.ndarray,
        gate: np.ndarray,
        sensitivity: np.ndarray,
    ) -> TonicPhasicCharacteristics:
        """Analyze tonic/phasic dynamics."""

        # Tonic baseline (average under low stress)
        low_stress_mask = stress < 0.5
        tonic_baseline = (
            float(np.mean(tonic[low_stress_mask])) if np.any(low_stress_mask) else 0.0
        )
        tonic_peak = float(np.max(tonic))

        # Tonic rise time (find first pulse and measure)
        rise_time = self._estimate_rise_time(tonic, threshold=0.63)
        decay_time = self._estimate_decay_time(tonic, threshold=0.37)

        # Phasic characteristics
        phasic_activation_threshold = self.controller.config["phase_threshold"]
        phasic_peak = float(np.max(phasic))

        # Estimate burst frequency (count peaks)
        phasic_bursts = self._count_peaks(phasic, prominence=0.1)
        phasic_burst_frequency = phasic_bursts / len(phasic) if len(phasic) > 0 else 0.0
        phasic_gate_width = self.controller.config["phase_kappa"]

        # Sensitivity characteristics
        sensitivity_floor = float(np.min(sensitivity))
        sensitivity_recovery_rate = self.controller.config["desens_rate"]
        desensitization_onset = self.controller.config["desens_threshold_ticks"]

        return TonicPhasicCharacteristics(
            tonic_baseline=tonic_baseline,
            tonic_peak=tonic_peak,
            tonic_rise_time=rise_time,
            tonic_decay_time=decay_time,
            phasic_activation_threshold=phasic_activation_threshold,
            phasic_peak_amplitude=phasic_peak,
            phasic_burst_frequency=phasic_burst_frequency,
            phasic_gate_transition_width=phasic_gate_width,
            sensitivity_floor=sensitivity_floor,
            sensitivity_recovery_rate=sensitivity_recovery_rate,
            desensitization_onset_time=desensitization_onset,
        )

    def _analyze_veto_cooldown(
        self,
        level: np.ndarray,
        tonic: np.ndarray,
        phasic: np.ndarray,
        gate: np.ndarray,
        veto: np.ndarray,
    ) -> VetoCooldownCharacteristics:
        """Analyze veto/cooldown behavior."""

        veto_threshold = self.controller.config["cooldown_threshold"]

        # Find veto transitions
        veto_activations = np.where(np.diff(veto.astype(int)) > 0)[0]
        veto_deactivations = np.where(np.diff(veto.astype(int)) < 0)[0]

        veto_activation_latency = 0.0
        veto_deactivation_latency = 0.0
        hysteresis_width = 0.0
        recovery_threshold = 0.0

        if len(veto_activations) > 0:
            # Measure latency to activation
            activation_levels = level[veto_activations]
            veto_activation_latency = float(np.mean(veto_activations))

        if len(veto_deactivations) > 0:
            # Measure latency to deactivation
            deactivation_levels = level[veto_deactivations]
            veto_deactivation_latency = float(np.mean(len(level) - veto_deactivations))
            recovery_threshold = float(np.mean(deactivation_levels))

            if len(veto_activations) > 0:
                hysteresis_width = float(
                    np.mean(activation_levels) - recovery_threshold
                )

        # Cooldown statistics
        cooldown_durations = [
            e.get("max_duration", 0)
            for e in self._cooldown_events
            if "max_duration" in e
        ]
        cooldown_mean = (
            float(np.mean(cooldown_durations)) if cooldown_durations else 0.0
        )
        cooldown_max = float(np.max(cooldown_durations)) if cooldown_durations else 0.0
        cooldown_frequency = (
            len(cooldown_durations) / len(veto) * 100 if len(veto) > 0 else 0.0
        )

        # Analyze veto contributions
        gate_veto = (
            float(np.mean(gate[veto > 0] > self.controller.config["gate_veto"]) * 100)
            if np.any(veto)
            else 0.0
        )
        phasic_veto = (
            float(
                np.mean(phasic[veto > 0] > self.controller.config["phasic_veto"]) * 100
            )
            if np.any(veto)
            else 0.0
        )
        tonic_veto = (
            float(np.mean(level[veto > 0] > veto_threshold) * 100)
            if np.any(veto)
            else 0.0
        )

        return VetoCooldownCharacteristics(
            veto_threshold=veto_threshold,
            veto_activation_latency=veto_activation_latency,
            veto_deactivation_latency=veto_deactivation_latency,
            cooldown_mean_duration=cooldown_mean,
            cooldown_max_duration=cooldown_max,
            cooldown_frequency=cooldown_frequency,
            hysteresis_width=hysteresis_width,
            recovery_threshold=recovery_threshold,
            gate_veto_contribution=gate_veto,
            phasic_veto_contribution=phasic_veto,
            tonic_veto_contribution=tonic_veto,
        )

    def _estimate_rise_time(self, signal: np.ndarray, threshold: float = 0.63) -> float:
        """Estimate rise time to threshold of peak."""
        if len(signal) < 2:
            return 0.0

        peak = np.max(signal)
        target = peak * threshold

        # Find first crossing
        crossings = np.where(signal >= target)[0]
        if len(crossings) > 0:
            return float(crossings[0])
        return 0.0

    def _estimate_decay_time(
        self, signal: np.ndarray, threshold: float = 0.37
    ) -> float:
        """Estimate decay time from peak to threshold."""
        if len(signal) < 2:
            return 0.0

        peak_idx = np.argmax(signal)
        if peak_idx >= len(signal) - 1:
            return 0.0

        peak = signal[peak_idx]
        target = peak * threshold

        # Find first crossing after peak
        after_peak = signal[peak_idx:]
        crossings = np.where(after_peak <= target)[0]
        if len(crossings) > 0:
            return float(crossings[0])
        return 0.0

    def _count_peaks(self, signal: np.ndarray, prominence: float = 0.1) -> int:
        """Count number of peaks in signal."""
        if len(signal) < 3:
            return 0

        # Simple peak counting
        peaks = 0
        for i in range(1, len(signal) - 1):
            if signal[i] > signal[i - 1] and signal[i] > signal[i + 1]:
                if signal[i] - min(signal[i - 1], signal[i + 1]) >= prominence:
                    peaks += 1
        return peaks

    def plot_profile(
        self, profile: BehavioralProfile, output_path: Optional[str] = None
    ) -> None:
        """Generate visualization plots of the behavioral profile.

        Args:
            profile: Behavioral profile to visualize.
            output_path: Optional path to save plots. If None, displays plots.
        """
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            logging.getLogger(__name__).warning(
                "matplotlib not available, skipping plots"
            )
            return

        if not self._history:
            logging.getLogger(__name__).warning(
                "No history data available for plotting"
            )
            return

        fig, axes = plt.subplots(4, 1, figsize=(12, 10))
        fig.suptitle(
            "Serotonin Controller Behavioral Profile", fontsize=14, fontweight="bold"
        )

        steps = np.arange(len(self._history))
        stress = np.array([r["stress"] for r in self._history])
        level = np.array([r["level"] for r in self._history])
        tonic = np.array([r["tonic"] for r in self._history])
        phasic = np.array([r["phasic"] for r in self._history])
        gate = np.array([r["gate"] for r in self._history])
        veto = np.array([r["veto"] for r in self._history])

        # Plot 1: Stress input
        axes[0].plot(steps, stress, "r-", label="Stress", linewidth=1.5)
        axes[0].set_ylabel("Stress Level")
        axes[0].set_title("Input Stress Pattern")
        axes[0].legend()
        axes[0].grid(True, alpha=0.3)

        # Plot 2: Tonic and phasic components
        axes[1].plot(steps, tonic, "b-", label="Tonic", linewidth=1.5)
        axes[1].plot(steps, phasic, "g-", label="Phasic", linewidth=1.5)
        axes[1].plot(steps, gate, "m--", label="Gate", linewidth=1, alpha=0.7)
        axes[1].axhline(
            y=profile.tonic_phasic.tonic_baseline,
            color="b",
            linestyle=":",
            alpha=0.5,
            label="Tonic Baseline",
        )
        axes[1].set_ylabel("Component Level")
        axes[1].set_title("Tonic/Phasic Dynamics")
        axes[1].legend()
        axes[1].grid(True, alpha=0.3)

        # Plot 3: Serotonin level
        axes[2].plot(steps, level, "k-", label="Serotonin Level", linewidth=1.5)
        axes[2].axhline(
            y=profile.veto_cooldown.veto_threshold,
            color="r",
            linestyle="--",
            label="Veto Threshold",
        )
        axes[2].fill_between(
            steps, 0, level, where=veto, alpha=0.3, color="red", label="HOLD Active"
        )
        axes[2].set_ylabel("Serotonin Level")
        axes[2].set_title("Serotonin Signal and Veto State")
        axes[2].legend()
        axes[2].grid(True, alpha=0.3)

        # Plot 4: Veto events
        axes[3].fill_between(
            steps, 0, 1, where=veto, alpha=0.6, color="red", label="HOLD"
        )
        axes[3].set_ylabel("Veto State")
        axes[3].set_xlabel("Step")
        axes[3].set_title(
            f"Veto/Cooldown Events (Rate: {profile.statistics.veto_rate:.1%})"
        )
        axes[3].set_ylim(-0.1, 1.1)
        axes[3].legend()
        axes[3].grid(True, alpha=0.3)

        plt.tight_layout()

        if output_path:
            plt.savefig(output_path, dpi=150, bbox_inches="tight")
            logging.getLogger(__name__).info("Saved profile plot to %s", output_path)
        else:
            plt.show()
