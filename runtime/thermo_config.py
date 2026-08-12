# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Thermodynamics Configuration Module

Centralized configuration for TACL (Thermodynamic Autonomic Control Layer)
including energy thresholds, crisis parameters, and system constants.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

import yaml


@dataclass
class CrisisThresholds:
    """Crisis detection thresholds."""

    # Free energy deviation thresholds (relative to baseline)
    normal_threshold: float = 0.0  # No crisis
    elevated_threshold: float = 0.1  # 10% deviation triggers elevated crisis
    critical_threshold: float = 0.25  # 25% deviation triggers critical crisis

    # Latency spike thresholds (ratio to baseline)
    latency_spike_elevated: float = 1.5  # 1.5x baseline
    latency_spike_critical: float = 2.0  # 2x baseline

    # Rate of change thresholds (dF/dt)
    dF_dt_warning: float = 0.01  # Warning threshold for energy derivative
    dF_dt_critical: float = 0.05  # Critical threshold for energy derivative

    # Sustained rise threshold (consecutive steps)
    sustained_rise_steps: int = 5


@dataclass
class SafetyConstraints:
    """Safety constraints for thermodynamic control."""

    # Monotonic descent tolerance
    epsilon_base: float = 0.01  # Base tolerance as fraction of baseline_EMA
    epsilon_min: float = 1e-9  # Minimum epsilon to prevent numerical issues

    # Adaptive epsilon parameters
    epsilon_adaptive_scale: float = 0.05  # Scale factor for dF/dt contribution

    # Circuit breaker parameters
    circuit_breaker_timeout_seconds: float = 300.0  # 5 minutes
    max_consecutive_violations: int = 3

    # Recovery window for temporary spikes
    recovery_window_steps: int = 3
    recovery_decay_factor: float = 0.9


@dataclass
class GeneticAlgorithmConfig:
    """Configuration for crisis-aware genetic algorithm."""

    # Population sizes by crisis mode
    pop_size_normal: int = 16
    pop_size_elevated: int = 24
    pop_size_critical: int = 32

    # Probabilities
    crossover_prob: float = 0.4
    mutation_prob_normal: float = 0.6
    mutation_prob_elevated: float = 0.7
    mutation_prob_critical: float = 0.8

    # Evolution parameters
    generations: int = 10
    elitism_count: int = 2

    # Fitness scaling
    fitness_scaling_factor: float = 1.0


@dataclass
class RecoveryAgentConfig:
    """Configuration for adaptive recovery agent (Q-learning)."""

    # Q-learning parameters
    learning_rate: float = 0.1
    discount_factor: float = 0.95
    epsilon_exploration: float = 0.1

    # Recovery actions
    actions: tuple = field(default_factory=lambda: ("slow", "medium", "fast"))

    # State discretization
    F_deviation_bins: int = 5
    latency_spike_bins: int = 4
    crisis_duration_bins: int = 3


@dataclass
class LinkActivatorConfig:
    """Configuration for link activator (protocol hot-swapping)."""

    # Bond type to protocol mapping priorities
    protocol_hierarchy: Dict[str, tuple] = field(
        default_factory=lambda: {
            "covalent": ("rdma", "crdt", "shared_memory"),
            "ionic": ("crdt", "grpc", "shared_memory"),
            "metallic": ("shared_memory", "grpc", "local"),
            "vdw": ("grpc", "gossip", "local"),
            "hydrogen": ("gossip", "grpc", "local"),
        }
    )

    # Activation costs (relative)
    activation_costs: Dict[str, float] = field(
        default_factory=lambda: {
            "rdma": 1.0,
            "crdt": 0.8,
            "shared_memory": 0.6,
            "grpc": 0.4,
            "gossip": 0.3,
            "local": 0.1,
        }
    )

    # Timeout for protocol activation (seconds)
    activation_timeout: float = 5.0

    # Maximum retries for failed activations
    max_retries: int = 3


