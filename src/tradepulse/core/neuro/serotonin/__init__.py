"""Legacy mirror for serotonin API; canonical lives in core.neuro.serotonin.*"""

from core.neuro.serotonin import (  # noqa: F401
    ControllerOutput,
    SerotoninConfig,
    SerotoninConfigEnvelope,
    SerotoninController,
    SerotoninLegacyConfig,
    _generate_config_table,
)
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
    "ControllerOutput",
    "SerotoninConfig",
    "SerotoninConfigEnvelope",
    "SerotoninController",
    "SerotoninLegacyConfig",
    "SerotoninMonitor",
    "SLI",
    "SLO",
    "SEROTONIN_ALERTS",
    "SEROTONIN_SLIS",
    "SEROTONIN_SLOS",
    "_generate_config_table",
    "create_grafana_dashboard_json",
    "create_prometheus_metrics",
]
