# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Configuration loader for the GeoSync Cortex microservice."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from core.security import (
    DEFAULT_HTTP_ALPN_PROTOCOLS,
    DEFAULT_MODERN_CIPHER_SUITES,
    parse_tls_version,
)

from .errors import ConfigurationError as CortexConfigurationError

CONFIG_ENV_PREFIX = "CORTEX__"
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "service.yaml"


# Keep alias for backward compatibility
class ConfigurationError(CortexConfigurationError):
    """Raised when configuration cannot be loaded or validated."""

    def __init__(self, message: str) -> None:
        """Initialize configuration error without details."""
        super().__init__(message, details={})


def _ensure_file(path: Path, *, description: str) -> Path:
    if not path.exists():
        raise ConfigurationError(f"{description} '{path}' does not exist")
    if not path.is_file():
        raise ConfigurationError(f"{description} '{path}' must be a file")
    return path


def _normalise_sequence(values: tuple[str, ...] | list[str] | str) -> tuple[str, ...]:
    if isinstance(values, str):
        candidates = [item.strip() for item in values.split(",")]
    else:
        candidates = [str(item).strip() for item in values]
    return tuple(dict.fromkeys(item for item in candidates if item))


@dataclass(slots=True)
class ServiceTLSSettings:
    """TLS parameters securing the cortex HTTP listener."""

    cert_file: Path
    key_file: Path
    client_ca_file: Path | None = None
    client_revocation_list_file: Path | None = None
    require_client_certificate: bool = False
    minimum_version: str = "TLSv1.2"
    cipher_suites: tuple[str, ...] = DEFAULT_MODERN_CIPHER_SUITES
    alpn_protocols: tuple[str, ...] = DEFAULT_HTTP_ALPN_PROTOCOLS

    def __post_init__(self) -> None:
        """Validate TLS configuration after initialization."""
        self.cert_file = _ensure_file(Path(self.cert_file), description="TLS certificate")
        self.key_file = _ensure_file(Path(self.key_file), description="TLS private key")
        if self.client_ca_file is not None:
            self.client_ca_file = _ensure_file(
                Path(self.client_ca_file), description="Trusted client CA bundle"
            )
        if self.client_revocation_list_file is not None:
            self.client_revocation_list_file = _ensure_file(
                Path(self.client_revocation_list_file),
                description="Client certificate revocation list",
            )
        self.cipher_suites = _normalise_sequence(self.cipher_suites)
        self.alpn_protocols = _normalise_sequence(self.alpn_protocols)

        # Validate cipher suites not empty
        if not self.cipher_suites:
            raise ConfigurationError("TLS cipher suites list cannot be empty")

        # Validate minimum TLS version
        parse_tls_version(self.minimum_version)

        # Warn on deprecated protocols
        if self.minimum_version in {"TLSv1.0", "TLSv1.1", "SSLv3"}:
            import logging

            logging.getLogger(__name__).warning(
                "Deprecated TLS version '%s' configured. Consider upgrading to TLSv1.2 or TLSv1.3",
                self.minimum_version,
            )

        if self.require_client_certificate and self.client_ca_file is None:
            raise ConfigurationError(
                "Client certificate authentication requires a trusted CA bundle"
            )


@dataclass(slots=True)
class ServiceMeta:
    """Metadata that describes the running service."""

    name: str = "GeoSync Cortex Service"
    version: str = "1.0.0"
    description: str = "Cognitive signal orchestration for GeoSync portfolios"
    metrics_path: str = "/metrics"
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8001
    tls: ServiceTLSSettings | None = None


@dataclass(slots=True)
class DatabaseSettings:
    """Database connectivity details."""

    url: str
    pool_size: int = 10
    pool_timeout: int = 30
    echo: bool = False
    tls: "DatabaseTLSSettings" | None = None


@dataclass(slots=True)
class DatabaseTLSSettings:
    """TLS credentials required for PostgreSQL connectivity."""

    ca_file: Path
    cert_file: Path
    key_file: Path

    def __post_init__(self) -> None:
        self.ca_file = _ensure_file(Path(self.ca_file), description="PostgreSQL CA bundle")
        self.cert_file = _ensure_file(
            Path(self.cert_file), description="PostgreSQL client certificate"
        )
        self.key_file = _ensure_file(Path(self.key_file), description="PostgreSQL client key")