@dataclass
class TelemetryConfig:
    """Configuration for telemetry and observability."""

    # Audit log path
    audit_log_path: Path = Path("/var/log/geosync/thermo_audit.jsonl")

    # Telemetry export paths
    telemetry_export_dir: Path = Path(".ci_artifacts")

    # History retention
    max_history_size: int = 10000

    # Export intervals
    export_interval_seconds: float = 60.0

    # Prometheus metrics
    enable_prometheus: bool = True
    prometheus_port: int = 9090


@dataclass
class CNSStabilizerConfig:
    """Configuration for CNS (Central Nervous System) Stabilizer."""

    # Normalization mode
    normalize: str = "logret"  # "logret", "zscore", or "none"

    # Hybrid mode (combine Kalman + PID)
    hybrid_mode: bool = True

    # Kalman filter parameters
    kalman_process_noise: float = 1e-5
    kalman_measurement_noise: float = 1e-3

    # PID controller parameters
    pid_kp: float = 0.5
    pid_ki: float = 0.1
    pid_kd: float = 0.05

    # Veto thresholds
    veto_integrity_threshold: float = 0.8
    veto_delta_f_threshold: float = 0.1

    # Circadian rhythm
    enable_circadian: bool = True
    circadian_period_hours: float = 24.0


@dataclass
class VLPOFilterConfig:
    """Configuration for VLPO (Ventrolateral Preoptic) Core Filter."""

    # Filter window size
    window_size: int = 64

    # Threshold for outlier rejection
    outlier_threshold: float = 3.0  # Standard deviations

    # Smoothing factor
    smoothing_alpha: float = 0.2

    # Sensory calibration configuration
    calibration_mode: str = "ema_minmax"
    calibration_window: int = 256
    calibration_alpha: float = 0.2
    quantile_low: float = 0.05
    quantile_high: float = 0.95


@dataclass
class DualApprovalConfig:
    """Configuration for dual approval system."""

    # Token validation
    require_dual_approval: bool = True
    token_env_var: str = "THERMO_DUAL_TOKEN"

    # Action types requiring dual approval
    dual_approval_actions: tuple = field(
        default_factory=lambda: (
            "topology_mutation",
            "protocol_activation",
            "circuit_breaker_override",
        )
    )

    # Token expiration
    token_expiration_seconds: float = 3600.0  # 1 hour


