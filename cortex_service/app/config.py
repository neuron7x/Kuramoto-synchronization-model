"""Configuration loader for the TradePulse Cortex microservice.

This module provides configuration loading with support for:
- YAML configuration files
- Environment variable overrides (CORTEX__ prefix)
- TLS settings validation
- Type-safe configuration dataclasses
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from core.security import DEFAULT_HTTP_ALPN_PROTOCOLS, DEFAULT_MODERN_CIPHER_SUITES, parse_tls_version

from .errors import ConfigurationError

CONFIG_ENV_PREFIX = "CORTEX__"
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "service.yaml"

# Singleton cache for configuration to avoid repeated file I/O
_settings_cache: CortexSettings | None = None


def _ensure_file(path: Path, *, description: str) -> Path:
    """Validate that a path exists and is a regular file.
    
    Args:
        path: Path to validate
        description: Human-readable description for error messages
        
    Returns:
        The validated path
        
    Raises:
        ConfigurationError: If path doesn't exist or isn't a file
    """
    if not path.exists():
        raise ConfigurationError(f"{description} '{path}' does not exist")
    if not path.is_file():
        raise ConfigurationError(f"{description} '{path}' must be a file")
    return path


def _normalise_sequence(values: tuple[str, ...] | list[str] | str) -> tuple[str, ...]:
    """Normalize a value to a tuple of unique strings.
    
    Handles comma-separated strings, lists, or tuples. Removes duplicates
    while preserving order.
    
    Args:
        values: Input value (string, list, or tuple)
        
    Returns:
        Tuple of unique non-empty strings
    """
    if isinstance(values, str):
        candidates = [item.strip() for item in values.split(",")]
    else:
        candidates = [str(item).strip() for item in values]
    return tuple(dict.fromkeys(item for item in candidates if item))


@dataclass(slots=True)
class ServiceTLSSettings:
    """TLS parameters securing the cortex HTTP listener.
    
    Attributes:
        cert_file: Path to server certificate file
        key_file: Path to server private key file
        client_ca_file: Optional path to trusted client CA bundle
        client_revocation_list_file: Optional path to CRL file
        require_client_certificate: Whether to require client certs
        minimum_version: Minimum TLS version (e.g., TLSv1.2, TLSv1.3)
        cipher_suites: Allowed TLS cipher suites
        alpn_protocols: ALPN protocols for HTTP negotiation
    """

    cert_file: Path
    key_file: Path
    client_ca_file: Path | None = None
    client_revocation_list_file: Path | None = None
    require_client_certificate: bool = False
    minimum_version: str = "TLSv1.2"
    cipher_suites: tuple[str, ...] = DEFAULT_MODERN_CIPHER_SUITES
    alpn_protocols: tuple[str, ...] = DEFAULT_HTTP_ALPN_PROTOCOLS

    def __post_init__(self) -> None:
        """Validate TLS settings after initialization.
        
        Raises:
            ConfigurationError: If validation fails
        """
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
        
        # Validate cipher suites list is non-empty
        if not self.cipher_suites:
            raise ConfigurationError("TLS cipher suites cannot be empty")
        
        parse_tls_version(self.minimum_version)
        if self.require_client_certificate and self.client_ca_file is None:
            raise ConfigurationError(
                "Client certificate authentication requires a trusted CA bundle"
            )


@dataclass(slots=True)
class ServiceMeta:
    """Metadata that describes the running service.
    
    Attributes:
        name: Service name for OpenAPI documentation
        version: Service version string
        description: Service description for OpenAPI
        metrics_path: HTTP path for Prometheus metrics endpoint
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        host: Host address to bind the server
        port: Port number for the HTTP server
        tls: Optional TLS configuration
    """

    name: str = "TradePulse Cortex Service"
    version: str = "1.0.0"
    description: str = "Cognitive signal orchestration for TradePulse portfolios"
    metrics_path: str = "/metrics"
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8001
    tls: ServiceTLSSettings | None = None


@dataclass(slots=True)
class DatabaseSettings:
    """Database connectivity details.
    
    Attributes:
        url: SQLAlchemy database URL
        pool_size: Maximum number of database connections in pool
        pool_timeout: Timeout in seconds for getting a connection
        echo: Whether to log SQL statements (debugging only)
        tls: Optional TLS configuration for PostgreSQL
    """

    url: str
    pool_size: int = 10
    pool_timeout: int = 30
    echo: bool = False
    tls: "DatabaseTLSSettings" | None = None


@dataclass(slots=True)
class DatabaseTLSSettings:
    """TLS credentials required for PostgreSQL connectivity.
    
    Attributes:
        ca_file: Path to PostgreSQL server CA certificate
        cert_file: Path to client certificate for PostgreSQL
        key_file: Path to client private key for PostgreSQL
    """

    ca_file: Path
    cert_file: Path
    key_file: Path

    def __post_init__(self) -> None:
        """Validate database TLS settings after initialization.
        
        Raises:
            ConfigurationError: If validation fails
        """
        self.ca_file = _ensure_file(Path(self.ca_file), description="PostgreSQL CA bundle")
        self.cert_file = _ensure_file(Path(self.cert_file), description="PostgreSQL client certificate")
        self.key_file = _ensure_file(Path(self.key_file), description="PostgreSQL client key")


@dataclass(slots=True)
class SignalSettings:
    """Hyper-parameters that shape signal computation.
    
    Attributes:
        rescale_min: Minimum bound for rescaled signal strength
        rescale_max: Maximum bound for rescaled signal strength
        smoothing_factor: Smoothing weight (0=no smoothing, 1=full smoothing)
        volatility_floor: Minimum volatility to prevent division by zero
    """

    rescale_min: float = -1.0
    rescale_max: float = 1.0
    smoothing_factor: float = 0.25
    volatility_floor: float = 1e-6


@dataclass(slots=True)
class RiskSettings:
    """Settings for portfolio risk evaluation.
    
    Attributes:
        max_absolute_exposure: Maximum allowed absolute exposure per instrument
        var_confidence: Confidence level for VaR calculation (0 < x < 1)
        stress_scenarios: Tuple of stress scenario multipliers (must be unique)
    """

    max_absolute_exposure: float = 2.0
    var_confidence: float = 0.95
    stress_scenarios: tuple[float, ...] = (0.85, 0.5)
    
    def __post_init__(self) -> None:
        """Validate risk settings after initialization.
        
        Raises:
            ConfigurationError: If validation fails
        """
        # Validate stress scenarios are unique
        if len(self.stress_scenarios) != len(set(self.stress_scenarios)):
            raise ConfigurationError("Stress scenarios must contain unique values")
        # Validate ordering (descending for stress scenarios makes sense)
        if len(self.stress_scenarios) > 1:
            sorted_scenarios = tuple(sorted(self.stress_scenarios, reverse=True))
            if self.stress_scenarios != sorted_scenarios:
                raise ConfigurationError(
                    f"Stress scenarios should be in descending order: {sorted_scenarios}"
                )


@dataclass(slots=True)
class RegimeSettings:
    """Parameters for market regime modulation.
    
    Attributes:
        decay: Decay factor for exponential smoothing (0 < x <= 1)
        min_valence: Minimum allowed regime valence
        max_valence: Maximum allowed regime valence
        confidence_floor: Minimum confidence level to report
    """

    decay: float = 0.2
    min_valence: float = -1.0
    max_valence: float = 1.0
    confidence_floor: float = 0.1


@dataclass(slots=True)
class CortexSettings:
    """Aggregated configuration for the cortex microservice.
    
    This is the top-level configuration object that combines all
    subsystem configurations.
    
    Attributes:
        service: Service metadata and HTTP server settings
        database: Database connection settings
        signals: Signal computation parameters
        risk: Risk assessment parameters
        regime: Market regime modulation parameters
    """

    service: ServiceMeta
    database: DatabaseSettings
    signals: SignalSettings
    risk: RiskSettings
    regime: RegimeSettings


def _deep_update(mapping: dict[str, Any], path: list[str], value: Any) -> None:
    """Update a nested mapping using the provided path.
    
    Args:
        mapping: The dictionary to update
        path: List of keys representing the nested path
        value: Value to set at the path location
    """
    cursor = mapping
    for key in path[:-1]:
        cursor = cursor.setdefault(key, {})
    cursor[path[-1]] = value


def _apply_env_overrides(raw: dict[str, Any]) -> dict[str, Any]:
    """Apply environment overrides using the ``CORTEX__`` prefix.
    
    Environment variables matching CORTEX__* are parsed as YAML and
    applied to the configuration. The variable name after the prefix
    is split on __ to create nested paths.
    
    Example:
        CORTEX__SERVICE__PORT=8080 sets config["service"]["port"] = 8080
    
    Args:
        raw: Base configuration dictionary
        
    Returns:
        Configuration with environment overrides applied
        
    Raises:
        ConfigurationError: If environment value contains invalid YAML
    """
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
    """Load and parse a YAML configuration file.
    
    Args:
        config_path: Path to the YAML configuration file
        
    Returns:
        Parsed configuration dictionary
        
    Raises:
        ConfigurationError: If file doesn't exist or contains invalid YAML
    """
    if not config_path.exists():
        raise ConfigurationError(f"Configuration file not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as handle:
        try:
            return yaml.safe_load(handle) or {}
        except yaml.YAMLError as exc:  # pragma: no cover - defensive branch
            raise ConfigurationError(f"Failed to parse configuration file {config_path}") from exc


def load_settings(config_path: str | os.PathLike[str] | None = None) -> CortexSettings:
    """Load settings from YAML and environment overrides.
    
    Configuration is loaded in the following order of precedence:
    1. Base YAML configuration file
    2. Environment variable overrides (CORTEX__ prefix)
    
    Args:
        config_path: Optional path to configuration file. If not provided,
            uses CORTEX_CONFIG_PATH environment variable or default path.
            
    Returns:
        Validated cortex configuration
        
    Raises:
        ConfigurationError: If configuration is invalid or cannot be loaded
    """
    # Resolve config path with proper type handling for mypy
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
            risk_config = {**risk_config, "stress_scenarios": tuple(float(s) for s in stress)}
        risk = RiskSettings(**risk_config)
        regime = RegimeSettings(**merged_config.get("regime", {}))
    except TypeError as exc:  # pragma: no cover - thin parsing wrapper
        raise ConfigurationError("Configuration payload is invalid") from exc

    settings = CortexSettings(service=service, database=database, signals=signals, risk=risk, regime=regime)
    
    # Cache the settings for reuse (singleton pattern)
    global _settings_cache
    _settings_cache = settings
    
    return settings


def get_cached_settings() -> CortexSettings | None:
    """Get the cached configuration if available.
    
    Returns:
        Cached settings or None if not yet loaded
    """
    return _settings_cache


__all__ = [
    "CortexSettings",
    "DatabaseSettings",
    "DatabaseTLSSettings",
    "DEFAULT_CONFIG_PATH",
    "RiskSettings",
    "RegimeSettings",
    "ServiceMeta",
    "ServiceTLSSettings",
    "SignalSettings",
    "get_cached_settings",
    "load_settings",
]
