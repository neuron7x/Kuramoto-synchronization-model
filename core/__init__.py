"""Core TradePulse modules providing trading infrastructure and analytics.

This package contains the fundamental building blocks for the TradePulse platform:

- **config**: Configuration models, registry, and validation
- **data**: Data ingestion, validation, and quality control
- **events**: Event sourcing and domain event infrastructure
- **messaging**: Event bus and message queue abstractions
- **neuro**: Neural network components and neuroeconomic controllers
- **utils**: Common utilities, logging, and helper functions
- **validation**: Physics, neuroscience, and mathematical validation modules

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

