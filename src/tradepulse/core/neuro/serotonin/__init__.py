"""Serotonin controller package with SRE observability."""

from .serotonin_controller import SerotoninConfig, SerotoninController
from .observability import (
    Alert,
    AlertSeverity,
    SerotoninMonitor,
    SLI,
    SLO,
    SEROTONIN_ALERTS,
    SEROTONIN_SLIS,
    SEROTONIN_SLOS,
)

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
]