@dataclass
class ThermoConfig:
    """Master configuration for TACL system."""

    # Sub-configurations
    crisis: CrisisThresholds = field(default_factory=CrisisThresholds)
    safety: SafetyConstraints = field(default_factory=SafetyConstraints)
    genetic_algorithm: GeneticAlgorithmConfig = field(default_factory=GeneticAlgorithmConfig)
    recovery_agent: RecoveryAgentConfig = field(default_factory=RecoveryAgentConfig)
    link_activator: LinkActivatorConfig = field(default_factory=LinkActivatorConfig)
    telemetry: TelemetryConfig = field(default_factory=TelemetryConfig)
    cns_stabilizer: CNSStabilizerConfig = field(default_factory=CNSStabilizerConfig)
    vlpo_filter: VLPOFilterConfig = field(default_factory=VLPOFilterConfig)
    dual_approval: DualApprovalConfig = field(default_factory=DualApprovalConfig)

    # Control temperature (for free energy calculation)
    control_temperature: float = 0.60

    # Maximum acceptable free energy
    max_acceptable_energy: float = 1.35

    # Controller cadence (seconds between control steps)
    control_step_interval: float = 0.001  # 1ms

    @classmethod
    def from_yaml(cls, path: str | Path) -> ThermoConfig:
        """Load configuration from YAML file.

        Args:
            path: Path to YAML configuration file

        Returns:
            ThermoConfig instance
        """
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # Recursively instantiate nested dataclasses
        config = cls()

        if "crisis" in data:
            config.crisis = CrisisThresholds(**data["crisis"])
        if "safety" in data:
            config.safety = SafetyConstraints(**data["safety"])
        if "genetic_algorithm" in data:
            config.genetic_algorithm = GeneticAlgorithmConfig(**data["genetic_algorithm"])
        if "recovery_agent" in data:
            config.recovery_agent = RecoveryAgentConfig(**data["recovery_agent"])
        if "link_activator" in data:
            config.link_activator = LinkActivatorConfig(**data["link_activator"])
        if "telemetry" in data:
            telemetry_data = data["telemetry"]
            if "audit_log_path" in telemetry_data:
                telemetry_data["audit_log_path"] = Path(telemetry_data["audit_log_path"])
            if "telemetry_export_dir" in telemetry_data:
                telemetry_data["telemetry_export_dir"] = Path(
                    telemetry_data["telemetry_export_dir"]
                )
            config.telemetry = TelemetryConfig(**telemetry_data)
        if "cns_stabilizer" in data:
            config.cns_stabilizer = CNSStabilizerConfig(**data["cns_stabilizer"])
        if "vlpo_filter" in data:
            config.vlpo_filter = VLPOFilterConfig(**data["vlpo_filter"])
        if "dual_approval" in data:
            config.dual_approval = DualApprovalConfig(**data["dual_approval"])

        # Top-level parameters
        if "control_temperature" in data:
            config.control_temperature = float(data["control_temperature"])
        if "max_acceptable_energy" in data:
            config.max_acceptable_energy = float(data["max_acceptable_energy"])
        if "control_step_interval" in data:
            config.control_step_interval = float(data["control_step_interval"])

        return config

    @classmethod
    def from_env(cls) -> ThermoConfig:
        """Load configuration from environment variables.

        Returns:
            ThermoConfig instance with values overridden by environment
        """
        config = cls()

        # Override from environment variables
        if "THERMO_CONTROL_TEMPERATURE" in os.environ:
            config.control_temperature = float(os.environ["THERMO_CONTROL_TEMPERATURE"])
        if "THERMO_MAX_ENERGY" in os.environ:
            config.max_acceptable_energy = float(os.environ["THERMO_MAX_ENERGY"])
        if "THERMO_AUDIT_LOG_PATH" in os.environ:
            config.telemetry.audit_log_path = Path(os.environ["THERMO_AUDIT_LOG_PATH"])
        if "THERMO_DUAL_TOKEN" in os.environ:
            # Token is loaded at runtime, just note it's available
            pass

        return config

    def to_dict(self) -> Dict:
        """Convert configuration to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "crisis": self.crisis.__dict__,
            "safety": self.safety.__dict__,
            "genetic_algorithm": self.genetic_algorithm.__dict__,
            "recovery_agent": self.recovery_agent.__dict__,
            "link_activator": {
                k: v if not isinstance(v, dict) else v
                for k, v in self.link_activator.__dict__.items()
            },
            "telemetry": {
                k: str(v) if isinstance(v, Path) else v for k, v in self.telemetry.__dict__.items()
            },
            "cns_stabilizer": self.cns_stabilizer.__dict__,
            "vlpo_filter": self.vlpo_filter.__dict__,
            "dual_approval": self.dual_approval.__dict__,
            "control_temperature": self.control_temperature,
            "max_acceptable_energy": self.max_acceptable_energy,
            "control_step_interval": self.control_step_interval,
        }

    def export_yaml(self, path: str | Path) -> None:
        """Export configuration to YAML file.

        Args:
            path: Path to output YAML file
        """
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False, sort_keys=False)

    def validate(self) -> "ConfigValidationResult":
        """Validate all configuration parameters for safety compliance.

        Returns:
            ConfigValidationResult with validation status and any issues found
        """
        issues: List[ConfigValidationIssue] = []
        warnings: List[ConfigValidationIssue] = []

        # Validate control temperature
        if self.control_temperature <= 0:
            issues.append(
                ConfigValidationIssue(
                    field="control_temperature",
                    message="Control temperature must be positive",
                    severity="error",
                    current_value=self.control_temperature,
                )
            )
        elif self.control_temperature > 1.0:
            warnings.append(
                ConfigValidationIssue(
                    field="control_temperature",
                    message="Control temperature > 1.0 may lead to unstable behavior",
                    severity="warning",
                    current_value=self.control_temperature,
                )
            )

        # Validate max_acceptable_energy
        if self.max_acceptable_energy <= 0:
            issues.append(
                ConfigValidationIssue(
                    field="max_acceptable_energy",
                    message="Maximum acceptable energy must be positive",
                    severity="error",
                    current_value=self.max_acceptable_energy,
                )
            )

        # Validate control_step_interval
        if self.control_step_interval <= 0:
            issues.append(
                ConfigValidationIssue(
                    field="control_step_interval",
                    message="Control step interval must be positive",
                    severity="error",
                    current_value=self.control_step_interval,
                )
            )
        elif self.control_step_interval < 0.0001:
            warnings.append(
                ConfigValidationIssue(
                    field="control_step_interval",
                    message="Very short control intervals may cause performance issues",
                    severity="warning",
                    current_value=self.control_step_interval,
                )
            )

        # Validate crisis thresholds ordering
        if self.crisis.elevated_threshold >= self.crisis.critical_threshold:
            issues.append(
                ConfigValidationIssue(
                    field="crisis.thresholds",
                    message="Elevated threshold must be less than critical threshold",
                    severity="error",
                    current_value={
                        "elevated": self.crisis.elevated_threshold,
                        "critical": self.crisis.critical_threshold,
                    },
                )
            )

        # Validate latency spike thresholds
        if self.crisis.latency_spike_elevated >= self.crisis.latency_spike_critical:
            issues.append(
                ConfigValidationIssue(
                    field="crisis.latency_spike_thresholds",
                    message="Elevated latency spike threshold must be less than critical",
                    severity="error",
                    current_value={
                        "elevated": self.crisis.latency_spike_elevated,
                        "critical": self.crisis.latency_spike_critical,
                    },
                )
            )

        # Validate dF/dt thresholds
        if self.crisis.dF_dt_warning >= self.crisis.dF_dt_critical:
            issues.append(
                ConfigValidationIssue(
                    field="crisis.dF_dt_thresholds",
                    message="dF/dt warning threshold must be less than critical",
                    severity="error",
                    current_value={
                        "warning": self.crisis.dF_dt_warning,
                        "critical": self.crisis.dF_dt_critical,
                    },
                )
            )

        # Validate safety constraints
        if self.safety.epsilon_base <= 0:
            issues.append(
                ConfigValidationIssue(
                    field="safety.epsilon_base",
                    message="Epsilon base must be positive",
                    severity="error",
                    current_value=self.safety.epsilon_base,
                )
            )

        if self.safety.epsilon_min <= 0:
            issues.append(
                ConfigValidationIssue(
                    field="safety.epsilon_min",
                    message="Epsilon minimum must be positive",
                    severity="error",
                    current_value=self.safety.epsilon_min,
                )
            )

        if self.safety.circuit_breaker_timeout_seconds <= 0:
            issues.append(
                ConfigValidationIssue(
                    field="safety.circuit_breaker_timeout_seconds",
                    message="Circuit breaker timeout must be positive",
                    severity="error",
                    current_value=self.safety.circuit_breaker_timeout_seconds,
                )
            )

        if self.safety.max_consecutive_violations < 1:
            issues.append(
                ConfigValidationIssue(
                    field="safety.max_consecutive_violations",
                    message="Max consecutive violations must be at least 1",
                    severity="error",
                    current_value=self.safety.max_consecutive_violations,
                )
            )

        if self.safety.recovery_decay_factor <= 0 or self.safety.recovery_decay_factor > 1:
            issues.append(
                ConfigValidationIssue(
                    field="safety.recovery_decay_factor",
                    message="Recovery decay factor must be in (0, 1]",
                    severity="error",
                    current_value=self.safety.recovery_decay_factor,
                )
            )

        # Validate genetic algorithm config
        if self.genetic_algorithm.pop_size_normal < 2:
            issues.append(
                ConfigValidationIssue(
                    field="genetic_algorithm.pop_size_normal",
                    message="Population size must be at least 2",
                    severity="error",
                    current_value=self.genetic_algorithm.pop_size_normal,
                )
            )

        if not (0 <= self.genetic_algorithm.crossover_prob <= 1):
            issues.append(
                ConfigValidationIssue(
                    field="genetic_algorithm.crossover_prob",
                    message="Crossover probability must be in [0, 1]",
                    severity="error",
                    current_value=self.genetic_algorithm.crossover_prob,
                )
            )

        for prob_name in [
            "mutation_prob_normal",
            "mutation_prob_elevated",
            "mutation_prob_critical",
        ]:
            prob_value = getattr(self.genetic_algorithm, prob_name)
            if not (0 <= prob_value <= 1):
                issues.append(
                    ConfigValidationIssue(
                        field=f"genetic_algorithm.{prob_name}",
                        message="Mutation probability must be in [0, 1]",
                        severity="error",
                        current_value=prob_value,
                    )
                )

        # Validate recovery agent config
        if not (0 < self.recovery_agent.learning_rate <= 1):
            issues.append(
                ConfigValidationIssue(
                    field="recovery_agent.learning_rate",
                    message="Learning rate must be in (0, 1]",
                    severity="error",
                    current_value=self.recovery_agent.learning_rate,
                )
            )

        if not (0 <= self.recovery_agent.discount_factor <= 1):
            issues.append(
                ConfigValidationIssue(
                    field="recovery_agent.discount_factor",
                    message="Discount factor must be in [0, 1]",
                    severity="error",
                    current_value=self.recovery_agent.discount_factor,
                )
            )

        # Validate CNS stabilizer config
        valid_normalize = {"logret", "zscore", "none"}
        if self.cns_stabilizer.normalize not in valid_normalize:
            issues.append(
                ConfigValidationIssue(
                    field="cns_stabilizer.normalize",
                    message=f"Normalize must be one of {valid_normalize}",
                    severity="error",
                    current_value=self.cns_stabilizer.normalize,
                )
            )

        # Validate veto thresholds
        if not (0 <= self.cns_stabilizer.veto_integrity_threshold <= 1):
            issues.append(
                ConfigValidationIssue(
                    field="cns_stabilizer.veto_integrity_threshold",
                    message="Veto integrity threshold must be in [0, 1]",
                    severity="error",
                    current_value=self.cns_stabilizer.veto_integrity_threshold,
                )
            )

        # Validate VLPO filter config
        if self.vlpo_filter.window_size < 1:
            issues.append(
                ConfigValidationIssue(
                    field="vlpo_filter.window_size",
                    message="Window size must be at least 1",
                    severity="error",
                    current_value=self.vlpo_filter.window_size,
                )
            )

        if self.vlpo_filter.outlier_threshold <= 0:
            issues.append(
                ConfigValidationIssue(
                    field="vlpo_filter.outlier_threshold",
                    message="Outlier threshold must be positive",
                    severity="error",
                    current_value=self.vlpo_filter.outlier_threshold,
                )
            )

        if not (0 < self.vlpo_filter.smoothing_alpha <= 1):
            issues.append(
                ConfigValidationIssue(
                    field="vlpo_filter.smoothing_alpha",
                    message="Smoothing alpha must be in (0, 1]",
                    severity="error",
                    current_value=self.vlpo_filter.smoothing_alpha,
                )
            )

        valid_calibration_modes = {"ema_minmax", "robust_quantile"}
        if self.vlpo_filter.calibration_mode not in valid_calibration_modes:
            issues.append(
                ConfigValidationIssue(
                    field="vlpo_filter.calibration_mode",
                    message=(f"Calibration mode must be one of {sorted(valid_calibration_modes)}"),
                    severity="error",
                    current_value=self.vlpo_filter.calibration_mode,
                )
            )

        if self.vlpo_filter.calibration_window < 1:
            issues.append(
                ConfigValidationIssue(
                    field="vlpo_filter.calibration_window",
                    message="Calibration window must be at least 1",
                    severity="error",
                    current_value=self.vlpo_filter.calibration_window,
                )
            )

        if not (0 < self.vlpo_filter.calibration_alpha <= 1):
            issues.append(
                ConfigValidationIssue(
                    field="vlpo_filter.calibration_alpha",
                    message="Calibration alpha must be in (0, 1]",
                    severity="error",
                    current_value=self.vlpo_filter.calibration_alpha,
                )
            )

        if not (0 <= self.vlpo_filter.quantile_low < self.vlpo_filter.quantile_high <= 1):
            issues.append(
                ConfigValidationIssue(
                    field="vlpo_filter.quantile_bounds",
                    message="Quantile bounds must satisfy 0 <= low < high <= 1",
                    severity="error",
                    current_value={
                        "low": self.vlpo_filter.quantile_low,
                        "high": self.vlpo_filter.quantile_high,
                    },
                )
            )

        # Validate dual approval config
        if self.dual_approval.token_expiration_seconds <= 0:
            issues.append(
                ConfigValidationIssue(
                    field="dual_approval.token_expiration_seconds",
                    message="Token expiration must be positive",
                    severity="error",
                    current_value=self.dual_approval.token_expiration_seconds,
                )
            )

        return ConfigValidationResult(
            valid=len(issues) == 0,
            issues=issues,
            warnings=warnings,
        )

    def validate_or_raise(self) -> None:
        """Validate configuration and raise if invalid.

        Raises:
            ConfigValidationError: If validation fails
        """
        result = self.validate()
        if not result.valid:
            raise ConfigValidationError(
                f"Configuration validation failed with {len(result.issues)} errors",
                result,
            )


@dataclass
class ConfigValidationIssue:
    """A single configuration validation issue."""

    field: str
    message: str
    severity: str  # "error" or "warning"
    current_value: Any = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "field": self.field,
            "message": self.message,
            "severity": self.severity,
            "current_value": (str(self.current_value) if self.current_value is not None else None),
        }


@dataclass
class ConfigValidationResult:
    """Result of configuration validation."""

    valid: bool
    issues: List["ConfigValidationIssue"]
    warnings: List["ConfigValidationIssue"]

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "valid": self.valid,
            "issues": [issue.to_dict() for issue in self.issues],
            "warnings": [warning.to_dict() for warning in self.warnings],
            "issue_count": len(self.issues),
            "warning_count": len(self.warnings),
        }


class ConfigValidationError(Exception):
    """Raised when configuration validation fails."""

    def __init__(self, message: str, result: ConfigValidationResult) -> None:
        super().__init__(message)
        self.result = result


def load_default_config() -> ThermoConfig:
    """Load default thermodynamics configuration.

    Attempts to load from file, falls back to defaults.

    Returns:
        ThermoConfig instance
    """
    config_paths = [
        Path("config/thermo_config.yaml"),
        Path("configs/thermo_config.yaml"),
        Path("/etc/geosync/thermo_config.yaml"),
    ]

    for config_path in config_paths:
        if config_path.exists():
            return ThermoConfig.from_yaml(config_path)

    # Fall back to environment or defaults
    return ThermoConfig.from_env()


__all__ = [
    "ThermoConfig",
    "CrisisThresholds",
    "SafetyConstraints",
    "GeneticAlgorithmConfig",
    "RecoveryAgentConfig",
    "LinkActivatorConfig",
    "TelemetryConfig",
    "CNSStabilizerConfig",
    "VLPOFilterConfig",
    "DualApprovalConfig",
    "ConfigValidationIssue",
    "ConfigValidationResult",
    "ConfigValidationError",
    "load_default_config",
]
