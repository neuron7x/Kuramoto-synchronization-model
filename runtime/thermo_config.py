"""Thermodynamics Configuration Module

Centralized configuration for TACL (Thermodynamic Autonomic Control Layer)
including energy thresholds, crisis parameters, and system constants.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

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
    protocol_hierarchy: Dict[str, tuple] = field(default_factory=lambda: {
        "covalent": ("rdma", "crdt", "shared_memory"),
        "ionic": ("crdt", "grpc", "shared_memory"),
        "metallic": ("shared_memory", "grpc", "local"),
        "vdw": ("grpc", "gossip", "local"),
        "hydrogen": ("gossip", "grpc", "local"),
    })
    
    # Activation costs (relative)
    activation_costs: Dict[str, float] = field(default_factory=lambda: {
        "rdma": 1.0,
        "crdt": 0.8,
        "shared_memory": 0.6,
        "grpc": 0.4,
        "gossip": 0.3,
        "local": 0.1,
    })
    
    # Timeout for protocol activation (seconds)
    activation_timeout: float = 5.0
    
    # Maximum retries for failed activations
    max_retries: int = 3


@dataclass
class TelemetryConfig:
    """Configuration for telemetry and observability."""
    
    # Audit log path
    audit_log_path: Path = Path("/var/log/tradepulse/thermo_audit.jsonl")
    
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


@dataclass
class DualApprovalConfig:
    """Configuration for dual approval system."""
    
    # Token validation
    require_dual_approval: bool = True
    token_env_var: str = "THERMO_DUAL_TOKEN"
    
    # Action types requiring dual approval
    dual_approval_actions: tuple = field(default_factory=lambda: (
        "topology_mutation",
        "protocol_activation",
        "circuit_breaker_override",
    ))
    
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
                telemetry_data["telemetry_export_dir"] = Path(telemetry_data["telemetry_export_dir"])
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
                k: str(v) if isinstance(v, Path) else v
                for k, v in self.telemetry.__dict__.items()
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


def load_default_config() -> ThermoConfig:
    """Load default thermodynamics configuration.
    
    Attempts to load from file, falls back to defaults.
    
    Returns:
        ThermoConfig instance
    """
    config_paths = [
        Path("config/thermo_config.yaml"),
        Path("configs/thermo_config.yaml"),
        Path("/etc/tradepulse/thermo_config.yaml"),
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
    "load_default_config",
]