@dataclass(slots=True)
class SignalSettings:
    """Hyper-parameters that shape signal computation."""

    rescale_min: float = -1.0
    rescale_max: float = 1.0
    smoothing_factor: float = 0.25
    volatility_floor: float = 1e-6


@dataclass(slots=True)
class RiskSettings:
    """Settings for portfolio risk evaluation."""

    max_absolute_exposure: float = 2.0
    var_confidence: float = 0.95
    stress_scenarios: tuple[float, ...] = (0.85, 0.5)

    def __post_init__(self) -> None:
        """Validate risk settings after initialization."""
        # Validate stress scenarios are unique and valid
        if not self.stress_scenarios:
            raise ConfigurationError("stress_scenarios cannot be empty")

        # Check for uniqueness
        unique_scenarios = set(self.stress_scenarios)
        if len(unique_scenarios) != len(self.stress_scenarios):
            raise ConfigurationError(
                f"stress_scenarios must contain unique values, got: {self.stress_scenarios}"
            )

        # Validate all scenarios are positive
        for scenario in self.stress_scenarios:
            if scenario <= 0:
                raise ConfigurationError(
                    f"All stress_scenarios must be positive, got: {self.stress_scenarios}"
                )

        # Validate var_confidence is in valid range
        if not 0 < self.var_confidence < 1:
            raise ConfigurationError(
                f"var_confidence must be between 0 and 1 (exclusive), got: {self.var_confidence}"
            )


@dataclass(slots=True)
class RegimeSettings:
    """Parameters for market regime modulation."""

    decay: float = 0.2
    min_valence: float = -1.0
    max_valence: float = 1.0
    confidence_floor: float = 0.1


@dataclass(slots=True)
class CortexSettings:
    """Aggregated configuration for the cortex microservice."""

    service: ServiceMeta
    database: DatabaseSettings
    signals: SignalSettings
    risk: RiskSettings
    regime: RegimeSettings


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
            raise ConfigurationError(
                f"Invalid YAML payload for environment override {key!r}: {candidate!r}"
            ) from exc
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

    if config_path is not None:
        resolved_path = Path(config_path)
    else:
        env_path = os.getenv("CORTEX_CONFIG_PATH")
        resolved_path = Path(env_path) if env_path else DEFAULT_CONFIG_PATH
    raw_config = _load_yaml_config(resolved_path)
    merged_config = _apply_env_overrides(raw_config)

    service_payload = dict(merged_config.get("service", {}))
    tls_payload = service_payload.get("tls")
    if isinstance(tls_payload, dict):
        service_payload["tls"] = ServiceTLSSettings(**tls_payload)

    database_payload = dict(merged_config.get("database", {}))
    db_tls_payload = database_payload.get("tls")
    if isinstance(db_tls_payload, dict):
        database_payload["tls"] = DatabaseTLSSettings(**db_tls_payload)

    try:
        service = ServiceMeta(**service_payload)
        database = DatabaseSettings(**database_payload)
        signals = SignalSettings(**merged_config.get("signals", {}))
        risk_config = merged_config.get("risk", {})
        stress = risk_config.get("stress_scenarios", (0.85, 0.5))
        if isinstance(stress, list):
            risk_config = {
                **risk_config,
                "stress_scenarios": tuple(float(s) for s in stress),
            }
        risk = RiskSettings(**risk_config)
        regime = RegimeSettings(**merged_config.get("regime", {}))
    except TypeError as exc:  # pragma: no cover - thin parsing wrapper
        raise ConfigurationError("Configuration payload is invalid") from exc

    return CortexSettings(
        service=service, database=database, signals=signals, risk=risk, regime=regime
    )


__all__ = [
    "ConfigurationError",
    "CortexSettings",
    "DatabaseSettings",
    "DatabaseTLSSettings",
    "DEFAULT_CONFIG_PATH",
    "RiskSettings",
    "RegimeSettings",
    "ServiceMeta",
    "ServiceTLSSettings",
    "SignalSettings",
    "load_settings",
]
