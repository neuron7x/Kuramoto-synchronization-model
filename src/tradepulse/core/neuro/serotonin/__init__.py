"""Serotonin controller package with SRE observability."""

__version__ = "2.4.0"

from .observability import (
    SEROTONIN_ALERTS,
    SEROTONIN_SLIS,
    SEROTONIN_SLOS,
    SLI,
    SLO,
    Alert,
    AlertSeverity,
    SerotoninMonitor,
)
from .serotonin_controller import SerotoninConfig, SerotoninController

__all__ = [
    "SerotoninConfig",
    "SerotoninController",
    "Alert",
    "AlertSeverity",
    "SerotoninMonitor",
    "SLI",
    "SLO",
    "SEROTONIN_ALERTS",
    "SEROTONIN_SLIS",
    "SEROTONIN_SLOS",
    "__version__",
]
