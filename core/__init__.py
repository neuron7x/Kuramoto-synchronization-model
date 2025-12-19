"""Core TradePulse modules providing trading infrastructure and analytics.

This package contains the fundamental building blocks for the TradePulse platform:

- **config**: Typed configuration management with env overrides
- **interfaces**: Core protocols/ABCs (DataSource, Indicator, EventBus, etc.)
- **errors**: Typed domain errors (ValidationError, ConfigError, etc.)
- **telemetry**: Vendor-agnostic metrics interface with sampling
- **versioning**: Build metadata and config provenance hashing
- **tracing**: Distributed tracing and correlation-id propagation
- **indicators**: Geometric and technical market indicators (Kuramoto, Ricci Flow, etc.)
- **data**: Data ingestion, validation, and quality control
- **events**: Event sourcing and domain event infrastructure
- **messaging**: Event bus and message queue abstractions
- **neuro**: Neural network components and neuroeconomic controllers
- **utils**: Common utilities, logging, and helper functions
- **validation**: Physics, neuroscience, and mathematical validation modules
- **engine**: Core trading engine loop and scheduling
- **features**: Feature store interface and implementations
- **pipelines**: Workflow orchestration with idempotent stages
- **risk_monitoring**: Risk monitoring and fail-safe decisions
- **security**: Artifact integrity, TLS policy, secure RNG

For more information, see the documentation at https://docs.tradepulse.io

Public API Surface
------------------
This module exposes the following key components:

Configuration:
    ConfigRegistry, TradePulseSettings, ConfigValidationError

Logging & Observability:
    StructuredLogger, get_logger, configure_logging

Events & Messaging:
    EventBus, SchemaRegistry

Neuroeconomic Controllers:
    SerotoninController, SerotoninConfig

Example:
    >>> from core import get_logger, SerotoninController
    >>> logger = get_logger(__name__)
    >>> controller = SerotoninController()
"""

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - for static analysis only
    from core.config import (
        ConfigRegistry,
        ConfigValidationError,
        TradePulseSettings,
    )
    from core.neuro.serotonin import (
        SerotoninConfig,
        SerotoninConfigEnvelope,
        SerotoninController,
    )
    from core.utils.logging import (
        StructuredLogger,
        configure_logging,
        get_logger,
    )

__all__ = [
    # Configuration
    "ConfigRegistry",
    "ConfigValidationError",
    "TradePulseSettings",
    # Logging & Observability
    "StructuredLogger",
    "configure_logging",
    "get_logger",
    # Neuroeconomic Controllers
    "SerotoninConfig",
    "SerotoninConfigEnvelope",
    "SerotoninController",
]

# Version information
__version__ = "2.5.0"


def _missing_attr(name: str) -> AttributeError:
    """Construct a consistent AttributeError message for missing exports."""
    return AttributeError(f"module 'core' has no attribute {name!r}")


def _lazy_load(module_name: str, name: str) -> object:
    """Load ``name`` from ``module_name`` on demand and cache the export."""
    try:
        module = import_module(module_name)
        value = getattr(module, name)
    except (ImportError, AttributeError) as exc:  # pragma: no cover - propagate as AttributeError
        raise _missing_attr(name) from exc
    globals()[name] = value
    return value


def __getattr__(name: str) -> object:
    """Lazily resolve exported symbols; raises AttributeError for unknown names."""

    if name in {"ConfigRegistry", "ConfigValidationError", "TradePulseSettings"}:
        return _lazy_load("core.config", name)

    if name in {"StructuredLogger", "configure_logging", "get_logger"}:
        return _lazy_load("core.utils.logging", name)

    if name in {"SerotoninConfig", "SerotoninConfigEnvelope", "SerotoninController"}:
        return _lazy_load("core.neuro.serotonin", name)

    raise _missing_attr(name)
