"""Deprecated mirror. Canonical module lives in core.neuro.serotonin.observability."""

from core.neuro.serotonin.observability import (  # noqa: F401
    SEROTONIN_ALERTS,
    SEROTONIN_SLIS,
    SEROTONIN_SLOS,
    SLI,
    SLO,
    Alert,
    AlertSeverity,
    SerotoninMonitor,
    create_grafana_dashboard_json,
    create_prometheus_metrics,
)

__all__ = [
    "Alert",
    "AlertSeverity",
    "SLI",
    "SLO",
    "SEROTONIN_ALERTS",
    "SEROTONIN_SLIS",
    "SEROTONIN_SLOS",
    "SerotoninMonitor",
    "create_grafana_dashboard_json",
    "create_prometheus_metrics",
]
