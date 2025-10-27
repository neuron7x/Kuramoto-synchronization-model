"""Configuration loader for the TradePulse Cortex microservice."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


CONFIG_ENV_PREFIX = "CORTEX__"
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "service.yaml"


@dataclass(slots=True)
class ServiceMeta:
    """Metadata that describes the running service."""

    name: str = "TradePulse Cortex Service"
    version: str = "1.0.0"
    description: str = "Cognitive signal orchestration for TradePulse portfolios"
    metrics_path: str = "/metrics"
    log_level: str = "INFO"


@dataclass(slots=True)
class DatabaseSettings:
    """Database connectivity details."""

    url: str = "sqlite+pysqlite:///:memory:"
    pool_size: int = 10
    pool_timeout: int = 30
    echo: bool = False


@dataclass(slots=True)
class SignalSettings:
    """Hyper-parameters that shape signal computation."""

    rescale_min: float = -1.0
    rescale_max: float = 1.0
    smoothing_factor: float = 0.25
    volatility_floor: float = 1e-6
    neighbor_coupling: float = 0.5
    valence_coupling: float = 0.75
    signal_gain: float = 1.0


@dataclass(slots=True)
class RiskSettings:
    """Settings for portfolio risk evaluation."""

    max_absolute_exposure: float = 2.0
    var_confidence: float = 0.95
    stress_scenarios: tuple[float, ...] = (0.85, 0.5)
    penalty_gain: float = 1.5


@dataclass(slots=True)
class RegimeSettings:
    """Parameters for market regime modulation."""

    decay: float = 0.2
    min_valence: float = -1.0
    max_valence: float = 1.0
    confidence_floor: float = 0.1
    initial_valence: float = 0.0


@dataclass(slots=True)
class CortexSettings:
    """Aggregated configuration for the cortex microservice."""

    service: ServiceMeta
    database: DatabaseSettings
    signals: SignalSettings
    risk: RiskSettings
    regime: RegimeSettings


class ConfigurationError(RuntimeError):
    """Raised when configuration cannot be loaded or validated."""


def _deep_update(mapping: dict[str, Any], path: list[str], value: Any) -> None:
    """Update a nested mapping using the provided path."""

    cursor = mapping
    for key in path[:-1]:
        cursor = cursor.setdefault(key, {})
    cursor[path[-1]] = value


def _apply_env_overrides(raw: dict[str, Any]) -> dict[str, Any]:
    """Apply environment overrides using the ``CORTEX__`` prefix."""

    for key, candidate in os.environ.items():
        if not key.startswith(CONFIG_ENV_PREFIX):
            continue
        path = key[len(CONFIG_ENV_PREFIX) :].lower().split("__")
        try:
            parsed_value = yaml.safe_load(candidate)
        except yaml.YAMLError as exc:  # pragma: no cover - defensive branch
            raise ConfigurationError(f"Invalid YAML payload for environment override {key!r}: {candidate!r}") from exc
        _deep_update(raw, path, parsed_value)
    return raw


def _load_yaml_config(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        raise ConfigurationError(f"Configuration file not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as handle:
        try:
            return yaml.safe_load(handle) or {}
        except yaml.YAMLError as exc:  # pragma: no cover - defensive branch
            raise ConfigurationError(f"Failed to parse configuration file {config_path}") from exc


def load_settings(config_path: str | os.PathLike[str] | None = None) -> CortexSettings:
    """Load settings from YAML and environment overrides."""

    resolved_path = Path(config_path or os.getenv("CORTEX_CONFIG_PATH", DEFAULT_CONFIG_PATH))
    raw_config = _load_yaml_config(resolved_path)
    merged_config = _apply_env_overrides(raw_config)

    try:
        service = ServiceMeta(**merged_config.get("service", {}))
        database = DatabaseSettings(**merged_config.get("database", {}))
        signals = SignalSettings(**merged_config.get("signals", {}))
        risk_config = merged_config.get("risk", {})
        stress = risk_config.get("stress_scenarios", (0.85, 0.5))
        if isinstance(stress, list):
            risk_config = {**risk_config, "stress_scenarios": tuple(float(s) for s in stress)}
        risk = RiskSettings(**risk_config)
        regime = RegimeSettings(**merged_config.get("regime", {}))
    except TypeError as exc:  # pragma: no cover - thin parsing wrapper
        raise ConfigurationError("Configuration payload is invalid") from exc

    return CortexSettings(service=service, database=database, signals=signals, risk=risk, regime=regime)


__all__ = [
    "ConfigurationError",
    "CortexSettings",
    "DatabaseSettings",
    "DEFAULT_CONFIG_PATH",
    "RiskSettings",
    "RegimeSettings",
    "ServiceMeta",
    "SignalSettings",
    "load_settings",
]
